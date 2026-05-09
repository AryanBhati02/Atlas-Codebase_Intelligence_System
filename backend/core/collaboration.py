
import json
import logging
import uuid
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger("codebase-intel.collab")

def _comments_path(session_dir: Path) -> Path:
    return session_dir / "comments.json"

def _load_comments(session_dir: Path) -> list[dict]:
    path = _comments_path(session_dir)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load comments: {e}")
            return []
    return []

def _save_comments(session_dir: Path, comments: list[dict]) -> None:
    path = _comments_path(session_dir)
    path.write_text(json.dumps(comments, default=str, indent=2), encoding="utf-8")

def add_comment(
    session_dir: Path,
    session_id: str,
    target_type: str,
    target_id: str,
    message: str,
    author: str = "Anonymous",
    parent_id: str | None = None,
) -> dict:
    comments = _load_comments(session_dir)
    
    comment = {
        "id": uuid.uuid4().hex[:12],
        "session_id": session_id,
        "target_type": target_type,
        "target_id": target_id,
        "message": message,
        "author": author,
        "parent_id": parent_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "resolved": False,
    }
    
    comments.append(comment)
    _save_comments(session_dir, comments)
    return comment

def get_comments(
    session_dir: Path,
    session_id: str,
    target_id: str | None = None,
    target_type: str | None = None,
) -> list[dict]:
    comments = _load_comments(session_dir)
    
    result = [c for c in comments if c.get("session_id") == session_id]
    
    if target_id:
        result = [c for c in result if c.get("target_id") == target_id]
    if target_type:
        result = [c for c in result if c.get("target_type") == target_type]
    
    result.sort(key=lambda c: c.get("created_at", ""), reverse=True)
    return result

def resolve_comment(session_dir: Path, comment_id: str) -> dict | None:
    comments = _load_comments(session_dir)
    
    for c in comments:
        if c.get("id") == comment_id:
            c["resolved"] = not c.get("resolved", False)
            _save_comments(session_dir, comments)
            return c
    
    return None

def delete_comment(session_dir: Path, comment_id: str) -> bool:
    comments = _load_comments(session_dir)
    original_len = len(comments)
    comments = [c for c in comments if c.get("id") != comment_id]
    
    if len(comments) < original_len:
        _save_comments(session_dir, comments)
        return True
    return False

def get_comment_counts(session_dir: Path, session_id: str) -> dict[str, int]:
    comments = _load_comments(session_dir)
    counts: dict[str, int] = {}
    
    for c in comments:
        if c.get("session_id") == session_id:
            tid = c.get("target_id", "")
            counts[tid] = counts.get(tid, 0) + 1
    
    return counts

def generate_share_token(session_dir: Path, session_id: str) -> str:
    share_path = session_dir / "share_token.json"
    
    if share_path.exists():
        try:
            data = json.loads(share_path.read_text(encoding="utf-8"))
            return data.get("token", "")
        except Exception:
            pass
    
    token = uuid.uuid4().hex[:16]
    share_data = {
        "token": token,
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
    }
    share_path.write_text(json.dumps(share_data), encoding="utf-8")
    return token
