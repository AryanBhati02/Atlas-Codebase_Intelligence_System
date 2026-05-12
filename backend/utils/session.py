import re
import uuid
import time
import shutil
import logging
from pathlib import Path

from config import SESSIONS_DIR, SESSION_LIFETIME_HOURS

logger = logging.getLogger("codebase-intel.session")

_SESSION_ID_PATTERN = re.compile(r'^[a-f0-9]{12}$')

def validate_session_id(session_id: str) -> bool:
    return bool(_SESSION_ID_PATTERN.match(session_id))

def create_session() -> tuple[str, Path]:
    session_id = uuid.uuid4().hex[:12]
    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "repo").mkdir(exist_ok=True)
    
    (session_dir / ".created_at").write_text(str(time.time()), encoding="utf-8")
    logger.info(f"Created session {session_id}")
    return session_id, session_dir

def get_session_dir(session_id: str) -> Path:
    if not validate_session_id(session_id):
        raise FileNotFoundError(f"Invalid session ID: {session_id}")
    session_dir = SESSIONS_DIR / session_id
    if not session_dir.exists():
        raise FileNotFoundError(f"Session {session_id} not found")
    return session_dir

def cleanup_session(session_id: str) -> None:
    session_dir = SESSIONS_DIR / session_id
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)
        logger.info(f"Cleaned up session {session_id}")

def cleanup_expired_sessions() -> int:
    if not SESSIONS_DIR.exists():
        return 0

    max_age_seconds = SESSION_LIFETIME_HOURS * 3600
    now = time.time()
    cleaned = 0

    for session_dir in SESSIONS_DIR.iterdir():
        if not session_dir.is_dir():
            continue
        try:
            created_file = session_dir / ".created_at"
            if created_file.exists():
                created_at = float(created_file.read_text(encoding="utf-8").strip())
            else:
                
                created_at = session_dir.stat().st_mtime

            if now - created_at > max_age_seconds:
                shutil.rmtree(session_dir, ignore_errors=True)
                cleaned += 1
        except Exception as e:
            logger.warning(f"Could not check session age for {session_dir.name}: {e}")

    return cleaned
