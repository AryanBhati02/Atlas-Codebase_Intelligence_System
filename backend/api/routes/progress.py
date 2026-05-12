import logging

from fastapi import APIRouter

from core.session_progress import progress_store

logger = logging.getLogger("codebase-intel.routes.progress")

router = APIRouter(prefix="/progress", tags=["Progress"])

@router.get("/{session_id}")
async def get_rich_progress(session_id: str):
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
