"""
GitHub repository ingestion via shallow git clone.

All cloning is done via subprocess (not GitPython) with:
  --depth=1        →  fetch only the latest commit tree (~10× faster)
  --single-branch  →  skip other branches
  --no-tags        →  skip tag objects

The clone subprocess runs inside asyncio.to_thread() so FastAPI's event
loop is never blocked, even for large repositories.

Post-clone directory scanning respects IGNORED_DIRS / IGNORED_EXTENSIONS
from config.py (node_modules, __pycache__, .git, *.min.js, etc. are
excluded automatically by scan_directory).
"""

import asyncio
import logging
import subprocess
from pathlib import Path

from core.ingest.file_filter import scan_directory
from models.schemas import FileEntry

logger = logging.getLogger("codebase-intel.ingest.git")


class GitIngestError(Exception):
    """Structured clone/ingest error with a machine-readable error_code."""

    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.error_code = error_code


# ── URL helpers ───────────────────────────────────────────────────────────────

def validate_github_url(url: str) -> bool:
    """Return True only for well-formed github.com repository URLs."""
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


def extract_repo_name(url: str) -> str:
    """Return 'owner/repo' from any github.com clone URL."""
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return parts[-1] if parts else "unknown"


# ── Core clone logic ──────────────────────────────────────────────────────────

def _do_clone_sync(url: str, repo_dir: Path, depth: int = 1) -> None:
    """
    Execute git clone synchronously.  Intended to run inside asyncio.to_thread().

    Raises GitIngestError with a specific error_code on every failure path
    so that callers can build structured HTTP responses without inspecting
    raw error strings.
    """
    cmd = [
        "git", "clone",
        f"--depth={depth}",
        "--single-branch",
        "--no-tags",
        url,
        str(repo_dir),
    ]
    logger.info(f"Cloning {url} (depth={depth})")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise GitIngestError(
            f"Git clone timed out after 120 s for {url}. "
            "Try a smaller or less active repository.",
            error_code="CLONE_TIMEOUT",
        )
    except FileNotFoundError:
        raise GitIngestError(
            "Git is not installed or not found in PATH. "
            "Install Git (https://git-scm.com) and restart the server.",
            error_code="GIT_NOT_INSTALLED",
        )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        lower = stderr.lower()
        if "not found" in lower or "repository not found" in lower or "404" in lower:
            raise GitIngestError(
                f"Repository not found: {url}. "
                "Check the URL and ensure the repository is public.",
                error_code="REPO_NOT_FOUND",
            )
        if "authentication failed" in lower or "could not read username" in lower:
            raise GitIngestError(
                f"Authentication failed for {url}. "
                "Only public repositories are supported.",
                error_code="AUTH_REQUIRED",
            )
        if "unable to connect" in lower or "could not resolve host" in lower:
            raise GitIngestError(
                "Cannot reach GitHub. Check your internet connection.",
                error_code="NETWORK_ERROR",
            )
        raise GitIngestError(
            f"Git clone failed (exit {result.returncode}): {stderr[:300]}",
            error_code="CLONE_FAILED",
        )

    logger.info(f"Clone complete → {repo_dir}")


# ── Public async API ──────────────────────────────────────────────────────────

async def clone_repository_async(
    url: str,
    session_dir: Path,
    depth: int = 1,
) -> tuple[str, list[FileEntry]]:
    """
    Clone a GitHub repository (non-blocking) and return (repo_name, file_entries).

    Runs the blocking git subprocess in a thread via asyncio.to_thread() so the
    FastAPI event loop remains responsive during the clone.

    Raises:
        ValueError        — URL failed validation.
        GitIngestError    — clone failed with a structured error_code.
    """
    url = url.strip()
    if not validate_github_url(url):
        raise ValueError(
            "Invalid GitHub URL. Expected format: https://github.com/owner/repo"
        )

    repo_name = extract_repo_name(url)
    repo_dir = session_dir / "repo"

    await asyncio.to_thread(_do_clone_sync, url, repo_dir, depth)

    # scan_directory filters out node_modules, __pycache__, .git, *.min.js, etc.
    # via IGNORED_DIRS and IGNORED_EXTENSIONS in config.py.
    files = await asyncio.to_thread(scan_directory, repo_dir)
    return repo_name, files


# ── Sync fallback (tests / backward compat) ───────────────────────────────────

def clone_repository(url: str, session_dir: Path) -> tuple[str, list[FileEntry]]:
    """Synchronous clone. Use clone_repository_async in production."""
    url = url.strip()
    if not validate_github_url(url):
        raise ValueError(
            "Invalid GitHub URL. Expected format: https://github.com/owner/repo"
        )

    repo_name = extract_repo_name(url)
    repo_dir = session_dir / "repo"
    _do_clone_sync(url, repo_dir, depth=1)
    files = scan_directory(repo_dir)
    return repo_name, files
