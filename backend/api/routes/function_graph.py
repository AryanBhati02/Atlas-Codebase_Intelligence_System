"""
function_graph.py
-----------------
FastAPI router exposing the function-level call graph for a session.

Endpoints
---------
GET  /api/sessions/{session_id}/function-graph
     → Full graph JSON (nodes + edges + stats)

GET  /api/sessions/{session_id}/function-graph/search?name={name}
     → Matching function nodes + their edges (case-insensitive substring)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from config import SESSIONS_DIR

logger = logging.getLogger("codebase-intel.routes.function_graph")

router = APIRouter(prefix="/sessions", tags=["Function Graph"])


def _load_function_graph(session_id: str) -> dict:
    """
    Load function_graph.json for *session_id*.
    Raises HTTPException 404 if not found, 500 on parse error.
    """
    graph_path: Path = SESSIONS_DIR / session_id / "function_graph.json"

    if not graph_path.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Function graph not available — re-analyze this repository",
                "error_code": "FUNCTION_GRAPH_NOT_FOUND",
                "session_id": session_id,
            },
        )

    try:
        return json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error(f"[{session_id}] Failed to load function_graph.json: {exc}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to read function graph data.",
                "error_code": "FUNCTION_GRAPH_READ_ERROR",
                "session_id": session_id,
            },
        )







@router.get("/{session_id}/function-graph")
async def get_function_graph(session_id: str) -> JSONResponse:
    """
    Return the full function-level call graph for a session.

    Response schema::

        {
            "nodes": [
                {
                    "id": "filepath::ClassName.method",
                    "name": "ClassName.method",
                    "file_path": "...",
                    "language": "python",
                    "line_start": 10,
                    "line_end": 40,
                    "complexity": 3,
                    "fan_in": 2,
                    "fan_out": 5,
                    "parameters": ["self", "request"],
                    "docstring": "..."
                },
                ...
            ],
            "edges": [
                {"source": "...", "target": "...", "edge_type": "call"},
                ...
            ],
            "stats": {
                "total_nodes": 412,
                "total_edges": 871,
                "avg_complexity": 2.3,
                "max_fan_in": 18,
                "max_fan_out": 12
            }
        }
    """
    data = _load_function_graph(session_id)
    return JSONResponse(content=data)







@router.get("/{session_id}/function-graph/search")
async def search_function_graph(
    session_id: str,
    name: str = Query(..., description="Substring to search in function names (case-insensitive)"),
) -> JSONResponse:
    """
    Search function nodes by name (case-insensitive substring match).

    Returns matching nodes together with all edges where either endpoint is
    a matched node.

    Response schema::

        {
            "query": "parseFile",
            "matched_nodes": [ { ...node fields... }, ... ],
            "related_edges": [ {"source", "target", "edge_type"}, ... ],
            "total_matches": 3
        }
    """
    data = _load_function_graph(session_id)

    nodes: list[dict] = data.get("nodes", [])
    edges: list[dict] = data.get("edges", [])

    query_lower = name.strip().lower()
    if not query_lower:
        raise HTTPException(
            status_code=400,
            detail={"error": "Query parameter 'name' must not be empty.", "error_code": "EMPTY_QUERY"},
        )

    
    matched_nodes = [
        n for n in nodes
        if query_lower in n.get("name", "").lower() or query_lower in n.get("id", "").lower()
    ]

    matched_ids = {n["id"] for n in matched_nodes}

    
    related_edges = [
        e for e in edges
        if e.get("source") in matched_ids or e.get("target") in matched_ids
    ]

    return JSONResponse(
        content={
            "query": name,
            "matched_nodes": matched_nodes,
            "related_edges": related_edges,
            "total_matches": len(matched_nodes),
        }
    )
