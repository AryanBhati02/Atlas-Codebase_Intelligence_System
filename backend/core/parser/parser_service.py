"""Parser orchestrator — routes files to the correct parser by language.

Uses ThreadPoolExecutor with BATCHED submission to prevent OOM on large repos.
Files are processed in chunks of PARSE_BATCH_SIZE (default 500) so that at most
~500 futures exist in memory at once instead of 100K+.
"""

import os
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.parser.python_parser import parse_python
from core.parser.js_parser import parse_js
from config import PARSE_BATCH_SIZE

logger = logging.getLogger("codebase-intel.parser")

_PYTHON_EXTS = {".py"}
_JS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"}


_MAX_WORKERS = min(16, max(4, (os.cpu_count() or 4) * 2))


def parse_file(content: str, file_path: str, extension: str) -> dict:
    ext = extension.lower()
    if ext in _PYTHON_EXTS:
        return parse_python(content, file_path)
    elif ext in _JS_EXTS:
        return parse_js(content, file_path)
    else:
        lines = content.split("\n")
        loc = sum(1 for l in lines if l.strip())
        return {
            "path": file_path,
            "imports": [],
            "functions": [],
            "classes": [],
            "loc": loc,
            "nesting_depth": 0,
        }


def _parse_single_entry(repo_dir_str: str, entry: dict) -> dict | None:
    """Read + parse a single file. Runs in a thread."""
    fpath = Path(repo_dir_str) / entry["path"]
    if not fpath.exists():
        return None
    try:
        content = fpath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    result = parse_file(content, entry["path"], entry.get("extension", ""))
    result["size_bytes"] = entry.get("size_bytes", 0)
    result["language"] = entry.get("language")
    return result


def parse_all_files(repo_dir: Path, file_entries: list[dict], progress_callback=None) -> list[dict]:
    """
    Parse all files using batched thread pool for parallel I/O + parsing.

    Instead of submitting ALL files to the executor at once (which creates
    100K+ futures in memory for large repos), we process in batches of
    PARSE_BATCH_SIZE. Each batch creates a fresh set of futures, processes
    them, then releases memory before the next batch.
    """
    total = len(file_entries)

    if total == 0:
        return []

    repo_dir_str = str(repo_dir)
    parsed: list[dict] = []
    completed = 0
    batch_size = PARSE_BATCH_SIZE

    logger.info(f"Parsing {total} files in batches of {batch_size} "
                f"(workers={_MAX_WORKERS})")

    for batch_start in range(0, total, batch_size):
        batch = file_entries[batch_start:batch_start + batch_size]

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {
                pool.submit(_parse_single_entry, repo_dir_str, entry): entry
                for entry in batch
            }

            for future in as_completed(futures):
                completed += 1
                try:
                    result = future.result(timeout=10)
                    if result:
                        parsed.append(result)
                except Exception as e:
                    entry = futures[future]
                    logger.debug(f"Parse failed for {entry.get('path', '?')}: {e}")

                
                if progress_callback and (completed % 5 == 0 or completed == total):
                    progress_callback("parsing", completed, total)

    logger.info(f"Parsing complete: {len(parsed)}/{total} files parsed")
    return parsed
