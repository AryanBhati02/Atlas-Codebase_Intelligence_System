from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("codebase-intel.search_routes")

router = APIRouter(prefix="/api/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    language: Optional[str] = None


class SearchResult(BaseModel):
    name: str
    file_path: str
    language: str
    line_start: int
    line_end: int
    behavioral_similarity: float
    textual_score: float
    final_score: float
    docstring: str
    complexity: int
    is_hot_path: bool


class SearchResponse(BaseModel):
    results: list[SearchResult]
    query: str
    total_candidates: int
    retrieval_time_ms: float


def _get_retriever():
    from core.retrieval.retriever_factory import get_retriever
    return get_retriever()


@router.post("", response_model=SearchResponse)
async def search_functions(request: SearchRequest) -> SearchResponse:
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    try:
        retriever = _get_retriever()
    except ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Qdrant is not reachable. Start Qdrant and try again. Detail: {exc}",
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Search index not found. Run index_repo.py first. Detail: {exc}",
        )
    except Exception as exc:
        logger.exception("Failed to initialise retriever")
        raise HTTPException(
            status_code=503,
            detail=f"Retriever initialisation failed: {exc}",
        )

    t0 = time.monotonic()
    try:
        raw_results = await retriever.retrieve(
            query=request.query.strip(),
            top_k=request.top_k,
            language=request.language,
        )
    except Exception as exc:
        logger.exception("Retrieval error")
        raise HTTPException(status_code=500, detail=f"Retrieval error: {exc}")
    elapsed_ms = (time.monotonic() - t0) * 1000.0

    results = [
        SearchResult(
            name=r.name,
            file_path=r.file_path,
            language=r.language,
            line_start=r.line_start,
            line_end=r.line_end,
            behavioral_similarity=r.behavioral_score,
            textual_score=r.textual_score,
            final_score=r.final_score,
            docstring=r.docstring,
            complexity=r.complexity,
            is_hot_path=r.is_hot_path,
        )
        for r in raw_results
    ]

    return SearchResponse(
        results=results,
        query=request.query,
        total_candidates=len(results),
        retrieval_time_ms=round(elapsed_ms, 2),
    )


@router.get("/stream")
async def stream_search(query: str, top_k: int = 10):
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    try:
        retriever = _get_retriever()
    except ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Qdrant is not reachable: {exc}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Retriever initialisation failed: {exc}",
        )

    async def event_generator():
        try:
            results = await retriever.retrieve(query=query.strip(), top_k=top_k)
        except Exception as exc:
            error_payload = json.dumps({"error": str(exc)})
            yield f"data: {error_payload}\n\n"
            return

        for result in results:
            payload = {
                "name": result.name,
                "file_path": result.file_path,
                "language": result.language,
                "line_start": result.line_start,
                "line_end": result.line_end,
                "behavioral_similarity": result.behavioral_score,
                "textual_score": result.textual_score,
                "final_score": result.final_score,
                "docstring": result.docstring,
                "complexity": result.complexity,
                "is_hot_path": result.is_hot_path,
            }
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0)

        done_payload = json.dumps({"done": True, "total": len(results)})
        yield f"data: {done_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health")
async def search_health() -> dict:
    try:
        retriever = _get_retriever()
        info = retriever.qdrant.get_collection_info()
        return {
            "status": "ok",
            "collection": info.get("name", "atlas_functions"),
            "point_count": info.get("point_count", 0),
            "qdrant_status": info.get("status", "unknown"),
        }
    except ConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Qdrant is not reachable. Make sure it is running. Detail: {exc}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Search health check failed: {exc}",
        )
