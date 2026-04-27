"""
Rich progress endpoint — /api/progress/{session_id}

Returns a richer format than /analyze/progress/{session_id}:
  progress       — 0.0–1.0 float computed from files_done / total_files
  files_done     — number of files fully parsed
  total_files    — total files in the session
  status         — pipeline stage string
  partial_nodes  — graph nodes already computed (populated at done)
  partial_edges  — graph edges already computed (populated at done)
  error          — error message or null
"""

import logging

from fastapi import APIRouter

from core.session_progress import progress_store

logger = logging.getLogger("codebase-intel.routes.progress")

router = APIRouter(prefix="/progress", tags=["Progress"])


@router.get("/{session_id}")
async def get_rich_progress(session_id: str):
    """
    Poll this endpoint for live analysis progress.

    The response shape is a superset of /analyze/progress — it carries
    everything needed to drive a progress bar, status badge, and (eventually)
    an incremental graph render.
    """
    entry = progress_store.get_sync(session_id)

    if entry is None:
        return {
            "progress": 0.0,
            "files_done": 0,
            "total_files": 0,
            "status": "pending",
            "partial_nodes": [],
            "partial_edges": [],
            "error": None,
        }

    return entry.as_rich_dict()
