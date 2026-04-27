"""
Parser orchestrator — sync and async interfaces for file parsing.

parse_all_files_async  (primary)
    Async, bounded by asyncio.Semaphore(10).
    Each file is parsed in a thread via asyncio.to_thread() so CPU-bound
    ast.parse() and regex work never blocks the event loop.
    Call via asyncio.run() from Celery tasks or threading fallback.

parse_all_files  (backward compat)
    Sync, batched ThreadPoolExecutor.
    Kept for tests and any call sites that haven't migrated yet.
"""

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from config import PARSE_BATCH_SIZE
from core.parser.js_parser import parse_js
from core.parser.python_parser import parse_python

logger = logging.getLogger("codebase-intel.parser")

_PYTHON_EXTS = {".py"}
_JS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"}
_MAX_WORKERS = min(16, max(4, (os.cpu_count() or 4) * 2))

# Secondary filter: catch artifact files that slipped through file_filter.
# file_filter already blocks most of these via IGNORED_DIRS / IGNORED_EXTENSIONS,
# but a shallow clone may include generated files in unexpected locations.
_SKIP_DIRS = frozenset({"node_modules", "__pycache__", "dist", "build", ".git"})
_SKIP_NAME_SUFFIXES = (".min.js", ".min.css", ".bundle.js", ".chunk.js")


# ── Helper ────────────────────────────────────────────────────────────────────

def parse_file(content: str, file_path: str, extension: str) -> dict:
    """Route file content to the correct language parser."""
    ext = extension.lower()
    if ext in _PYTHON_EXTS:
        return parse_python(content, file_path)
    if ext in _JS_EXTS:
        return parse_js(content, file_path)
    # Generic fallback: count non-blank lines, no AST extraction.
    loc = sum(1 for line in content.split("\n") if line.strip())
    return {
        "path": file_path,
        "imports": [],
        "functions": [],
        "classes": [],
        "loc": loc,
        "nesting_depth": 0,
    }


def _should_skip(entry: dict) -> bool:
    """Return True for files that should not be parsed (secondary filter)."""
    path: str = entry.get("path", "").replace("\\", "/")
    parts = path.split("/")
    # Skip files nested inside artifact directories
    if any(part in _SKIP_DIRS for part in parts[:-1]):
        return True
    # Skip files with known minified/generated name suffixes
    name = parts[-1] if parts else ""
    return any(name.endswith(suf) for suf in _SKIP_NAME_SUFFIXES)


def _parse_single_entry(repo_dir_str: str, entry: dict) -> dict | None:
    """
    Read + parse one file. Runs in a thread pool thread.
    Returns None if the file should be skipped or cannot be read/parsed.
    No shared mutable state — safe for concurrent use.
    """
    if _should_skip(entry):
        return None

    fpath = Path(repo_dir_str) / entry["path"]
    if not fpath.exists():
        return None

    try:
        content = fpath.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        logger.debug(f"Read error for {entry['path']}: {exc}")
        return None

    try:
        result = parse_file(content, entry["path"], entry.get("extension", ""))
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"Parse error for {entry['path']}: {exc}")
        return None

    result["size_bytes"] = entry.get("size_bytes", 0)
    result["language"] = entry.get("language")
    return result


# ── Async interface (primary) ─────────────────────────────────────────────────

async def parse_all_files_async(
    repo_dir: Path,
    file_entries: list[dict],
    progress_callback=None,
) -> list[dict]:
    """
    Parse all files with bounded async concurrency.

    asyncio.Semaphore(10) caps the number of simultaneous asyncio.to_thread()
    calls, preventing thread-pool and memory explosion on large repos.

    progress_callback(current: int, total: int) is called after each file
    completes (from within the event loop, so it must be non-blocking).

    Usage:
        # From a Celery task or daemon thread:
        parsed = asyncio.run(parse_all_files_async(repo_dir, entries))

        # From an async function:
        parsed = await parse_all_files_async(repo_dir, entries)
    """
    if not file_entries:
        return []

    total = len(file_entries)
    repo_dir_str = str(repo_dir)
    sem = asyncio.Semaphore(10)
    results: list[dict] = []
    parsed_count = 0
    count_lock = asyncio.Lock()

    logger.info(f"Async parsing {total} files (semaphore=10, workers≤{_MAX_WORKERS})")

    async def _parse_one(entry: dict) -> dict | None:
        nonlocal parsed_count
        async with sem:
            # Run blocking read + AST parse in a thread so the event loop
            # is never blocked, even on files that take tens of milliseconds.
            result = await asyncio.to_thread(_parse_single_entry, repo_dir_str, entry)
            async with count_lock:
                parsed_count += 1
                count = parsed_count  # capture for callback
            if progress_callback and (count % 10 == 0 or count == total):
                progress_callback(count, total)
            return result

    tasks = [_parse_one(entry) for entry in file_entries]
    raw = await asyncio.gather(*tasks, return_exceptions=True)

    for item in raw:
        if isinstance(item, BaseException):
            logger.debug(f"gather() exception: {item}")
        elif item is not None:
            results.append(item)

    logger.info(f"Async parse done: {len(results)}/{total} files parsed successfully")
    return results


# ── Sync interface (backward compat) ─────────────────────────────────────────

def parse_all_files(
    repo_dir: Path,
    file_entries: list[dict],
    progress_callback=None,
) -> list[dict]:
    """
    Sync batched parser using ThreadPoolExecutor.

    Processes PARSE_BATCH_SIZE files per batch so that at most ~batch_size
    futures exist in memory at once (prevents OOM on 100 K-file repos).

    progress_callback(stage: str, current: int, total: int)
    """
    total = len(file_entries)
    if total == 0:
        return []

    repo_dir_str = str(repo_dir)
    parsed: list[dict] = []
    completed = 0
    batch_size = PARSE_BATCH_SIZE

    logger.info(f"Sync parsing {total} files in batches of {batch_size} (workers={_MAX_WORKERS})")

    for batch_start in range(0, total, batch_size):
        batch = file_entries[batch_start : batch_start + batch_size]

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {
                pool.submit(_parse_single_entry, repo_dir_str, entry): entry
                for entry in batch
            }
            for future in as_completed(futures):
                completed += 1
                try:
                    result = future.result(timeout=10)
                    if result is not None:
                        parsed.append(result)
                except Exception as exc:
                    entry = futures[future]
                    logger.debug(f"Parse failed for {entry.get('path', '?')}: {exc}")

                if progress_callback and (completed % 5 == 0 or completed == total):
                    progress_callback("parsing", completed, total)

    logger.info(f"Sync parse done: {len(parsed)}/{total} files parsed successfully")
    return parsed
