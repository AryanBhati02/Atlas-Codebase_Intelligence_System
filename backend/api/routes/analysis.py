"""Dead Code + Function Graph API routes."""

import json
from fastapi import APIRouter, HTTPException, Query
from pathlib import Path

from utils.session import get_session_dir
from core.analysis.dead_code import analyze_dead_code
from core.analysis.function_graph import build_function_graph
from models.schemas import (
    DeadCodeResponse,
    DeadFileEntry,
    DeadFunctionEntry,
    DeadExportEntry,
    DeadCodeSummary,
    FunctionGraphResponse,
    FunctionNode,
    FunctionEdge,
)

router = APIRouter(prefix="/analysis", tags=["Analysis"])




@router.get("/dead-code/{session_id}", response_model=DeadCodeResponse)
async def get_dead_code(session_id: str):
    """Analyze dead code for a session. Results are cached in dead_code.json."""
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    
    cache_path = session_dir / "dead_code.json"
    if cache_path.exists():
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return _build_dead_code_response(data)

    
    parsed_path = session_dir / "parsed.json"
    if not parsed_path.exists():
        raise HTTPException(status_code=404, detail="Run analyze first.")

    parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
    repo_dir = session_dir / "repo"

    
    result = analyze_dead_code(parsed, repo_dir)

    
    cache_path.write_text(json.dumps(result), encoding="utf-8")

    return _build_dead_code_response(result)


def _build_dead_code_response(data: dict) -> DeadCodeResponse:
    return DeadCodeResponse(
        dead_files=[DeadFileEntry(**d) for d in data["dead_files"]],
        dead_functions=[DeadFunctionEntry(**d) for d in data["dead_functions"]],
        dead_exports=[DeadExportEntry(**d) for d in data["dead_exports"]],
        summary=DeadCodeSummary(**data["summary"]),
    )




@router.get("/function-graph/{session_id}", response_model=FunctionGraphResponse)
async def get_function_graph(
    session_id: str,
    file: str = Query(..., description="Relative file path within the repo"),
):
    """Build function-level call graph for a specific file."""
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    
    cache_dir = session_dir / "function_graphs"
    cache_dir.mkdir(exist_ok=True)
    safe_name = file.replace("/", "__").replace("\\", "__")
    cache_path = cache_dir / f"{safe_name}.json"

    if cache_path.exists():
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return _build_fn_graph_response(file, data)

    
    parsed_path = session_dir / "parsed.json"
    if not parsed_path.exists():
        raise HTTPException(status_code=404, detail="Run analyze first.")

    parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
    parsed_file = next((f for f in parsed if f["path"] == file), None)
    if not parsed_file:
        raise HTTPException(status_code=404, detail=f"File not found: {file}")

    repo_dir = session_dir / "repo"

    
    result = build_function_graph(file, repo_dir, parsed_file)

    
    cache_path.write_text(json.dumps(result), encoding="utf-8")

    return _build_fn_graph_response(file, result)


def _build_fn_graph_response(file_path: str, data: dict) -> FunctionGraphResponse:
    return FunctionGraphResponse(
        file_path=file_path,
        nodes=[FunctionNode(**n) for n in data["nodes"]],
        edges=[FunctionEdge(**e) for e in data["edges"]],
    )
