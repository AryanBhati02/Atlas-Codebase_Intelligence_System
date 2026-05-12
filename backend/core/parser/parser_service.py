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

_SKIP_DIRS = frozenset({"node_modules", "__pycache__", "dist", "build", ".git"})
_SKIP_NAME_SUFFIXES = (".min.js", ".min.css", ".bundle.js", ".chunk.js")

def parse_file(content: str, file_path: str, extension: str) -> dict:
    ext = extension.lower()
    if ext in _PYTHON_EXTS:
        return parse_python(content, file_path)
    if ext in _JS_EXTS:
        return parse_js(content, file_path)
                                                                 
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
    path: str = entry.get("path", "").replace("\\", "/")
    parts = path.split("/")
                                                   
    if any(part in _SKIP_DIRS for part in parts[:-1]):
        return True
                                                            
    name = parts[-1] if parts else ""
    return any(name.endswith(suf) for suf in _SKIP_NAME_SUFFIXES)

def _parse_single_entry(repo_dir_str: str, entry: dict) -> dict | None:
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
    except Exception as exc:                
        logger.debug(f"Parse error for {entry['path']}: {exc}")
        return None

    result["size_bytes"] = entry.get("size_bytes", 0)
    result["language"] = entry.get("language")
    return result

async def parse_all_files_async(
    repo_dir: Path,
    file_entries: list[dict],
    progress_callback=None,
) -> list[dict]:
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
                                                                         
            result = await asyncio.to_thread(_parse_single_entry, repo_dir_str, entry)
            async with count_lock:
                parsed_count += 1
                count = parsed_count                        
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

def parse_all_files(
    repo_dir: Path,
    file_entries: list[dict],
    progress_callback=None,
) -> list[dict]:
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
