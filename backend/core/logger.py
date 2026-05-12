import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

class _JsonFormatter(logging.Formatter):

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
                                                 
        for field in ("session_id", "duration_ms", "provider", "url", "file_count"):
            val = getattr(record, field, None)
            if val is not None:
                payload[field] = val

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)

def get_logger(name: str) -> logging.Logger:
    log = logging.getLogger(name)
    if not log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        log.addHandler(handler)
        log.propagate = False
    log.setLevel(logging.INFO)
    return log
