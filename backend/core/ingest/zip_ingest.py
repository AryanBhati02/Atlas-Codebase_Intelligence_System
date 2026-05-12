import asyncio
import logging
import shutil
import zipfile
from pathlib import Path

from core.ingest.file_filter import scan_directory
from models.schemas import FileEntry

logger = logging.getLogger("codebase-intel.ingest.zip")

MAX_ZIP_SIZE_BYTES: int = 100 * 1024 * 1024                           
MAX_EXTRACTED_SIZE_BYTES: int = 500 * 1024 * 1024                       

def validate_zip_file(file_path: Path) -> None:
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

def _do_extract_sync(file_path: Path, session_dir: Path) -> tuple[str, list[FileEntry]]:
    validate_zip_file(file_path)

    repo_dir = session_dir / "repo"

    logger.info(f"Extracting {file_path.name} → {repo_dir}")
    with zipfile.ZipFile(file_path, "r") as zf:
        zf.extractall(repo_dir)

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

    file_path.unlink(missing_ok=True)

    files = scan_directory(repo_dir)
    logger.info(f"Extraction complete: {len(files)} source files found")
    return repo_name, files

async def extract_zip_async(
    file_path: Path, session_dir: Path
) -> tuple[str, list[FileEntry]]:
    return await asyncio.to_thread(_do_extract_sync, file_path, session_dir)

def extract_zip(file_path: Path, session_dir: Path) -> tuple[str, list[FileEntry]]:
    return _do_extract_sync(file_path, session_dir)
