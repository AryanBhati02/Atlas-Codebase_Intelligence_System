"""Analyze route — triggers parse + graph + score pipeline for a session.
Uses polling-based progress (no SSE) for maximum reliability."""

import json
import asyncio
import threading
from fastapi import APIRouter, HTTPException
from pathlib import Path

from models.schemas import AnalyzeResponse, ParsedFile, GraphNode, GraphEdge, GraphData
from core.parser.parser_service import parse_all_files
from core.scoring.complexity_scorer import score_files
from core.graph.graph_builder import build_graph
from utils.session import get_session_dir

router = APIRouter(prefix="/analyze", tags=["Analyze"])


_progress: dict[str, dict] = {}
_progress_lock = threading.Lock()


def _set_progress(session_id: str, stage: str, current: int, total: int, done=False, error: str | None = None):
    with _progress_lock:
        _progress[session_id] = {
            "stage": stage,
            "current": current,
            "total": total,
            "done": done,
            "error": error,
        }


def _run_pipeline(session_id: str, session_dir: Path):
    """Run the full analysis pipeline in a background thread with timeout guard."""
    import time as _time
    import logging as _logging
    from config import ANALYSIS_TIMEOUT_SECONDS

    log = _logging.getLogger("codebase-intel.pipeline")
    start_time = _time.time()

    def _check_timeout():
        elapsed = _time.time() - start_time
        if elapsed > ANALYSIS_TIMEOUT_SECONDS:
            raise TimeoutError(
                f"Analysis timed out after {elapsed:.0f}s "
                f"(limit: {ANALYSIS_TIMEOUT_SECONDS}s)"
            )

    try:
        _set_progress(session_id, "starting", 0, 0)

        repo_dir = session_dir / "repo"
        if not repo_dir.exists():
            _set_progress(session_id, "error", 0, 0, error="Repository data not found.")
            return

        
        entries_path = session_dir / "file_entries.json"
        if not entries_path.exists():
            from core.ingest.file_filter import scan_directory
            log.info(f"[{session_id}] Scanning directory...")
            file_entries = scan_directory(repo_dir)
            entries_data = [e.model_dump() for e in file_entries]
            entries_path.write_text(json.dumps(entries_data), encoding="utf-8")
        else:
            entries_data = json.loads(entries_path.read_text(encoding="utf-8"))

        total = len(entries_data)
        log.info(f"[{session_id}] Starting pipeline for {total} files")
        _set_progress(session_id, "parsing", 0, total)
        _check_timeout()

        def on_progress(stage: str, current: int, file_total: int):
            _set_progress(session_id, stage, current, file_total)

        
        parsed = parse_all_files(repo_dir, entries_data, on_progress)
        _check_timeout()

        
        _set_progress(session_id, "scoring", 0, 1)
        parsed = score_files(parsed)
        _set_progress(session_id, "scoring", 1, 1)
        _check_timeout()

        
        _set_progress(session_id, "graph", 0, 1)
        graph_data = build_graph(parsed)
        _set_progress(session_id, "graph", 1, 1)
        _check_timeout()

        
        _set_progress(session_id, "saving", 0, 1)
        (session_dir / "parsed.json").write_text(json.dumps(parsed), encoding="utf-8")
        (session_dir / "graph.json").write_text(json.dumps(graph_data), encoding="utf-8")

        elapsed = _time.time() - start_time
        log.info(f"[{session_id}] Pipeline complete: {len(parsed)} files in {elapsed:.1f}s")
        _set_progress(session_id, "done", 1, 1, done=True)

    except MemoryError:
        log.error(f"[{session_id}] Out of memory during analysis")
        _set_progress(session_id, "error", 0, 0,
                      error="Out of memory. Try a smaller repository or increase MAX_FILES_LIMIT.")

    except TimeoutError as e:
        log.error(f"[{session_id}] {e}")
        _set_progress(session_id, "error", 0, 0, error=str(e))

    except Exception as e:
        log.error(f"[{session_id}] Pipeline error: {e}", exc_info=True)
        _set_progress(session_id, "error", 0, 0, error=str(e))



@router.post("/start/{session_id}")
async def start_analysis(session_id: str):
    """Start analysis in background. Returns immediately. Poll /progress/{session_id} for status."""
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    
    if (session_dir / "parsed.json").exists() and (session_dir / "graph.json").exists():
        _set_progress(session_id, "done", 1, 1, done=True)
        return {"status": "cached"}

    
    with _progress_lock:
        existing = _progress.get(session_id)
        if existing and not existing.get("done") and not existing.get("error"):
            return {"status": "running"}

    
    _set_progress(session_id, "starting", 0, 0)
    thread = threading.Thread(
        target=_run_pipeline,
        args=(session_id, session_dir),
        daemon=True,
    )
    thread.start()
    return {"status": "started"}


@router.get("/progress/{session_id}")
async def get_progress(session_id: str):
    """Poll this endpoint for live progress. Returns stage/current/total/done/error."""
    with _progress_lock:
        state = _progress.get(session_id)

    if state is None:
        return {"stage": "pending", "current": 0, "total": 0, "done": False, "error": None}
    return state


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
        raise HTTPException(status_code=425, detail="Analysis not complete yet.")

    parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
    graph_data = json.loads(graph_path.read_text(encoding="utf-8"))

    repo_name = session_id
    ingest_meta = session_dir / "meta.json"
    if ingest_meta.exists():
        meta = json.loads(ingest_meta.read_text(encoding="utf-8"))
        repo_name = meta.get("repo_name", session_id)

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
        raise HTTPException(status_code=404, detail="Run analyze first.")

    data = json.loads(graph_path.read_text(encoding="utf-8"))
    return GraphData(
        nodes=[GraphNode(**n) for n in data["nodes"]],
        edges=[GraphEdge(**e) for e in data["edges"]],
    )
