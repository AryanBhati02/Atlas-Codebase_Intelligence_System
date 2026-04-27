"""SQLite-backed AI response cache.

Uses file content SHA-256 hash to auto-invalidate stale entries.
One database per session stored at session_dir/ai_cache.db.
"""

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("codebase-intel.cache")


def _get_db(session_dir: Path) -> sqlite3.Connection:
    db_path = session_dir / "ai_cache.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_cache (
            key TEXT PRIMARY KEY,
            file_hash TEXT NOT NULL,
            response TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def hash_content(content: str) -> str:
    """SHA-256 hash of file content for cache invalidation."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def get_cached(session_dir: Path, key: str, current_hash: str) -> dict | None:
    """Return cached response if hash matches, else None."""
    try:
        conn = _get_db(session_dir)
        row = conn.execute(
            "SELECT file_hash, response FROM ai_cache WHERE key = ?", (key,)
        ).fetchone()
        conn.close()

        if row and row[0] == current_hash:
            return json.loads(row[1])
    except Exception as e:
        logger.warning(f"Cache read failed for key '{key}': {e}")
    return None


def set_cached(session_dir: Path, key: str, file_hash: str, response: dict) -> None:
    """Upsert a cache entry."""
    try:
        conn = _get_db(session_dir)
        conn.execute(
            """INSERT OR REPLACE INTO ai_cache (key, file_hash, response, created_at)
               VALUES (?, ?, ?, ?)""",
            (key, file_hash, json.dumps(response), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Cache write failed for key '{key}': {e}")
