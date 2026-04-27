"""
Central async analysis pipeline.

This is the single implementation of clone → scan → parse → score → graph → persist.
It is called in two ways:
  1. Celery task  →  asyncio.run(run_analysis_pipeline(...))
  2. Thread fallback  →  asyncio.run(run_analysis_pipeline(...))

Using asyncio.run() inside a non-async context (Celery task or daemon thread)
creates a fresh event loop for the duration of the call, which is safe and
idiomatic for Python 3.10+.
"""

import asyncio
import json
import logging
import time
from pathlib import Path

from config import ANALYSIS_TIMEOUT_SECONDS

logger = logging.getLogger("codebase-intel.pipeline")


class PipelineError(Exception):
    """Raised for known, non-retryable pipeline failures."""

    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.error_code = error_code


async def run_analysis_pipeline(session_id: str, session_dir: Path) -> None:
    """
    Full async analysis pipeline: scan → parse → score → build graph → persist.

    Writes progress to ProgressStore at each stage via update_sync() so that
    both Celery workers (separate process) and the FastAPI polling endpoint
    stay in sync through the shared progress.json on disk.

    Raises PipelineError, TimeoutError, MemoryError — callers must catch these
    and set error state on the ProgressStore.
    """
    from core.session_progress import progress_store

    start = time.monotonic()
    log = logging.getLogger(f"codebase-intel.pipeline.{session_id[:8]}")

    def _elapsed() -> float:
        return time.monotonic() - start

    def _check_timeout() -> None:
        if _elapsed() > ANALYSIS_TIMEOUT_SECONDS:
            raise TimeoutError(
                f"Analysis timed out after {_elapsed():.0f}s "
                f"(limit: {ANALYSIS_TIMEOUT_SECONDS}s). "
                "Try a smaller repository or increase ANALYSIS_TIMEOUT_SECONDS."
            )

    # ── 1. Validate session ──────────────────────────────────────────────────
    repo_dir = session_dir / "repo"
    if not repo_dir.exists():
        raise PipelineError(
            f"Repository directory not found for session {session_id}. "
            "Ensure ingestion completed successfully before starting analysis.",
            error_code="REPO_NOT_FOUND",
        )

    # ── 2. Scan or load file entries ─────────────────────────────────────────
    entries_path = session_dir / "file_entries.json"
    if not entries_path.exists():
        progress_store.update_sync(session_id, status="scanning")
        log.info(f"Scanning repository directory")
        from core.ingest.file_filter import scan_directory
        # scan_directory is CPU + I/O bound; run in a thread to free the event loop.
        file_entries = await asyncio.to_thread(scan_directory, repo_dir)
        entries_data = [e.model_dump() for e in file_entries]
        await asyncio.to_thread(
            entries_path.write_text,
            json.dumps(entries_data),
            "utf-8",
        )
    else:
        entries_data = json.loads(entries_path.read_text(encoding="utf-8"))

    total = len(entries_data)
    log.info(f"Pipeline starting for {total} files")
    progress_store.update_sync(session_id, status="parsing", total_files=total, parsed_files=0)

    # ── 3. Parse all files (bounded async concurrency) ───────────────────────
    _check_timeout()
    from core.parser.parser_service import parse_all_files_async

    def _on_progress(current: int, total_: int) -> None:
        progress_store.update_sync(session_id, parsed_files=current, total_files=total_)

    parsed = await parse_all_files_async(repo_dir, entries_data, progress_callback=_on_progress)
    _check_timeout()

    # ── 4. Score ─────────────────────────────────────────────────────────────
    progress_store.update_sync(session_id, status="scoring")
    from core.scoring.complexity_scorer import score_files
    parsed = await asyncio.to_thread(score_files, parsed)
    _check_timeout()

    # ── 5. Build dependency graph ─────────────────────────────────────────────
    progress_store.update_sync(session_id, status="graph")
    from core.graph.graph_builder import build_graph
    graph_data = await asyncio.to_thread(build_graph, parsed)
    _check_timeout()

    # ── 6. Persist to disk ───────────────────────────────────────────────────
    progress_store.update_sync(session_id, status="saving")

    parsed_json = json.dumps(parsed)
    graph_json = json.dumps(graph_data)

    await asyncio.to_thread(
        (session_dir / "parsed.json").write_text, parsed_json, "utf-8"
    )
    await asyncio.to_thread(
        (session_dir / "graph.json").write_text, graph_json, "utf-8"
    )

    elapsed = _elapsed()
    log.info(f"Pipeline complete: {len(parsed)} files in {elapsed:.1f}s")

    progress_store.update_sync(
        session_id,
        status="done",
        parsed_files=len(parsed),
        total_files=total,
    )
