"""
FastAPI router: GET /api/mcp/status

Reports the live health of the Atlas MCP server components so the front-end
(or a CI check) can verify that the retriever stack is ready before Claude
Code / Cursor connects.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter

logger = logging.getLogger("atlas.mcp_status")

router = APIRouter(tags=["mcp"])

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_TOOLS = [
    "search_codebase",
    "check_exists",
    "get_function_context",
    "get_hot_paths",
    "get_architecture_rules",
]

@router.get("/api/mcp/status")
async def mcp_status() -> dict:
    """Return the current health of the Atlas MCP server components.

    Response fields:
    - connected        : True if Qdrant is reachable.
    - indexed_functions: Number of points in the 'atlas_functions' collection.
    - collection       : Qdrant collection name.
    - tools            : List of the 5 exposed MCP tool names.
    - model_loaded     : True if the model checkpoint file exists on disk.
    - bm25_loaded      : True if the BM25 index file exists on disk.
    """
    #Qdrant health check
    qdrant_connected = False
    indexed_functions: int = 0
    collection_name = "atlas_functions"

    try:
        from core.retrieval.qdrant_store import AtlasQdrantStore  # noqa: PLC0415

        store = AtlasQdrantStore()
        qdrant_connected = store.is_healthy()
        if qdrant_connected:
            info = store.get_collection_info()
            indexed_functions = info.get("point_count") or 0
            collection_name = info.get("name", collection_name)
    except Exception as exc:
        logger.warning("Qdrant health check failed: %s", exc)

    #Artefact existence checkss
    checkpoint_path = _BACKEND_DIR / "training" / "checkpoints" / "best_model.pt"
    bm25_path = _BACKEND_DIR / "training" / "data" / "bm25_index.pkl"

    model_loaded = checkpoint_path.exists()
    bm25_loaded = bm25_path.exists()

    return {
        "connected": qdrant_connected,
        "indexed_functions": indexed_functions,
        "collection": collection_name,
        "tools": _TOOLS,
        "model_loaded": model_loaded,
        "bm25_loaded": bm25_loaded,
    }
