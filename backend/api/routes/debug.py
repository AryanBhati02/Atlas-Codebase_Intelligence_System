"""
GET /api/debug/session/{session_id}

Returns diagnostic information about a session directory so operators can
verify that:
  1. The session directory exists and is on the correct volume mount.
  2. The repo/ sub-directory was populated by git clone / ZIP extract.
  3. The .ingest_ready sentinel was written by the ingest route.
  4. The .ingest_failed sentinel was NOT written (i.e. no ingest error).

This endpoint is intentionally read-only and has no side-effects.
"""
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from config import SESSIONS_DIR

logger = logging.getLogger("codebase-intel.routes.debug")

router = APIRouter(prefix="/debug", tags=["Debug"])


@router.get("/session/{session_id}")
async def debug_session(session_id: str):
    """
    Returns a JSON snapshot of the session directory state.
    Useful for diagnosing path / volume-mount / sentinel issues in Docker.
    """
    session_dir: Path = SESSIONS_DIR / session_id

    session_exists = session_dir.exists() and session_dir.is_dir()
    if not session_exists:

        return {
            "session_id": session_id,
            "sessions_dir": str(SESSIONS_DIR.resolve()),
            "session_exists": False,
            "repo_exists": False,
            "repo_file_count": 0,
            "ready_exists": False,
            "failed_exists": False,
            "failed_reason": None,
            "repo_absolute_path": str((session_dir / "repo").resolve()),
            "ready_absolute_path": str((session_dir / ".ingest_ready").resolve()),
            "failed_absolute_path": str((session_dir / ".ingest_failed").resolve()),
            "meta_exists": False,
            "file_entries_exist": False,
        }

    repo_dir = session_dir / "repo"
    ready_file = session_dir / ".ingest_ready"
    failed_file = session_dir / ".ingest_failed"

    repo_exists = repo_dir.exists() and repo_dir.is_dir()
    repo_file_count = 0
    if repo_exists:
        try:
            repo_file_count = sum(1 for _ in repo_dir.rglob("*") if _.is_file())
        except Exception:
            repo_file_count = -1

    failed_reason: str | None = None
    if failed_file.exists():
        try:
            failed_reason = failed_file.read_text(encoding="utf-8").strip()
        except Exception:
            failed_reason = "<unreadable>"

    return {
        "session_id": session_id,
        "sessions_dir": str(SESSIONS_DIR.resolve()),
        "session_exists": True,
        "repo_exists": repo_exists,
        "repo_file_count": repo_file_count,
        "ready_exists": ready_file.exists(),
        "failed_exists": failed_file.exists(),
        "failed_reason": failed_reason,
        "repo_absolute_path": str(repo_dir.resolve()),
        "ready_absolute_path": str(ready_file.resolve()),
        "failed_absolute_path": str(failed_file.resolve()),
        "meta_exists": (session_dir / "meta.json").exists(),
        "file_entries_exist": (session_dir / "file_entries.json").exists(),
    }
