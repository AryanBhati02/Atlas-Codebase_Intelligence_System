"""
Analyze routes — starts the parse/graph pipeline and streams live progress.

POST /analyze/start/{session_id}
    Dispatches the pipeline as a Celery task (primary path).
    Falls back to a daemon thread if Celery/Redis is unreachable.
    Returns immediately with {"status": "queued"|"started"|"cached"}.

GET /analyze/progress/{session_id}
    Polling endpoint. Returns the legacy format the frontend already expects:
    {"stage", "current", "total", "done", "error"}

POST /analyze/{session_id}
    Returns cached analysis results once done=true.

GET /analyze/graph/{session_id}
    Returns the dependency graph only.
"""

import asyncio
import json
import logging
import threading
from pathlib import Path

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


# ── Thread-fallback pipeline runner ──────────────────────────────────────────

def _run_pipeline_in_thread(session_id: str, session_dir: Path) -> None:
    """
    Execute the async pipeline inside a daemon thread via asyncio.run().

    Used only when Celery/Redis is unavailable.  asyncio.run() creates a
    fresh event loop for the thread, so async primitives inside the pipeline
    (Semaphore, gather, to_thread) all work correctly.
    """
    from core.pipeline import PipelineError, run_analysis_pipeline

    log = logging.getLogger(f"codebase-intel.thread.{session_id[:8]}")
    log.info("Starting pipeline in thread fallback mode")

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
    except Exception as exc:  # noqa: BLE001
        log.error(f"Unexpected error: {exc}", exc_info=True)
        progress_store.update_sync(
            session_id,
            status="error",
            error_message=str(exc)[:300],
        )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/start/{session_id}")
async def start_analysis(session_id: str):
    """
    Kick off the analysis pipeline for a session.

    Strategy:
      1. If results already exist on disk → mark done, return "cached".
      2. If a pipeline is already running   → return "running".
      3. Try to dispatch a Celery task      → return "queued".
      4. If Celery is unavailable           → start a daemon thread, return "started".
    """
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Fast-path: results already on disk (e.g. page reload)
    if (session_dir / "parsed.json").exists() and (session_dir / "graph.json").exists():
        progress_store.update_sync(session_id, status="done", parsed_files=1, total_files=1)
        logger.info(f"[{session_id}] Analysis already complete; serving from cache")
        return {"status": "cached", "session_id": session_id}

    # Guard: don't spawn two pipelines for the same session
    current = progress_store.get_sync(session_id)
    if current and current.status not in ("done", "error", "queued", ""):
        logger.info(f"[{session_id}] Pipeline already running (status={current.status})")
        return {"status": "running", "session_id": session_id}

    # Read source_type for logging / task metadata
    source_type = "unknown"
    meta_path = session_dir / "meta.json"
    if meta_path.exists():
        try:
            source_type = json.loads(meta_path.read_text(encoding="utf-8")).get(
                "source_type", "unknown"
            )
        except Exception:
            pass

    # Mark as queued before dispatch so the progress endpoint immediately
    # returns a non-None entry.
    progress_store.update_sync(session_id, status="queued")

    # ── Primary: Celery task ──────────────────────────────────────────────
    celery_ok = False
    try:
        from workers.tasks import run_analysis_pipeline_task

        run_analysis_pipeline_task.delay(session_id, source_type)
        celery_ok = True
        logger.info(f"[{session_id}] Dispatched to Celery (source_type={source_type})")
    except ImportError:
        logger.warning(f"[{session_id}] Celery workers package not importable; using thread")
    except Exception as exc:  # noqa: BLE001
        # Covers kombu.exceptions.OperationalError (Redis unreachable), etc.
        logger.warning(
            f"[{session_id}] Celery unavailable ({type(exc).__name__}: {exc}); "
            "using thread fallback"
        )

    # ── Fallback: daemon thread ───────────────────────────────────────────
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
    """
    Return live pipeline progress in the format the frontend polling expects.

    Format (backward-compatible with the previous threading implementation):
      stage   — current pipeline stage string
      current — number of files parsed so far
      total   — total files to parse
      done    — true when pipeline has finished successfully
      error   — error message string, or null
    """
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
    """Return cached analysis results. Call /start/{session_id} first."""
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
    """Return only the dependency graph (nodes + edges)."""
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
