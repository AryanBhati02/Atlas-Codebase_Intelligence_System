"""
GitHub repository ingestion via git clone.
Validates URLs, clones into session directory, and scans the result.
Supports async cloning and configurable depth.
"""

import asyncio
import subprocess
from pathlib import Path

from models.schemas import FileEntry
from core.ingest.file_filter import scan_directory


def extract_repo_name(url: str) -> str:
    """Extract 'owner/repo' from a GitHub URL."""
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return parts[-1] if parts else "unknown"


def validate_github_url(url: str) -> bool:
    """Validate that the URL points to a GitHub repository."""
    url = url.strip().lower()
    valid_prefixes = (
        "https://github.com/",
        "http://github.com/",
        "https://www.github.com/",
    )
    if not any(url.startswith(p) for p in valid_prefixes):
        return False
    
    path_parts = url.split("github.com/")[-1].strip("/").split("/")
    return len(path_parts) >= 2 and all(part for part in path_parts[:2])


async def clone_repository_async(url: str, session_dir: Path, depth: int = 1) -> tuple[str, list[FileEntry]]:
    """
    Clone a GitHub repository (non-blocking) and return repo name + file entries.
    Uses --depth=1 by default for speed. Deeper history loaded on-demand by git timeline.
    """
    url = url.strip()

    if not validate_github_url(url):
        raise ValueError(
            "Invalid GitHub URL. Expected format: https://github.com/owner/repo"
        )

    repo_name = extract_repo_name(url)
    repo_dir = session_dir / "repo"

    def _do_clone():
        result = subprocess.run(
            ["git", "clone", f"--depth={depth}", "--single-branch", "--no-tags", url, str(repo_dir)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip()
            if "not found" in error_msg.lower() or "404" in error_msg:
                raise RuntimeError(f"Repository not found: {url}")
            raise RuntimeError(f"Git clone failed: {error_msg}")

    try:
        await asyncio.to_thread(_do_clone)
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "Git clone timed out (120s limit). Try a smaller repository."
        )
    except FileNotFoundError:
        raise RuntimeError(
            "Git is not installed or not in PATH. Install Git and try again."
        )

    files = scan_directory(repo_dir)
    return repo_name, files


def clone_repository(url: str, session_dir: Path) -> tuple[str, list[FileEntry]]:
    """Sync wrapper for backward compatibility."""
    url = url.strip()

    if not validate_github_url(url):
        raise ValueError(
            "Invalid GitHub URL. Expected format: https://github.com/owner/repo"
        )

    repo_name = extract_repo_name(url)
    repo_dir = session_dir / "repo"

    try:
        result = subprocess.run(
            ["git", "clone", "--depth=1", "--single-branch", "--no-tags", url, str(repo_dir)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip()
            if "not found" in error_msg.lower() or "404" in error_msg:
                raise RuntimeError(f"Repository not found: {url}")
            raise RuntimeError(f"Git clone failed: {error_msg}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "Git clone timed out (120s limit). Try a smaller repository."
        )
    except FileNotFoundError:
        raise RuntimeError(
            "Git is not installed or not in PATH. Install Git and try again."
        )

    files = scan_directory(repo_dir)
    return repo_name, files
