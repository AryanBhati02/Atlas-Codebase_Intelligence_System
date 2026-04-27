"""Advanced AI endpoints — README generator, refactor suggestions, security scanner."""

import json
from fastapi import APIRouter, HTTPException

from models.schemas import (
    ReadmeRequest, ReadmeResponse,
    RefactorRequest, RefactorResponse,
    SecurityScanRequest, SecurityScanResponse, SecurityFinding, SecuritySummary, SecurityRecommendation,
    PRReviewRequest, PRReviewResponse,
)
from core.ai.advanced import generate_readme, get_refactor_suggestions, scan_security, generate_pr_review
from core.ai.cache import get_cached, set_cached, hash_content
from utils.session import get_session_dir
from utils.session_cache import load_parsed, load_graph, load_dead_code

router = APIRouter(prefix="/ai/advanced", tags=["Advanced AI"])




@router.post("/readme", response_model=ReadmeResponse)
async def ai_readme(request: ReadmeRequest):
    try:
        session_dir = get_session_dir(request.session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    all_parsed = load_parsed(session_dir)
    if not all_parsed:
        raise HTTPException(status_code=404, detail="Run analyze first.")

    
    cache_key = "advanced:readme"
    content_hash = hash_content(str(len(all_parsed)))
    cached = get_cached(session_dir, cache_key, content_hash)
    if cached:
        return ReadmeResponse(**cached)

    graph = load_graph(session_dir)
    repo_name = request.session_id
    meta_path = session_dir / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        repo_name = meta.get("repo_name", repo_name)

    result = await generate_readme(repo_name, all_parsed, graph, session_dir / "repo")
    response = ReadmeResponse(readme=result["readme"], source=result["source"])
    set_cached(session_dir, cache_key, content_hash, response.model_dump())
    return response




@router.post("/refactor", response_model=RefactorResponse)
async def ai_refactor(request: RefactorRequest):
    try:
        session_dir = get_session_dir(request.session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    file_path = session_dir / "repo" / request.file_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    content = file_path.read_text(encoding="utf-8", errors="ignore")
    content_hash = hash_content(content)
    cache_key = f"advanced:refactor:{request.file_path}"
    cached = get_cached(session_dir, cache_key, content_hash)
    if cached:
        return RefactorResponse(**cached)

    
    all_parsed = load_parsed(session_dir)
    parsed = {}
    for p in all_parsed:
        if p["path"] == request.file_path:
            parsed = p
            break

    
    dead_code = load_dead_code(session_dir)
    dead_exports = dead_code.get("dead_exports", [])

    result = await get_refactor_suggestions(request.file_path, parsed, content, dead_exports)
    response = RefactorResponse(
        file_path=request.file_path,
        suggestions=result["suggestions"],
        source=result["source"],
    )
    set_cached(session_dir, cache_key, content_hash, response.model_dump())
    return response




@router.post("/security", response_model=SecurityScanResponse)
async def ai_security(request: SecurityScanRequest):
    try:
        session_dir = get_session_dir(request.session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    all_parsed = load_parsed(session_dir)
    if not all_parsed:
        raise HTTPException(status_code=404, detail="Run analyze first.")

    cache_key = "advanced:security"
    content_hash = hash_content(str(len(all_parsed)))
    cached = get_cached(session_dir, cache_key, content_hash)
    if cached:
        return SecurityScanResponse(**cached)

    repo_dir = session_dir / "repo"
    result = scan_security(all_parsed, repo_dir)

    response = SecurityScanResponse(
        findings=[SecurityFinding(**f) for f in result["findings"]],
        summary=SecuritySummary(**result["summary"]),
        recommendations=[SecurityRecommendation(**r) for r in result.get("recommendations", [])],
    )
    set_cached(session_dir, cache_key, content_hash, response.model_dump())
    return response




@router.post("/pr-review", response_model=PRReviewResponse)
async def ai_pr_review(request: PRReviewRequest):
    try:
        session_dir = get_session_dir(request.session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    all_parsed = load_parsed(session_dir)
    if not all_parsed:
        raise HTTPException(status_code=404, detail="Run analyze first.")

    
    file_key = "|".join(sorted(request.file_paths)) if request.file_paths else "all"
    cache_key = f"advanced:pr-review:{hash_content(file_key)}"
    content_hash = hash_content(str(len(all_parsed)) + file_key)
    cached = get_cached(session_dir, cache_key, content_hash)
    if cached:
        return PRReviewResponse(**cached)

    graph = load_graph(session_dir)
    dead_code = load_dead_code(session_dir)

    repo_name = request.session_id
    meta_path = session_dir / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        repo_name = meta.get("repo_name", repo_name)

    repo_dir = session_dir / "repo"
    result = await generate_pr_review(all_parsed, graph, dead_code, request.file_paths, repo_name, repo_dir)
    response = PRReviewResponse(review=result["review"], source=result["source"])
    set_cached(session_dir, cache_key, content_hash, response.model_dump())
    return response
