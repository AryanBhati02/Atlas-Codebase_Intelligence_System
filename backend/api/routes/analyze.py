import asyncio
import json
import logging
import time
import threading
from pathlib import Path
from typing import Protocol, cast

from fastapi import APIRouter, HTTPException

from core.session_progress import progress_store
from models.schemas import (
    AnalyzeResponse,
    GraphData,
    GraphEdge,
    GraphNode,
    ParsedFile,
)
from utils.session import get_session_dir

logger = logging.getLogger("codebase-intel.routes.analyze")

router = APIRouter(prefix="/analyze", tags=["Analyze"])

# Sentinel files written by the ingest route — same constants as tasks.py
_INGEST_READY = ".ingest_ready"
_INGEST_FAILED = ".ingest_failed"
_READY_WAIT_SECS = 30
_READY_POLL_INTERVAL = 1


class CeleryTask(Protocol):
    def delay(self, *args: object, **kwargs: object) -> object:
        ...


def _wait_for_ingest_sentinel(session_id: str, session_dir: Path) -> bool:
    """
    Block (in a thread) until .ingest_ready appears or .ingest_failed is found.
    Returns True if ready, False if failed/timed-out.
    """
    log = logging.getLogger(f"codebase-intel.thread.{session_id[:8]}")
    ready_file = session_dir / _INGEST_READY
    failed_file = session_dir / _INGEST_FAILED

    log.info(f"[INGEST_WAIT] Thread fallback waiting for sentinel {ready_file}")
    for i in range(_READY_WAIT_SECS):
        if failed_file.exists():
            reason = failed_file.read_text(encoding="utf-8").strip()
            log.error(f"[INGEST_FAILED] Ingestion failed before thread pipeline: {reason}")
            progress_store.update_sync(
                session_id,
                status="error",
                error_message=f"Ingestion failed before analysis could start: {reason}",
            )
            return False
        if ready_file.exists():
            log.info(f"[INGEST_READY] Sentinel found after {i}s — starting thread pipeline")
            return True
        time.sleep(_READY_POLL_INTERVAL)

    log.error(f"[INGEST_TIMEOUT] Repo not ready after {_READY_WAIT_SECS}s (thread)")
    progress_store.update_sync(
        session_id,
        status="error",
        error_message=(
            f"Ingestion timed out — repository was not ready after "
            f"{_READY_WAIT_SECS}s. Please re-ingest the repository."
        ),
    )
    return False


def _run_pipeline_in_thread(session_id: str, session_dir: Path) -> None:
    from core.pipeline import PipelineError, run_analysis_pipeline

    log = logging.getLogger(f"codebase-intel.thread.{session_id[:8]}")
    log.info("Starting pipeline in thread fallback mode")

    if not _wait_for_ingest_sentinel(session_id, session_dir):
        return

    try:
        asyncio.run(run_analysis_pipeline(session_id, session_dir))

    except PipelineError as exc:
        log.error(f"Pipeline error [{exc.error_code}]: {exc}")
        progress_store.update_sync(
            session_id,
            status="error",
            error_message=f"[{exc.error_code}] {exc}",
        )
    except TimeoutError as exc:
        log.error(f"Timeout: {exc}")
        progress_store.update_sync(session_id, status="error", error_message=str(exc))
    except MemoryError:
        log.error("OOM during analysis")
        progress_store.update_sync(
            session_id,
            status="error",
            error_message="Out of memory. Try a smaller repository.",
        )
    except Exception as exc:
        log.error(f"Unexpected error: {exc}", exc_info=True)
        progress_store.update_sync(
            session_id,
            status="error",
            error_message=str(exc)[:300],
        )

@router.post("/start/{session_id}")
async def start_analysis(session_id: str):
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    if (session_dir / "parsed.json").exists() and (session_dir / "graph.json").exists():
        progress_store.update_sync(session_id, status="done", parsed_files=1, total_files=1)
        logger.info(f"[{session_id}] Analysis already complete; serving from cache")
        return {"status": "cached", "session_id": session_id}

    current = progress_store.get_sync(session_id)
    if current and current.status not in ("done", "error", "queued", ""):
        logger.info(f"[{session_id}] Pipeline already running (status={current.status})")
        return {"status": "running", "session_id": session_id}

    source_type = "unknown"
    meta_path = session_dir / "meta.json"
    if meta_path.exists():
        try:
            source_type = json.loads(meta_path.read_text(encoding="utf-8")).get(
                "source_type", "unknown"
            )
        except Exception:
            pass

    progress_store.update_sync(session_id, status="queued")

    celery_ok = False
    try:
        from workers.tasks import run_analysis_pipeline_task

        cast(CeleryTask, run_analysis_pipeline_task).delay(session_id, source_type)
        celery_ok = True
        logger.info(f"[{session_id}] Dispatched to Celery (source_type={source_type})")
    except ImportError:
        logger.warning(f"[{session_id}] Celery workers package not importable; using thread")
    except Exception as exc:                
                                                                            
        logger.warning(
            f"[{session_id}] Celery unavailable ({type(exc).__name__}: {exc}); "
            "using thread fallback"
        )

    if not celery_ok:
        thread = threading.Thread(
            target=_run_pipeline_in_thread,
            args=(session_id, session_dir),
            daemon=True,
            name=f"pipeline-{session_id[:8]}",
        )
        thread.start()

    return {
        "status": "queued" if celery_ok else "started",
        "session_id": session_id,
    }

@router.get("/progress/{session_id}")
async def get_progress(session_id: str):
    entry = progress_store.get_sync(session_id)

    if entry is None:
        return {
            "stage": "pending",
            "current": 0,
            "total": 0,
            "done": False,
            "error": None,
        }

    return entry.as_legacy_dict()

@router.post("/{session_id}", response_model=AnalyzeResponse)
async def analyze_session(session_id: str):
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    parsed_path = session_dir / "parsed.json"
    graph_path = session_dir / "graph.json"

    if not parsed_path.exists() or not graph_path.exists():
        raise HTTPException(
            status_code=425,
            detail="Analysis not complete yet. Poll /analyze/progress/{session_id}.",
        )

    try:
        parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
        graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error(f"[{session_id}] Failed to read analysis results: {exc}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Analysis results are corrupted.",
                "error_code": "RESULTS_CORRUPT",
                "session_id": session_id,
            },
        )

    repo_name = session_id
    meta_path = session_dir / "meta.json"
    if meta_path.exists():
        try:
            repo_name = json.loads(
                meta_path.read_text(encoding="utf-8")
            ).get("repo_name", session_id)
        except Exception:
            pass

    return AnalyzeResponse(
        session_id=session_id,
        repo_name=repo_name,
        total_files=len(parsed),
        parsed_files=[ParsedFile(**f) for f in parsed],
        graph=GraphData(
            nodes=[GraphNode(**n) for n in graph_data["nodes"]],
            edges=[GraphEdge(**e) for e in graph_data["edges"]],
        ),
    )

@router.get("/graph/{session_id}", response_model=GraphData)
async def get_graph(session_id: str):
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    graph_path = session_dir / "graph.json"
    if not graph_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Graph not built yet. Run /analyze/start/{session_id} first.",
        )

    try:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error(f"[{session_id}] Failed to read graph.json: {exc}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Graph data is corrupted.",
                "error_code": "GRAPH_CORRUPT",
                "session_id": session_id,
            },
        )

    return GraphData(
        nodes=[GraphNode(**n) for n in data["nodes"]],
        edges=[GraphEdge(**e) for e in data["edges"]],
    )
