"""Structured JSON logging for all Atlas backend modules.

Usage:
    from core.logger import get_logger
    logger = get_logger(__name__)
    logger.info("clone finished", extra={"session_id": sid, "duration_ms": 420})
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class _JsonFormatter(logging.Formatter):
    """Emits each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        # Structured fields injected via extra={}
        for field in ("session_id", "duration_ms", "provider", "url", "file_count"):
            val = getattr(record, field, None)
            if val is not None:
                payload[field] = val

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    """Return a JSON-formatted logger.  Each module calls this once at import time."""
    log = logging.getLogger(name)
    if not log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        log.addHandler(handler)
        log.propagate = False
    log.setLevel(logging.INFO)
    return log
