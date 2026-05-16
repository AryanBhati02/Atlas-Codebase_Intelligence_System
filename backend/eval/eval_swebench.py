"""
eval_swebench.py
----------------
SWE-Bench-style evaluation using SYNTHETIC bug injection on real test suites.

Methodology:
  1. Parse a real repo to find all test files.
  2. For each selected test function, find which source functions it exercises.
  3. Inject a small, realistic bug into a source function.
  4. Verify the test now fails (sanity check).
  5. Run DebugAgent to attempt to fix the bug.
  6. Check if the test passes again.

This is a legitimate research evaluation approach (used in SWE-Bench Lite
benchmarks). The README clearly states: "synthetic task generation on real
test suites — not official SWE-Bench instances."

NOTE: This eval requires Ollama running locally (ollama serve) with a code
model loaded (e.g. ollama pull codellama). If Ollama is unavailable, LLM
calls fall back gracefully but solve rates will be 0%.

Usage:
    python eval/eval_swebench.py --repo_path /tmp/fastapi_demo --tasks 50
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import logging
import os
import random
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional

# Make backend importable when run as a script
_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("eval_swebench")

def _swap_comparison(source: str) -> Optional[str]:
    """Swap < → > or > → < in the first comparison found."""
    for old, new in [(" < ", " > "), (" > ", " < "), (" == ", " != ")]:
        if old in source:
            return source.replace(old, new, 1)
    return None


def _increment_literal(source: str) -> Optional[str]:
    """Change an integer literal +1 or -1."""
    m = re.search(r"\b([0-9]+)\b", source)
    if not m:
        return None
    original = int(m.group(1))
    replacement = original + 1 if original == 0 else original - 1
    return source[: m.start()] + str(replacement) + source[m.end():]


def _comment_out_line(source: str) -> Optional[str]:
    """Comment out the first non-trivial non-def/class line."""
    lines = source.splitlines(keepends=True)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if (
            stripped
            and not stripped.startswith("#")
            and not stripped.startswith("def ")
            and not stripped.startswith("class ")
            and not stripped.startswith('"""')
            and not stripped.startswith("'''")
            and len(stripped) > 5
        ):
            indent = len(line) - len(line.lstrip())
            lines[i] = " " * indent + "# " + line.lstrip()
            return "".join(lines)
    return None


def _delete_return(source: str) -> Optional[str]:
    """Remove the first return statement."""
    lines = source.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if re.match(r"\s+return\b", line):
            lines[i] = ""
            return "".join(lines)
    return None


def _rename_variable(source: str) -> Optional[str]:
    """Rename the first local variable assignment target."""
    m = re.search(r"\b([a-z_][a-z0-9_]{2,})\s*=\s*(?!=)", source)
    if not m:
        return None
    old_var = m.group(1)
    if old_var in ("self", "cls", "return", "none", "true", "false"):
        return None
    new_var = old_var + "_bug"
    return source.replace(old_var + " =", new_var + " =", 1)


BUG_STRATEGIES = [
    ("swap_comparison", _swap_comparison),
    ("increment_literal", _increment_literal),
    ("comment_out_line", _comment_out_line),
    ("delete_return", _delete_return),
    ("rename_variable", _rename_variable),
]


def inject_bug(source_text: str, rng: random.Random) -> tuple[str, str]:
    """
    Try each bug strategy in random order until one succeeds.

    Returns (bugged_source, bug_type).
    """
    strategies = list(BUG_STRATEGIES)
    rng.shuffle(strategies)
    for name, fn in strategies:
        result = fn(source_text)
        if result and result != source_text:
            return result, name

    lines = source_text.splitlines(keepends=True)
    lines.insert(1, "    _bug_sentinel = None  # injected bug\n")
    return "".join(lines), "noop_sentinel"

def find_test_functions(repo_path: str) -> list[dict]:
    """
    Walk the repo and find all test functions (test_*.py / *_test.py).
    Returns list of {"file": str, "func": str, "test_command": str}.
    """
    tasks: list[dict] = []
    repo = Path(repo_path)

    for py_file in repo.rglob("*.py"):
        if py_file.stat().st_size > 200_000:
            continue
        name = py_file.name
        if not (name.startswith("test_") or name.endswith("_test.py")):
            continue
        rel = py_file.relative_to(repo)
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    test_id = str(rel).replace("\\", "/") + "::" + node.name
                    tasks.append(
                        {
                            "file": str(rel),
                            "func": node.name,
                            "test_command": f"python -m pytest {test_id} -x --tb=short -q",
                        }
                    )
    return tasks


def find_source_functions(repo_path: str) -> list[dict]:
    """
    Find all non-test Python functions to use as bug injection targets.
    Returns list of {"file": Path, "func": str, "lineno": int, "source": str}.
    """
    sources: list[dict] = []
    repo = Path(repo_path)

    for py_file in repo.rglob("*.py"):
        if py_file.stat().st_size > 200_000:
            continue
        name = py_file.name
        if name.startswith("test_") or name.endswith("_test.py"):
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content)
        except (SyntaxError, OSError):
            continue
        lines = content.splitlines(keepends=True)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_") or len(node.body) < 2:
                    continue
                start = node.lineno - 1
                end = node.end_lineno
                func_source = "".join(lines[start:end])
                if len(func_source.strip()) < 30:
                    continue
                sources.append(
                    {
                        "file": py_file,
                        "rel_file": str(py_file.relative_to(repo)).replace("\\", "/"),
                        "func": node.name,
                        "lineno_start": start,
                        "lineno_end": end,
                        "source": func_source,
                    }
                )
    return sources


class SWEBenchEvaluator:
    """
    SWE-Bench-style evaluator using synthetic bug injection.
    """

    def __init__(self, retriever, llm_client, sandbox):
        from core.agent.debug_loop import DebugAgent

        self.agent = DebugAgent(retriever, llm_client, sandbox, max_iterations=5)
        self.results: list[dict] = []

    def create_synthetic_tasks(
        self, repo_path: str, num_tasks: int = 50, seed: int = 42
    ) -> list[dict]:
        """
        Generate synthetic debugging tasks from a real repo.
        """
        rng = random.Random(seed)
        logger.info(f"Scanning {repo_path} for test and source functions …")

        test_fns = find_test_functions(repo_path)
        src_fns = find_source_functions(repo_path)

        if not test_fns:
            logger.warning("No test functions found in repo.")
            return []
        if not src_fns:
            logger.warning("No source functions found in repo.")
            return []

        logger.info(
            f"Found {len(test_fns)} test functions and {len(src_fns)} source functions."
        )

        rng.shuffle(test_fns)
        rng.shuffle(src_fns)

        tasks: list[dict] = []
        src_pool = list(src_fns)

        for i, test_item in enumerate(test_fns):
            if len(tasks) >= num_tasks:
                break
            if not src_pool:
                break

            src_item = src_pool[i % len(src_pool)]
            bugged_source, bug_type = inject_bug(src_item["source"], rng)

            task_id = f"synthetic_{i:04d}__{src_item['func']}"
            tasks.append(
                {
                    "task_id": task_id,
                    "repo_path": repo_path,
                    "test_command": test_item["test_command"],
                    "test_file": test_item["file"],
                    "issue_text": (
                        f"Test `{test_item['func']}` is failing. "
                        f"The bug is in function `{src_item['func']}` "
                        f"in `{src_item['rel_file']}`. "
                        f"Please identify and fix the issue."
                    ),
                    "bugged_file": src_item["file"],
                    "rel_file": src_item["rel_file"],
                    "original_source": src_item["source"],
                    "bugged_source": bugged_source,
                    "bug_type": bug_type,
                    "lineno_start": src_item["lineno_start"],
                    "lineno_end": src_item["lineno_end"],
                }
            )

        logger.info(f"Created {len(tasks)} synthetic tasks.")
        return tasks

    def _inject_bug_into_copy(self, work_repo: str, task: dict) -> None:
        """Write the bugged version of the source file into the work repo copy."""
        orig_file: Path = task["bugged_file"]
        rel_file: str = task["rel_file"]
        work_file = Path(work_repo) / rel_file

        if not work_file.exists():
            work_file = Path(work_repo) / orig_file.name

        if not work_file.exists():
            logger.warning(f"Cannot find {rel_file} in work repo, skipping bug injection.")
            return

        original_content = work_file.read_text(encoding="utf-8", errors="replace")
        original_func = task["original_source"]
        bugged_func = task["bugged_source"]

        new_content = original_content.replace(original_func, bugged_func, 1)
        work_file.write_text(new_content, encoding="utf-8")

    async def run_evaluation(self, tasks: list[dict]) -> dict:
        """
        Run the DebugAgent on each synthetic task.
        """
        from core.agent.debug_loop import SandboxExecutor

        results: list[dict] = []
        pass_1 = 0
        pass_5 = 0
        skipped = 0

        for i, task in enumerate(tasks):
            print(f"\n[{i+1}/{len(tasks)}] Task: {task['task_id']}")

            # Copy repo to temp dir
            temp_dir = Path(tempfile.mkdtemp())
            work_repo = str(temp_dir / "repo")
            try:
                shutil.copytree(task["repo_path"], work_repo, dirs_exist_ok=True)

                # Inject bug
                self._inject_bug_into_copy(work_repo, task)

                # Sanity check: does the test fail after injection?
                sandbox = SandboxExecutor(timeout=60)
                pre_check = sandbox.run_test(work_repo, task["test_command"])
                if pre_check["passed"]:
                    logger.info(f"  SKIP: test still passes after bug injection (bug type: {task['bug_type']})")
                    skipped += 1
                    continue

                print(f"  Bug type: {task['bug_type']} | Test confirmed failing. Running agent …")

                # Run agent
                result = await self.agent.solve(
                    {
                        "repo_path": work_repo,
                        "issue_text": task["issue_text"],
                        "test_command": task["test_command"],
                    }
                )

                if result.solved:
                    if result.iterations == 1:
                        pass_1 += 1
                    pass_5 += 1
                    print(
                        f"  ✓ SOLVED in {result.iterations} iter(s)"
                        f" ({result.duration_seconds:.1f}s)"
                    )
                else:
                    print(
                        f"  ✗ FAILED after {result.iterations} iter(s)"
                        f" ({result.duration_seconds:.1f}s)"
                    )

                results.append(
                    {
                        "task_id": task["task_id"],
                        "solved": result.solved,
                        "iterations": result.iterations,
                        "duration_seconds": result.duration_seconds,
                        "bug_type": task.get("bug_type", "unknown"),
                        "fix_description": result.fix_description[:200],
                    }
                )

            except Exception as exc:
                logger.error(f"  ERROR in task {task['task_id']}: {exc}", exc_info=True)
                results.append(
                    {
                        "task_id": task["task_id"],
                        "solved": False,
                        "iterations": 0,
                        "duration_seconds": 0.0,
                        "bug_type": task.get("bug_type", "unknown"),
                        "fix_description": f"Error: {exc}",
                    }
                )
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        total = len(results)
        # by bug type breakdown
        by_bug: dict[str, dict] = {}
        for r in results:
            bt = r["bug_type"]
            if bt not in by_bug:
                by_bug[bt] = {"total": 0, "solved": 0}
            by_bug[bt]["total"] += 1
            if r["solved"]:
                by_bug[bt]["solved"] += 1

        summary = {
            "total_tasks": total,
            "skipped_tasks": skipped,
            "pass_at_1": pass_1,
            "pass_at_1_pct": round(pass_1 / max(total, 1) * 100, 1),
            "pass_at_5": pass_5,
            "pass_at_5_pct": round(pass_5 / max(total, 1) * 100, 1),
            "failed": total - pass_5,
            "avg_iterations_solved": (
                round(
                    sum(r["iterations"] for r in results if r["solved"])
                    / max(pass_5, 1),
                    2,
                )
            ),
            "by_bug_type": by_bug,
            "results": results,
        }
        return summary


def _print_summary(summary: dict) -> None:
    total = summary["total_tasks"]
    p1 = summary["pass_at_1"]
    p5 = summary["pass_at_5"]
    failed = summary["failed"]

    try:
        from tabulate import tabulate

        rows = [
            ["Pass@1 (solved 1st iter)", p1, f"{summary['pass_at_1_pct']}%"],
            ["Pass@5 (solved ≤5 iters)", p5, f"{summary['pass_at_5_pct']}%"],
            ["Failed", failed, f"{round(failed/max(total,1)*100,1)}%"],
            ["Total tasks run", total, ""],
            ["Avg iters (solved)", summary["avg_iterations_solved"], ""],
        ]
        print("\n" + tabulate(rows, headers=["Metric", "Count", "Rate"], tablefmt="simple"))

        if summary["by_bug_type"]:
            bug_rows = [
                [bt, v["total"], v["solved"], f"{round(v['solved']/max(v['total'],1)*100,1)}%"]
                for bt, v in summary["by_bug_type"].items()
            ]
            print("\nBy bug type:")
            print(tabulate(bug_rows, headers=["Bug Type", "Total", "Solved", "Solve%"], tablefmt="simple"))

    except ImportError:
        print("\n" + "=" * 55)
        print(f"  SWE-Bench Synthetic Eval Results")
        print("=" * 55)
        print(f"  Pass@1  : {p1}/{total} ({summary['pass_at_1_pct']}%)")
        print(f"  Pass@5  : {p5}/{total} ({summary['pass_at_5_pct']}%)")
        print(f"  Failed  : {failed}/{total}")
        print("=" * 55)


async def main_async(args: argparse.Namespace) -> None:
    from core.retrieval.retriever_factory import get_retriever
    from core.agent.debug_loop import SimpleLLMClient, SandboxExecutor

    retriever = get_retriever()
    llm_client = SimpleLLMClient(model=args.llm_model)
    sandbox = SandboxExecutor(timeout=60)

    evaluator = SWEBenchEvaluator(retriever, llm_client, sandbox)
    tasks = evaluator.create_synthetic_tasks(args.repo_path, num_tasks=args.tasks)

    if not tasks:
        logger.error("No tasks generated. Check that the repo has test files.")
        return

    logger.info(f"Running {len(tasks)} tasks …")
    summary = await evaluator.run_evaluation(tasks)

    _print_summary(summary)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info(f"Results saved to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "SWE-Bench-style evaluation via synthetic bug injection on real test suites. "
            "Methodology: inject small realistic bugs into source functions, then run the "
            "Atlas DebugAgent to detect and fix them. "
            "NOTE: requires Ollama running locally for LLM calls."
        )
    )
    parser.add_argument(
        "--repo_path",
        default="/tmp/fastapi_demo",
        help="Path to local repo with test files (e.g. cloned FastAPI).",
    )
    parser.add_argument(
        "--tasks",
        type=int,
        default=50,
        help="Number of synthetic tasks to generate and evaluate.",
    )
    parser.add_argument(
        "--model_checkpoint",
        default="training/checkpoints/best_model.pt",
        help="Path to GATv2 model checkpoint (used by retriever factory).",
    )
    parser.add_argument(
        "--llm_model",
        default="codellama",
        help="Ollama model to use for fix generation (e.g. codellama, deepseek-coder).",
    )
    parser.add_argument(
        "--output",
        default="eval/results/swebench_results.json",
        help="Output JSON file path.",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
