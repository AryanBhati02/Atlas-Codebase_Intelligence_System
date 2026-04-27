"""
ProgressStore — thread-safe, disk-backed progress tracking for analysis sessions.

Design rationale
────────────────
Analysis pipelines run either in a Celery worker process or a daemon thread.
FastAPI's polling endpoint runs in the main async event loop. These three
contexts cannot share in-memory state directly.

Solution: disk is the source of truth.

  Writer path (Celery worker / thread):
      progress_store.update_sync(session_id, status="parsing", ...)
      → acquires threading.Lock → reads progress.json → merges kwargs → writes progress.json

  Reader path (FastAPI async endpoint):
      progress_store.get_sync(session_id)
      → reads progress.json from disk

threading.Lock is used instead of asyncio.Lock because:
  1. It works identically in sync (Celery) and async (FastAPI) contexts.
  2. asyncio.Lock is bound to an event loop, which breaks when called
     from a Celery worker's asyncio.run() context vs. the FastAPI loop.
  3. Disk writes for a small JSON file take < 1 ms — brief lock holding
     is acceptable even inside an async handler.
"""

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from config import SESSIONS_DIR

logger = logging.getLogger("codebase-intel.progress")

_VALID_STATUSES = frozenset({
    "queued", "cloning", "extracting", "scanning",
    "parsing", "scoring", "graph", "saving", "done", "error",
})


@dataclass
class ProgressEntry:
    status: str = "queued"
    total_files: int = 0
    parsed_files: int = 0
    partial_nodes: list = field(default_factory=list)
    partial_edges: list = field(default_factory=list)
    error_message: str = ""

    def as_legacy_dict(self) -> dict:
        """Map to the format the existing frontend polling expects."""
        return {
            "stage": self.status,
            "current": self.parsed_files,
            "total": self.total_files,
            "done": self.status == "done",
            "error": self.error_message or None,
        }

    def as_rich_dict(self) -> dict:
        """Full format for the /api/progress/{session_id} endpoint."""
        total = self.total_files or 1
        if self.status == "done":
            progress = 1.0
        elif self.status == "error":
            progress = 0.0
        else:
            progress = round(min(self.parsed_files / total, 0.99), 3)

        return {
            "progress": progress,
            "files_done": self.parsed_files,
            "total_files": self.total_files,
            "status": self.status,
            "partial_nodes": self.partial_nodes,
            "partial_edges": self.partial_edges,
            "error": self.error_message or None,
        }


class ProgressStore:
    """
    Disk-backed progress store. Thread-safe via threading.Lock.

    All public methods are intentionally non-async so they can be called
    from Celery tasks, daemon threads, and async route handlers without
    event-loop concerns.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def update_sync(self, session_id: str, **kwargs) -> None:
        """
        Atomically update one or more fields of a session's progress entry.
        Creates the entry if it does not exist yet.
        Safe to call from Celery tasks, daemon threads, and async handlers.
        """
        if "status" in kwargs and kwargs["status"] not in _VALID_STATUSES:
            logger.warning(
                f"Unknown status '{kwargs['status']}' for {session_id}; ignoring"
            )
            kwargs.pop("status")

        with self._lock:
            current = self._read_disk(session_id) or ProgressEntry()
            for key, value in kwargs.items():
                if hasattr(current, key):
                    setattr(current, key, value)
                else:
                    logger.debug(f"ProgressEntry has no field '{key}'; skipping")
            self._write_disk(session_id, current)

    def get_sync(self, session_id: str) -> Optional[ProgressEntry]:
        """
        Read the current progress entry for a session.
        Returns None if no progress has been recorded yet.
        """
        return self._read_disk(session_id)

    def clear_sync(self, session_id: str) -> None:
        """Remove the progress file for a session (e.g., on reset)."""
        with self._lock:
            self._delete_disk(session_id)

    # Async shims — same semantics, callable with `await` from route handlers.
    async def update(self, session_id: str, **kwargs) -> None:
        self.update_sync(session_id, **kwargs)

    async def get(self, session_id: str) -> Optional[ProgressEntry]:
        return self.get_sync(session_id)

    async def clear(self, session_id: str) -> None:
        self.clear_sync(session_id)

    # ── Disk I/O (private) ────────────────────────────────────────────────────

    def _progress_path(self, session_id: str) -> Path:
        return SESSIONS_DIR / session_id / "progress.json"

    def _write_disk(self, session_id: str, entry: ProgressEntry) -> None:
        path = self._progress_path(session_id)
        if not path.parent.exists():
            logger.debug(f"Session dir missing for {session_id}; skipping progress write")
            return
        try:
            path.write_text(json.dumps(asdict(entry)), encoding="utf-8")
        except OSError as exc:
            logger.warning(f"Progress write failed for {session_id}: {exc}")

    def _read_disk(self, session_id: str) -> Optional[ProgressEntry]:
        path = self._progress_path(session_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Tolerate extra/missing keys across schema versions
            valid_keys = set(ProgressEntry.__dataclass_fields__.keys())
            filtered = {k: v for k, v in data.items() if k in valid_keys}
            return ProgressEntry(**filtered)
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.warning(f"Progress read failed for {session_id}: {exc}")
            return None

    def _delete_disk(self, session_id: str) -> None:
        try:
            self._progress_path(session_id).unlink(missing_ok=True)
        except OSError as exc:
            logger.warning(f"Progress delete failed for {session_id}: {exc}")


# Module-level singleton — import this everywhere.
progress_store = ProgressStore()
