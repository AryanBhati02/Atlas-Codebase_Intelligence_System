"""
ZIP file ingestion with safety validation.

extract_zip_async   (primary)  — non-blocking, uses asyncio.to_thread()
extract_zip         (sync)     — kept for tests and backward compat

Safety checks enforced before extraction:
  - Valid ZIP archive
  - Compressed file ≤ 100 MB
  - Uncompressed total ≤ 500 MB (zip-bomb guard)
  - No path traversal (../ or absolute paths)
"""

import asyncio
import logging
import shutil
import zipfile
from pathlib import Path

from core.ingest.file_filter import scan_directory
from models.schemas import FileEntry

logger = logging.getLogger("codebase-intel.ingest.zip")

MAX_ZIP_SIZE_BYTES: int = 100 * 1024 * 1024        # 100 MB compressed
MAX_EXTRACTED_SIZE_BYTES: int = 500 * 1024 * 1024  # 500 MB uncompressed


# ── Validation ────────────────────────────────────────────────────────────────

def validate_zip_file(file_path: Path) -> None:
    """
    Validate the ZIP file for safety before extraction.

    Raises ValueError with a user-readable message on every failure.
    """
    if not zipfile.is_zipfile(file_path):
        raise ValueError("Uploaded file is not a valid ZIP archive.")

    file_size = file_path.stat().st_size
    if file_size > MAX_ZIP_SIZE_BYTES:
        raise ValueError(
            f"ZIP file too large: {file_size / 1024 / 1024:.1f} MB "
            f"(limit: {MAX_ZIP_SIZE_BYTES // 1024 // 1024} MB)."
        )

    with zipfile.ZipFile(file_path, "r") as zf:
        total_uncompressed = sum(info.file_size for info in zf.infolist())
        if total_uncompressed > MAX_EXTRACTED_SIZE_BYTES:
            raise ValueError(
                f"Extracted content too large: "
                f"{total_uncompressed / 1024 / 1024:.1f} MB "
                f"(limit: {MAX_EXTRACTED_SIZE_BYTES // 1024 // 1024} MB). "
                "Possible zip bomb detected."
            )
        for info in zf.infolist():
            if info.filename.startswith("/") or ".." in info.filename:
                raise ValueError(
                    "ZIP contains unsafe file paths (path traversal detected). "
                    "Re-archive the repository without absolute or relative paths."
                )


# ── Core extraction logic ─────────────────────────────────────────────────────

def _do_extract_sync(file_path: Path, session_dir: Path) -> tuple[str, list[FileEntry]]:
    """
    Validate + extract a ZIP into session_dir/repo/ and return
    (repo_name, file_entries).  Intended to run inside asyncio.to_thread().

    If the ZIP has a single root directory (common for GitHub downloads),
    that directory is flattened so session_dir/repo/ is the repo root.
    """
    validate_zip_file(file_path)

    repo_dir = session_dir / "repo"

    logger.info(f"Extracting {file_path.name} → {repo_dir}")
    with zipfile.ZipFile(file_path, "r") as zf:
        zf.extractall(repo_dir)

    # Flatten single-root-folder ZIPs (e.g., myrepo-main/ from GitHub exports).
    contents = list(repo_dir.iterdir())
    if len(contents) == 1 and contents[0].is_dir():
        single_dir = contents[0]
        repo_name = single_dir.name
        temp_dir = session_dir / "_temp_extract"
        shutil.move(str(single_dir), str(temp_dir))
        shutil.rmtree(repo_dir)
        shutil.move(str(temp_dir), str(repo_dir))
    else:
        repo_name = file_path.stem

    # Remove the uploaded archive — no longer needed.
    file_path.unlink(missing_ok=True)

    files = scan_directory(repo_dir)
    logger.info(f"Extraction complete: {len(files)} source files found")
    return repo_name, files


# ── Public async API ──────────────────────────────────────────────────────────

async def extract_zip_async(
    file_path: Path, session_dir: Path
) -> tuple[str, list[FileEntry]]:
    """
    Extract a ZIP archive (non-blocking) and return (repo_name, file_entries).

    zipfile.ZipFile.extractall() is I/O-bound and can stall the event loop
    for large archives; running it in a thread keeps FastAPI responsive.

    Raises:
        ValueError  — validation failed (size, path traversal, not a ZIP).
        OSError     — filesystem error during extraction.
    """
    return await asyncio.to_thread(_do_extract_sync, file_path, session_dir)


# ── Sync fallback (tests / backward compat) ───────────────────────────────────

def extract_zip(file_path: Path, session_dir: Path) -> tuple[str, list[FileEntry]]:
    """Synchronous extraction. Use extract_zip_async in production."""
    return _do_extract_sync(file_path, session_dir)
