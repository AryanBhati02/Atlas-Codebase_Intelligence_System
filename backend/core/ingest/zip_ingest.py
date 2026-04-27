"""
ZIP file ingestion with safety validation.
Handles extraction, zip bomb detection, and path traversal prevention.
"""

import zipfile
import shutil
from pathlib import Path

from models.schemas import FileEntry
from core.ingest.file_filter import scan_directory

MAX_ZIP_SIZE_BYTES: int = 100 * 1024 * 1024       
MAX_EXTRACTED_SIZE_BYTES: int = 500 * 1024 * 1024  


def validate_zip_file(file_path: Path) -> None:
    """
    Validate ZIP file for safety:
    - Must be a valid ZIP archive
    - Must not exceed size limits
    - Must not contain path traversal attacks
    - Must not be a zip bomb
    """
    if not zipfile.is_zipfile(file_path):
        raise ValueError("Uploaded file is not a valid ZIP archive.")

    file_size = file_path.stat().st_size
    if file_size > MAX_ZIP_SIZE_BYTES:
        raise ValueError(
            f"ZIP file too large: {file_size / 1024 / 1024:.1f}MB (max 100MB)."
        )

    with zipfile.ZipFile(file_path, "r") as zf:
        
        total_uncompressed = sum(info.file_size for info in zf.infolist())
        if total_uncompressed > MAX_EXTRACTED_SIZE_BYTES:
            raise ValueError(
                f"Extracted size too large: {total_uncompressed / 1024 / 1024:.1f}MB "
                f"(max 500MB). Possible zip bomb detected."
            )

        
        for info in zf.infolist():
            if info.filename.startswith("/") or ".." in info.filename:
                raise ValueError(
                    "ZIP contains unsafe file paths (path traversal detected)."
                )


def extract_zip(file_path: Path, session_dir: Path) -> tuple[str, list[FileEntry]]:
    """
    Extract ZIP file into session directory and return repo name + file entries.
    Handles single-root-folder ZIPs by flattening the structure.
    """
    validate_zip_file(file_path)

    repo_dir = session_dir / "repo"

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
    return repo_name, files
