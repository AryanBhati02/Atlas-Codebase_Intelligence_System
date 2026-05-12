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
    "parsing", "scoring", "graph", "saving", "function_graph", "done", "error",
})

@dataclass
class ProgressEntry:
    status: str = "queued"
    total_files: int = 0
    parsed_files: int = 0
    partial_nodes: list = field(default_factory=list)
    partial_edges: list = field(default_factory=list)
    function_count: int = 0
    error_message: str = ""

    def as_legacy_dict(self) -> dict:
        return {
            "stage": self.status,
            "current": self.parsed_files,
            "total": self.total_files,
            "done": self.status == "done",
            "function_count": self.function_count,
            "error": self.error_message or None,
        }

    def as_rich_dict(self) -> dict:
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
            "function_count": self.function_count,
            "error": self.error_message or None,
        }

class ProgressStore:

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def update_sync(self, session_id: str, **kwargs) -> None:
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
        return self._read_disk(session_id)

    def clear_sync(self, session_id: str) -> None:
        with self._lock:
            self._delete_disk(session_id)

    async def update(self, session_id: str, **kwargs) -> None:
        self.update_sync(session_id, **kwargs)

    async def get(self, session_id: str) -> Optional[ProgressEntry]:
        return self.get_sync(session_id)

    async def clear(self, session_id: str) -> None:
        self.clear_sync(session_id)

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

progress_store = ProgressStore()
