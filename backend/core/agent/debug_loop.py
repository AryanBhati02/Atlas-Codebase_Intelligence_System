"""
debug_loop.py
-------------
Automated debugging agent that uses Atlas behavioral search to find relevant
context for fixing failing tests, then drives an LLM to generate patches.

Components:
 - SandboxExecutor  : run tests + apply patches safely via subprocess
 - SimpleLLMClient  : Ollama-backed async LLM caller with graceful fallback
 - DebugAgent       : iterative fix loop (up to max_iterations)
 - DebugResult      : structured output of a debugging run
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("atlas.agent")

@dataclass
class DebugResult:
    solved: bool
    iterations: int
    fix_description: str
    fix_diff: str
    error_trace: str
    retrieval_results: list[dict] = field(default_factory=list)
    duration_seconds: float = 0.0

class SandboxExecutor:
    """Run tests safely in a subprocess with configurable timeout."""

    def __init__(self, timeout: int = 120):
        self.timeout = timeout

    def run_test(self, repo_path: str, test_command: str) -> dict:
        """
        Execute *test_command* inside *repo_path*.

        Returns:
            {"passed": bool, "stdout": str, "stderr": str,
             "return_code": int, "duration_ms": int}
        """
        start = time.monotonic()
        try:
            result = subprocess.run(
                test_command,
                shell=True,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            return {
                "passed": result.returncode == 0,
                "stdout": result.stdout[-5000:],
                "stderr": result.stderr[-5000:],
                "return_code": result.returncode,
                "duration_ms": duration_ms,
            }
        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "stdout": "",
                "stderr": f"Test timed out after {self.timeout}s",
                "return_code": -1,
                "duration_ms": self.timeout * 1000,
            }
        except Exception as exc:
            return {
                "passed": False,
                "stdout": "",
                "stderr": str(exc),
                "return_code": -1,
                "duration_ms": 0,
            }

    def apply_patch(self, repo_path: str, patch_text: str) -> bool:
        """
        Write *patch_text* to a temp file and apply it with ``git apply``.

        Returns True if the patch was applied successfully.
        """
        import tempfile as _tempfile

        with _tempfile.NamedTemporaryFile(
            mode="w", suffix=".patch", delete=False, encoding="utf-8"
        ) as f:
            f.write(patch_text)
            patch_file = f.name

        try:
            result = subprocess.run(
                f"git apply {patch_file}",
                shell=True,
                cwd=repo_path,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                logger.debug(f"git apply stderr: {result.stderr}")
            return result.returncode == 0
        finally:
            Path(patch_file).unlink(missing_ok=True)

class SimpleLLMClient:
    """
    Async LLM client backed by a local Ollama instance.

    Falls back gracefully if Ollama is unavailable so the rest of the eval
    can still run (returning an empty / error string).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "codellama",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def generate(self, prompt: str) -> str:
        """Send *prompt* to Ollama and return the response text."""
        try:
            import aiohttp
        except ImportError:
            return (
                "aiohttp not installed. Run: pip install aiohttp\n"
                "Cannot generate LLM response."
            )

        payload = {"model": self.model, "prompt": prompt, "stream": False}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("response", "")
                    else:
                        text = await resp.text()
                        return f"LLM error {resp.status}: {text[:500]}"
        except Exception as exc:
            return (
                f"LLM connection failed: {exc}. "
                "Make sure Ollama is running: ollama serve"
            )

class DebugAgent:
    """
    Automated debug agent.

    On each iteration:
      1. Run failing test → capture traceback
      2. Use Atlas retriever to find behaviorally-similar functions
      3. Ask LLM to generate a unified-diff fix
      4. Apply patch → re-run test
      5. Repeat up to max_iterations
    """

    def __init__(
        self,
        retriever,
        llm_client: SimpleLLMClient,
        sandbox: Optional[SandboxExecutor] = None,
        max_iterations: int = 5,
    ):
        self.retriever = retriever
        self.llm = llm_client
        self.sandbox = sandbox or SandboxExecutor()
        self.max_iterations = max_iterations

    async def solve(self, issue: dict) -> DebugResult:
        """
        Attempt to fix a failing test.

        `issue` keys:
            repo_path    – local path to the repo checkout
            issue_text   – description of the bug
            test_command – command that should pass after the fix
            test_file    – (optional) path to the test file
        """
        start_time = time.monotonic()
        all_retrieval_results: list[dict] = []
        last_error = ""
        fix_description = ""
        fix_diff = ""

        for iteration in range(1, self.max_iterations + 1):
            logger.info(
                f"[DebugAgent] iteration {iteration}/{self.max_iterations}"
            )

            test_result = self.sandbox.run_test(
                issue["repo_path"], issue["test_command"]
            )

            if test_result["passed"]:
                duration = time.monotonic() - start_time
                return DebugResult(
                    solved=True,
                    iterations=iteration,
                    fix_description=fix_description,
                    fix_diff=fix_diff,
                    error_trace="",
                    retrieval_results=all_retrieval_results,
                    duration_seconds=round(duration, 2),
                )

            error_text = test_result["stderr"] or test_result["stdout"]
            error_summary = self._parse_error(error_text)

            search_queries = [
                error_summary.get("error_type", "error handling"),
                f"fix {error_summary.get('function_name', 'bug')}",
                error_summary.get("file_name", ""),
            ]

            retrieval_context: list[dict] = []
            for query in search_queries:
                if not query.strip():
                    continue
                try:
                    results = await self.retriever.retrieve(query, top_k=3)
                    for r in results:
                        retrieval_context.append(
                            {
                                "name": r.name,
                                "file": r.file_path,
                                "line": r.line_start,
                                "similarity": r.behavioral_score,
                                "docstring": (r.docstring or "")[:200],
                            }
                        )
                except Exception as exc:
                    logger.debug(f"Retrieval failed for '{query}': {exc}")

            all_retrieval_results.extend(retrieval_context)

            prompt = self._build_fix_prompt(
                issue_text=issue["issue_text"],
                error_text=error_text[-3000:],
                retrieval_context=retrieval_context[:10],
                previous_error=last_error if iteration > 1 else None,
                iteration=iteration,
            )

            try:
                llm_response = await self.llm.generate(prompt)
                fix_diff = self._extract_diff(llm_response)
                fix_description = self._extract_description(llm_response)
            except Exception as exc:
                logger.error(f"LLM generation failed: {exc}")
                last_error = str(exc)
                continue

            if fix_diff:
                applied = self.sandbox.apply_patch(issue["repo_path"], fix_diff)
                if not applied:
                    logger.warning(
                        "Patch apply failed; trying direct file edits from LLM response"
                    )
                    self._apply_direct_edits(issue["repo_path"], llm_response)

            last_error = error_text[-1000:]

        # Max iterations exhausted
        duration = time.monotonic() - start_time
        return DebugResult(
            solved=False,
            iterations=self.max_iterations,
            fix_description=fix_description,
            fix_diff=fix_diff,
            error_trace=last_error,
            retrieval_results=all_retrieval_results,
            duration_seconds=round(duration, 2),
        )

    def _parse_error(self, error_text: str) -> dict:
        """
        Extract structured information from a Python traceback.

        Returns:
            {"error_type": str, "error_message": str, "file_name": str,
             "line_number": int, "function_name": str}
        """
        result = {
            "error_type": "",
            "error_message": "",
            "file_name": "",
            "line_number": 0,
            "function_name": "",
        }

        if not error_text:
            return result

        lines = error_text.splitlines()

        file_pattern = re.compile(
            r'^\s*File "(.+?)", line (\d+), in (.+)$'
        )
        for line in reversed(lines):
            m = file_pattern.match(line)
            if m:
                result["file_name"] = Path(m.group(1)).name
                result["line_number"] = int(m.group(2))
                result["function_name"] = m.group(3).strip()
                break

        exc_pattern = re.compile(r'^([A-Za-z][A-Za-z0-9_]*(?:Error|Exception|Warning|Fault)): (.+)$')
        for line in reversed(lines):
            m = exc_pattern.match(line.strip())
            if m:
                result["error_type"] = m.group(1)
                result["error_message"] = m.group(2)[:200]
                break

        if not result["error_type"]:
            for line in reversed(lines):
                stripped = line.strip()
                if stripped:
                    result["error_type"] = stripped[:80]
                    break

        return result

    def _build_fix_prompt(
        self,
        issue_text: str,
        error_text: str,
        retrieval_context: list[dict],
        previous_error: Optional[str],
        iteration: int,
    ) -> str:
        """Build the LLM prompt for fix generation."""
        context_str = ""
        for r in retrieval_context:
            sim = r.get("similarity", 0.0)
            context_str += (
                f"\n  - {r['name']} at {r['file']}:{r['line']}"
                f" (similarity: {sim:.2f}): {r['docstring']}"
            )

        prev_str = (
            f"Previous attempt failed with:\n{previous_error}\n\n"
            if previous_error
            else "This is the first attempt.\n\n"
        )

        prompt = (
            f"You are a debugging agent fixing a failing test.\n\n"
            f"Issue: {issue_text}\n\n"
            f"Current error:\n{error_text}\n\n"
            f"Atlas found these relevant functions in the codebase:{context_str}\n\n"
            f"{prev_str}"
            f"Iteration {iteration}. Generate a fix as a unified diff "
            f"(--- a/file, +++ b/file format).\n"
            f"Only modify the minimum code necessary. "
            f"Explain what you're fixing in one sentence before the diff."
        )
        return prompt

    def _extract_diff(self, llm_response: str) -> str:
        """Extract a unified diff from the LLM response."""
        # Prefer ```diff ... ``` blocks
        diff_match = re.search(r"```diff\n(.*?)```", llm_response, re.DOTALL)
        if diff_match:
            return diff_match.group(1)

        # Fallback: scan for --- +++ pattern
        lines = llm_response.split("\n")
        diff_lines: list[str] = []
        in_diff = False
        for line in lines:
            if line.startswith("--- ") or line.startswith("+++ "):
                in_diff = True
            if in_diff:
                diff_lines.append(line)

                if not line.strip() and len(diff_lines) > 3:
                    break

        return "\n".join(diff_lines) if diff_lines else ""

    def _extract_description(self, llm_response: str) -> str:
        """Return the first substantive sentence from the LLM response."""
        for line in llm_response.strip().split("\n"):
            line = line.strip()
            if (
                line
                and not line.startswith("```")
                and not line.startswith("---")
                and not line.startswith("+++")
            ):
                return line[:200]
        return "Fix applied"

    def _apply_direct_edits(self, repo_path: str, llm_response: str) -> None:
        """
        Fallback: extract file blocks from LLM response and overwrite files.

        Expects blocks like:
            ```python
            # File: path/to/file.py
            <content>
            ```
        """
        file_blocks = re.findall(
            r"```(?:python|javascript|typescript)?\n# File: (.+?)\n(.*?)```",
            llm_response,
            re.DOTALL,
        )
        for file_path_str, content in file_blocks:
            full_path = Path(repo_path) / file_path_str.strip()
            if full_path.exists():
                try:
                    full_path.write_text(content, encoding="utf-8")
                    logger.info(f"Direct edit applied to {full_path}")
                except OSError as exc:
                    logger.warning(f"Could not write {full_path}: {exc}")
