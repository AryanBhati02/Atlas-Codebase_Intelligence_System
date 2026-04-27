"""AI endpoints — file explanation, code analysis, beginner guide, Q&A."""

import json
from fastapi import APIRouter, HTTPException

from models.schemas import (
    AIExplainRequest, AIExplainResponse,
    AIAnalyzeCodeRequest, AIAnalyzeCodeResponse,
    BeginnerGuideRequest, BeginnerGuideResponse, TopFileEntry,
    QARequest, QAResponse, FileReference,
)
from core.ai.ai_client import explain_file, analyze_code, beginner_guide, answer_question
from core.ai.cache import get_cached, set_cached, hash_content
from utils.session import get_session_dir
from utils.session_cache import load_parsed

router = APIRouter(prefix="/ai", tags=["AI"])




@router.post("/explain", response_model=AIExplainResponse)
async def ai_explain(request: AIExplainRequest):
    try:
        session_dir = get_session_dir(request.session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    file_path = session_dir / "repo" / request.file_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    content = file_path.read_text(encoding="utf-8", errors="ignore")
    content_hash = hash_content(content)

    
    cache_key = f"explain:{request.file_path}"
    cached = get_cached(session_dir, cache_key, content_hash)
    if cached:
        return AIExplainResponse(**cached)

    
    parsed = {}
    all_parsed = load_parsed(session_dir)
    for p in all_parsed:
        if p["path"] == request.file_path:
            parsed = p
            break

    result = await explain_file(request.file_path, content, parsed)
    response = AIExplainResponse(
        file_path=request.file_path,
        explanation=result["explanation"],
        source=result["source"],
    )

    
    set_cached(session_dir, cache_key, content_hash, response.model_dump())

    return response




@router.post("/analyze-code", response_model=AIAnalyzeCodeResponse)
async def ai_analyze(request: AIAnalyzeCodeRequest):
    try:
        session_dir = get_session_dir(request.session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    content_hash = hash_content(request.code)
    cache_key = f"analyze:{request.file_path}:{request.start_line}-{request.end_line}"
    cached = get_cached(session_dir, cache_key, content_hash)
    if cached:
        return AIAnalyzeCodeResponse(**cached)

    result = await analyze_code(request.code, request.file_path)
    response = AIAnalyzeCodeResponse(
        analysis=result["analysis"],
        source=result["source"],
    )

    set_cached(session_dir, cache_key, content_hash, response.model_dump())

    return response




@router.post("/beginner-guide", response_model=BeginnerGuideResponse)
async def ai_beginner_guide(request: BeginnerGuideRequest):
    try:
        session_dir = get_session_dir(request.session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    repo_dir = session_dir / "repo"
    all_parsed = load_parsed(session_dir)
    if not all_parsed:
        raise HTTPException(status_code=404, detail="Run analyze first.")

    
    cache_key = "beginner:guide"
    content_hash = hash_content(str(len(all_parsed)))
    cached = get_cached(session_dir, cache_key, content_hash)
    if cached:
        return BeginnerGuideResponse(**cached)

    
    repo_name = request.session_id
    meta_path = session_dir / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        repo_name = meta.get("repo_name", repo_name)

    result = await beginner_guide(repo_name, all_parsed, repo_dir)

    response = BeginnerGuideResponse(
        guide=result["guide"],
        top_files=[TopFileEntry(**tf) for tf in result["top_files"]],
        source=result["source"],
    )

    set_cached(session_dir, cache_key, content_hash, response.model_dump())

    return response




@router.post("/qa", response_model=QAResponse)
async def ai_qa(request: QARequest):
    try:
        session_dir = get_session_dir(request.session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    repo_dir = session_dir / "repo"
    all_parsed = load_parsed(session_dir)
    if not all_parsed:
        raise HTTPException(status_code=404, detail="Run analyze first.")

    
    content_hash = hash_content(request.question.strip().lower())
    cache_key = f"qa:{content_hash}"
    cached = get_cached(session_dir, cache_key, content_hash)
    if cached:
        return QAResponse(**cached)

    result = await answer_question(request.question, all_parsed, repo_dir)

    response = QAResponse(
        answer=result["answer"],
        referenced_files=[FileReference(**rf) for rf in result["referenced_files"]],
        source=result["source"],
    )

    set_cached(session_dir, cache_key, content_hash, response.model_dump())

    return response
