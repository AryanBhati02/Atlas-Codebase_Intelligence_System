
import asyncio
import logging

from workers.celery_app import celery_app

logger = logging.getLogger("codebase-intel.tasks")

@celery_app.task(
    name="tasks.run_analysis_pipeline",
    max_retries=0,                                                             
    acks_late=True,                                                       
    time_limit=660,                                                                       
    soft_time_limit=600,                                                                
)
def run_analysis_pipeline_task(session_id: str, source_type: str) -> dict:
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

    except Exception as exc:                
                                                                            
        log.error(f"Unexpected task error: {exc}", exc_info=True)
        progress_store.update_sync(
            session_id,
            status="error",
            error_message=str(exc)[:300],
        )
        return {"status": "error", "error_code": "UNKNOWN", "session_id": session_id}
