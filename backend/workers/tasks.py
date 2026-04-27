"""
Celery task definitions for background analysis pipeline.

Each task is a thin synchronous wrapper that calls asyncio.run() to drive
the async pipeline in core/pipeline.py. Using asyncio.run() inside a Celery
worker is safe: the worker thread has no running event loop, so asyncio.run()
creates a fresh one for the duration of the task.

To register tasks, the worker must be started from the backend/ directory:
    celery -A workers.celery_app worker --loglevel=info --concurrency=2
"""

import asyncio
import logging

from workers.celery_app import celery_app

logger = logging.getLogger("codebase-intel.tasks")


@celery_app.task(
    name="tasks.run_analysis_pipeline",
    max_retries=0,           # Do not retry — analysis errors need user action.
    acks_late=True,          # Ack only after success so crash = re-queue.
    time_limit=660,          # Hard kill after 11 min (matches ANALYSIS_TIMEOUT + buffer).
    soft_time_limit=600,     # Raise SoftTimeLimitExceeded at 10 min for graceful abort.
)
def run_analysis_pipeline_task(session_id: str, source_type: str) -> dict:
    """
    Run the full analysis pipeline for a session.

    Args:
        session_id:  12-char hex session identifier.
        source_type: "github" | "zip" — informational, used for logging only.

    Returns a status dict that Celery stores in the result backend.
    Errors are reported via ProgressStore (disk), not via Celery result.
    """
    from pathlib import Path
    from workers.celery_app import _BACKEND_DIR
    import sys
    import os

    backend_path = os.path.abspath(_BACKEND_DIR)

    if backend_path not in map(os.path.abspath, sys.path):
        sys.path.insert(0, backend_path)
    from config import SESSIONS_DIR
    from core.session_progress import progress_store
    from core.pipeline import PipelineError, run_analysis_pipeline

    session_dir = Path(SESSIONS_DIR) / session_id
    log = logging.getLogger(f"codebase-intel.tasks.{session_id[:8]}")
    log.info(f"Task started — source_type={source_type}")

    try:
        asyncio.run(run_analysis_pipeline(session_id, session_dir))
        log.info("Task completed successfully")
        return {"status": "done", "session_id": session_id}

    except PipelineError as exc:
        log.error(f"Pipeline error [{exc.error_code}]: {exc}")
        progress_store.update_sync(
            session_id,
            status="error",
            error_message=f"[{exc.error_code}] {exc}",
        )
        return {"status": "error", "error_code": exc.error_code, "session_id": session_id}

    except TimeoutError as exc:
        log.error(f"Timeout: {exc}")
        progress_store.update_sync(
            session_id,
            status="error",
            error_message=str(exc),
        )
        return {"status": "error", "error_code": "TIMEOUT", "session_id": session_id}

    except MemoryError:
        log.error("Out of memory during analysis")
        progress_store.update_sync(
            session_id,
            status="error",
            error_message=(
                "Out of memory. Try a smaller repository or increase the "
                "worker's memory limit."
            ),
        )
        return {"status": "error", "error_code": "OOM", "session_id": session_id}

    except Exception as exc:  # noqa: BLE001
        # Catch-all: never let an unhandled exception leave the task without
        # updating the progress store — otherwise the frontend polls forever.
        log.error(f"Unexpected task error: {exc}", exc_info=True)
        progress_store.update_sync(
            session_id,
            status="error",
            error_message=str(exc)[:300],
        )
        return {"status": "error", "error_code": "UNKNOWN", "session_id": session_id}
