import asyncio
import logging
import shutil
import subprocess
from pathlib import Path

from core.ingest.file_filter import scan_directory
from models.schemas import FileEntry

logger = logging.getLogger("codebase-intel.ingest.git")


class GitIngestError(Exception):

    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.error_code = error_code


def validate_github_url(url: str) -> bool:
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
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return parts[-1] if parts else "unknown"


def _do_clone_sync(url: str, repo_dir: Path, depth: int = 1) -> None:
    abs_repo_dir = repo_dir.resolve()

    target_exists = abs_repo_dir.exists()
    target_contents = list(abs_repo_dir.iterdir()) if target_exists else []
    logger.info(
        "[CLONE_PROCESS_START] url=%s  target=%s  "
        "target_exists=%s  target_file_count=%d",
        url, abs_repo_dir, target_exists, len(target_contents),
    )

    if target_exists:
        logger.info(
            "[CLONE_PROCESS_START] Removing existing target dir before clone: %s",
            abs_repo_dir,
        )
        shutil.rmtree(abs_repo_dir)

    cmd = [
        "git", "clone",
        f"--depth={depth}",
        "--single-branch",
        "--no-tags",
        url,
        str(abs_repo_dir),
    ]
    logger.info("[CLONE_PROCESS_START] cmd=%s", " ".join(cmd))

    proc = None
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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

    stdout_text = proc.stdout.decode("utf-8", errors="replace").strip()
    stderr_text = proc.stderr.decode("utf-8", errors="replace").strip()

    logger.info("[CLONE_PROCESS_EXIT] returncode=%d", proc.returncode)
    if stdout_text:
        logger.info("[CLONE_STDOUT] %s", stdout_text[:2000])
    if stderr_text:
        logger.info("[CLONE_STDERR] %s", stderr_text[:2000])

    if proc.returncode != 0:
        lower = stderr_text.lower()
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
            f"Git clone failed (exit {proc.returncode}): {stderr_text[:300]}",
            error_code="CLONE_FAILED",
        )

    # Verify the clone actually produced files before returning.
    if not abs_repo_dir.exists():
        raise GitIngestError(
            f"Clone exit 0 but target dir missing: {abs_repo_dir}",
            error_code="CLONE_EMPTY",
        )

    cloned_files = [p for p in abs_repo_dir.rglob("*") if p.is_file()]
    file_count = len(cloned_files)
    logger.info(
        "[CLONE_PROCESS_EXIT] Clone verified: %d files in %s",
        file_count, abs_repo_dir,
    )

    if file_count == 0:
        raise GitIngestError(
            f"Clone exit 0 but repository is empty at {abs_repo_dir}. "
            "The repository may contain no files.",
            error_code="CLONE_EMPTY",
        )


async def clone_repository_async(
    url: str,
    session_dir: Path,
    depth: int = 1,
) -> tuple[str, list[FileEntry]]:
    url = url.strip()
    if not validate_github_url(url):
        raise ValueError(
            "Invalid GitHub URL. Expected format: https://github.com/owner/repo"
        )

    repo_name = extract_repo_name(url)
    repo_dir = session_dir / "repo"

    await asyncio.to_thread(_do_clone_sync, url, repo_dir, depth)

    files = await asyncio.to_thread(scan_directory, repo_dir)
    return repo_name, files


def clone_repository(url: str, session_dir: Path) -> tuple[str, list[FileEntry]]:
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
