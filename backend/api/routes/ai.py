
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import httpx

from models.schemas import (
    AIExplainRequest, AIExplainResponse,
    AIAnalyzeCodeRequest, AIAnalyzeCodeResponse,
    BeginnerGuideRequest, BeginnerGuideResponse, TopFileEntry,
    QARequest, QAResponse, FileReference,
)
from core.ai.ai_client import explain_file, analyze_code, beginner_guide, answer_question
from core.ai.router import route_stream
from core.ai.prompts import (
    build_explain_prompt,
    build_security_prompt,
    build_refactor_prompt,
    build_onboarding_prompt,
    build_qa_prompt,
)
from core.ai.cache import get_cached, set_cached, hash_content
from core.ai.advanced import scan_security, get_refactor_suggestions, generate_readme, generate_pr_review
from core.errors import ProviderUnavailableError
from core.ai.free_api import ProviderError
from utils.session import get_session_dir
from utils.session_cache import load_parsed, load_graph, load_dead_code

router = APIRouter(prefix="/ai", tags=["AI"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}

def _sse_chunk(text: str) -> str:
    return f"data: {json.dumps({'text': text})}\n\n"

def _sse_done() -> str:
    return "data: [DONE]\n\n"

def _sse_error(msg: str) -> str:
    return f"data: {json.dumps({'error': msg})}\n\n"

async def _stream_prompt(prompt: str):
    try:
        async for chunk in route_stream(prompt):
            yield _sse_chunk(chunk)
    except Exception as e:
        yield _sse_error(str(e))
    yield _sse_done()

def _load_repo_name(session_dir: Path, fallback: str) -> str:
    meta_path = session_dir / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return meta.get("repo_name", fallback)
        except Exception:
            pass
    return fallback

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

    try:
        result = await explain_file(request.file_path, content, parsed)
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "AI provider not available. Is Ollama running?",
                "code": "PROVIDER_OFFLINE",
            },
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "AI response timed out. Try a smaller file or a faster model.",
                "code": "TIMEOUT",
            },
        )
    except ProviderUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": f"AI provider error: {exc}",
                "code": "PROVIDER_ERROR",
            },
        )
    except ProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": f"AI provider error: {exc}",
                "code": "PROVIDER_ERROR",
            },
        )

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

    try:
        result = await analyze_code(request.code, request.file_path)
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail={"error": "AI provider not available. Is Ollama running?", "code": "PROVIDER_OFFLINE"},
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=503,
            detail={"error": "AI response timed out. Try a smaller file or a faster model.", "code": "TIMEOUT"},
        )
    except (ProviderUnavailableError, ProviderError) as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": f"AI provider error: {exc}", "code": "PROVIDER_ERROR"},
        )

    response = AIAnalyzeCodeResponse(analysis=result["analysis"], source=result["source"])
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

    repo_name = _load_repo_name(session_dir, request.session_id)
    try:
        result = await beginner_guide(repo_name, all_parsed, repo_dir)
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail={"error": "AI provider not available. Is Ollama running?", "code": "PROVIDER_OFFLINE"},
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=503,
            detail={"error": "AI response timed out. Try a smaller file or a faster model.", "code": "TIMEOUT"},
        )
    except (ProviderUnavailableError, ProviderError) as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": f"AI provider error: {exc}", "code": "PROVIDER_ERROR"},
        )

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

    try:
        result = await answer_question(request.question, all_parsed, repo_dir)
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail={"error": "AI provider not available. Is Ollama running?", "code": "PROVIDER_OFFLINE"},
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=503,
            detail={"error": "AI response timed out. Try a smaller file or a faster model.", "code": "TIMEOUT"},
        )
    except (ProviderUnavailableError, ProviderError) as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": f"AI provider error: {exc}", "code": "PROVIDER_ERROR"},
        )

    response = QAResponse(
        answer=result["answer"],
        referenced_files=[FileReference(**rf) for rf in result["referenced_files"]],
        source=result["source"],
    )
    set_cached(session_dir, cache_key, content_hash, response.model_dump())
    return response

@router.get("/explain/stream")
async def ai_explain_stream(
    session_id: str = Query(...),
    file_path: str = Query(...),
):
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    full_path = session_dir / "repo" / file_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    content = full_path.read_text(encoding="utf-8", errors="ignore")
    all_parsed = load_parsed(session_dir)
    parsed = next((p for p in all_parsed if p["path"] == file_path), {})

    imported_by = [p["path"] for p in all_parsed if file_path in p.get("imports", [])]

    repo_name = _load_repo_name(session_dir, session_id)
    file_data = {
        "repo_name": repo_name,
        "file_path": file_path,
        "language": parsed.get("language", "Unknown"),
        "loc": parsed.get("loc", 0),
        "complexity_score": parsed.get("complexity_score", 0),
        "nesting_depth": parsed.get("nesting_depth", 0),
        "functions": parsed.get("functions", []),
        "classes": parsed.get("classes", []),
        "imports": parsed.get("imports", []),
        "imported_by": imported_by,
        "content": content[:2000],
    }

    prompt = build_explain_prompt(file_data)
    return StreamingResponse(_stream_prompt(prompt), media_type="text/event-stream", headers=_SSE_HEADERS)

@router.post("/analyze/stream")
async def ai_analyze_stream(request: AIAnalyzeCodeRequest):
    try:
        session_dir = get_session_dir(request.session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    all_parsed = load_parsed(session_dir)
    parsed = next((p for p in all_parsed if p["path"] == request.file_path), {})

    full_path = session_dir / "repo" / request.file_path
    content_before = ""
    content_after = ""
    if full_path.exists():
        try:
            lines = full_path.read_text(encoding="utf-8", errors="ignore").split("\n")
            sl = max(0, (request.start_line or 1) - 11)
            el = min(len(lines), (request.end_line or len(lines)) + 10)
            content_before = "\n".join(lines[sl:max(0, (request.start_line or 1) - 1)])
            content_after = "\n".join(lines[min(len(lines), request.end_line or len(lines)):el])
        except Exception:
            pass

    file_context = {
        "file_path": request.file_path,
        "language": parsed.get("language", "Unknown"),
        "imports": parsed.get("imports", []),
        "complexity_score": parsed.get("complexity_score", 0),
        "content_before": content_before,
        "content_after": content_after,
    }

    prompt = build_refactor_prompt(request.code, file_context)
    return StreamingResponse(_stream_prompt(prompt), media_type="text/event-stream", headers=_SSE_HEADERS)

@router.get("/beginner/stream")
async def ai_beginner_stream(session_id: str = Query(...)):
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    all_parsed = load_parsed(session_dir)
    if not all_parsed:
        raise HTTPException(status_code=404, detail="Run analyze first.")

    repo_name = _load_repo_name(session_dir, session_id)

    file_tree = [f["path"] for f in all_parsed]
    total_loc = sum(f.get("loc", 0) for f in all_parsed)

    lang_counts: dict[str, int] = {}
    for f in all_parsed:
        lang = f.get("language") or "Other"
        lang_counts[lang] = lang_counts.get(lang, 0) + 1

    entry_names = {"main", "app", "index", "server", "__main__"}
    entry_points = [f["path"] for f in all_parsed if Path(f["path"]).stem.lower() in entry_names]

    import_counts: dict[str, int] = {}
    for f in all_parsed:
        for imp in f.get("imports", []):
            import_counts[imp] = import_counts.get(imp, 0) + 1
    top_imported = [
        {"path": k, "count": v}
        for k, v in sorted(import_counts.items(), key=lambda x: -x[1])[:10]
    ]

    repo_summary = {
        "repo_name": repo_name,
        "file_tree": file_tree,
        "top_imported": top_imported,
        "entry_points": entry_points,
        "total_files": len(all_parsed),
        "total_loc": total_loc,
        "languages": lang_counts,
        "parsed_files": all_parsed,
    }

    prompt = build_onboarding_prompt(repo_summary)
    return StreamingResponse(_stream_prompt(prompt), media_type="text/event-stream", headers=_SSE_HEADERS)

@router.get("/qa/stream")
async def ai_qa_stream(
    session_id: str = Query(...),
    question: str = Query(...),
    history: str = Query(default="[]"),
):
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    all_parsed = load_parsed(session_dir)
    if not all_parsed:
        raise HTTPException(status_code=404, detail="Run analyze first.")

    repo_dir = session_dir / "repo"

    try:
        history_list: list[dict] = json.loads(history)
    except Exception:
        history_list = []

    from core.ai.ai_client import _find_relevant_files
    relevant = _find_relevant_files(question, all_parsed, repo_dir)

    context_items: list[dict] = []
    for f in relevant[:5]:
        item = dict(f)
        try:
            fpath = repo_dir / f["path"]
            if fpath.exists():
                item["content"] = fpath.read_text(encoding="utf-8", errors="ignore")[:1500]
        except Exception:
            item["content"] = ""
        item["relevance_reason"] = "matched query keywords"
        context_items.append(item)

    prompt = build_qa_prompt(question, context_items, history_list)

    async def qa_generator():
                                                                                
        refs = [{"path": f["path"], "relevance_reason": "matched query"} for f in relevant[:5]]
        yield f"data: {json.dumps({'refs': refs})}\n\n"
        async for chunk in route_stream(prompt):
            yield _sse_chunk(chunk)
        yield _sse_done()

    return StreamingResponse(qa_generator(), media_type="text/event-stream", headers=_SSE_HEADERS)

@router.get("/security/stream")
async def ai_security_stream(
    session_id: str = Query(...),
    file_path: str = Query(...),
):
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    full_path = session_dir / "repo" / file_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    content = full_path.read_text(encoding="utf-8", errors="ignore")
    all_parsed = load_parsed(session_dir)
    parsed = next((p for p in all_parsed if p["path"] == file_path), {})

    repo_dir = session_dir / "repo"
    scan_result = scan_security(all_parsed, repo_dir)
    file_findings = [f for f in scan_result["findings"] if f.get("file") == file_path]

    file_data = {
        "file_path": file_path,
        "language": parsed.get("language", "Unknown"),
        "content": content,
    }

    prompt = build_security_prompt(file_data, file_findings)
    return StreamingResponse(_stream_prompt(prompt), media_type="text/event-stream", headers=_SSE_HEADERS)

@router.get("/refactor/stream")
async def ai_refactor_stream(
    session_id: str = Query(...),
    file_path: str = Query(...),
):
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    full_path = session_dir / "repo" / file_path
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")

    content = full_path.read_text(encoding="utf-8", errors="ignore")
    all_parsed = load_parsed(session_dir)
    parsed = next((p for p in all_parsed if p["path"] == file_path), {})
    dead_code = load_dead_code(session_dir)
    dead_exports = dead_code.get("dead_exports", [])

    result = await get_refactor_suggestions(file_path, parsed, content, dead_exports)

    lang = parsed.get("language", "Unknown")
    file_context = {
        "file_path": file_path,
        "language": lang,
        "imports": parsed.get("imports", []),
        "complexity_score": parsed.get("complexity_score", 0),
        "content_before": "",
        "content_after": "",
    }
    prompt = build_refactor_prompt(content[:3000], file_context)
    return StreamingResponse(_stream_prompt(prompt), media_type="text/event-stream", headers=_SSE_HEADERS)

@router.get("/readme/stream")
async def ai_readme_stream(session_id: str = Query(...)):
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    all_parsed = load_parsed(session_dir)
    if not all_parsed:
        raise HTTPException(status_code=404, detail="Run analyze first.")

    graph = load_graph(session_dir)
    repo_name = _load_repo_name(session_dir, session_id)
    repo_dir = session_dir / "repo"

    file_tree = [f["path"] for f in all_parsed]
    total_loc = sum(f.get("loc", 0) for f in all_parsed)
    lang_counts: dict[str, int] = {}
    for f in all_parsed:
        lang = f.get("language") or "Other"
        lang_counts[lang] = lang_counts.get(lang, 0) + 1

    entry_names = {"main", "app", "index", "server", "__main__"}
    entry_points = [f["path"] for f in all_parsed if Path(f["path"]).stem.lower() in entry_names]

    import_counts: dict[str, int] = {}
    for f in all_parsed:
        for imp in f.get("imports", []):
            import_counts[imp] = import_counts.get(imp, 0) + 1
    top_imported = [
        {"path": k, "count": v}
        for k, v in sorted(import_counts.items(), key=lambda x: -x[1])[:10]
    ]

    repo_summary = {
        "repo_name": repo_name,
        "file_tree": file_tree,
        "top_imported": top_imported,
        "entry_points": entry_points,
        "total_files": len(all_parsed),
        "total_loc": total_loc,
        "languages": lang_counts,
        "parsed_files": all_parsed,
    }

    from core.ai.prompts import build_onboarding_prompt

    name = repo_name
    tree_str = "\n".join(f"  {p}" for p in file_tree[:40])
    if len(file_tree) > 40:
        tree_str += f"\n  … +{len(file_tree) - 40} more"
    top_str = "\n".join(f"  {item['path']} (×{item['count']})" for item in top_imported[:10])
    ep_str = "\n".join(f"  {ep}" for ep in entry_points[:5]) or "  (none)"
    lang_str = ", ".join(f"{l} ({c})" for l, c in sorted(lang_counts.items(), key=lambda x: -x[1])[:5])
    key_files = sorted(all_parsed, key=lambda f: -f.get("complexity_score", 0))[:8]
    key_str = "\n".join(
        f"  {f['path']} ({f.get('language','?')}, {f.get('loc',0)} LOC, cx={f.get('complexity_score',0):.0%})"
        for f in key_files
    )
    edges = len(graph.get("edges", []))

    readme_prompt = (
        f"Generate a professional, GitHub-ready README.md for the '{name}' repository.\n\n"
        f"=== REPOSITORY STATS ===\n"
        f"Files: {len(all_parsed)}  |  LOC: {total_loc:,}  |  Dependency edges: {edges}\n"
        f"Languages: {lang_str}\n\n"
        f"=== FILE TREE ===\n{tree_str}\n\n"
        f"=== ENTRY POINTS ===\n{ep_str}\n\n"
        f"=== HUB FILES ===\n{top_str}\n\n"
        f"=== KEY FILES BY COMPLEXITY ===\n{key_str}\n\n"
        f"=== TASK ===\n"
        f"Write a complete README.md with these sections:\n\n"
        f"# {name} — title + one-line description\n\n"
        f"## Overview — what this project does and why it exists\n\n"
        f"## Getting Started\n"
        f"### Prerequisites\n"
        f"### Installation (with code blocks)\n"
        f"### Running (with code blocks)\n\n"
        f"## Project Structure — directory tree with explanations\n\n"
        f"## Architecture — design patterns, data flow, key abstractions\n\n"
        f"## Key Files — table of most important files with their roles\n\n"
        f"## Contributing — how to contribute\n\n"
        f"## License\n\n"
        f"Use proper markdown: tables, code blocks, badges. "
        f"Every section must use ACTUAL file names from the tree above."
    )

    return StreamingResponse(_stream_prompt(readme_prompt), media_type="text/event-stream", headers=_SSE_HEADERS)

@router.get("/pr-review/stream")
async def ai_pr_review_stream(
    session_id: str = Query(...),
    file_paths: str = Query(default=""),
):
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    all_parsed = load_parsed(session_dir)
    if not all_parsed:
        raise HTTPException(status_code=404, detail="Run analyze first.")

    selected = [p.strip() for p in file_paths.split(",") if p.strip()] if file_paths else []
    graph = load_graph(session_dir)
    dead_code = load_dead_code(session_dir)
    repo_name = _load_repo_name(session_dir, session_id)
    repo_dir = session_dir / "repo"

    targets = [f for f in all_parsed if f["path"] in selected] if selected else sorted(
        all_parsed, key=lambda x: -x.get("complexity_score", 0)
    )[:10]

    file_summary = "\n".join(
        f"  {f['path']} ({f.get('language','?')}, {f.get('loc',0)} LOC, "
        f"cx={f.get('complexity_score',0):.0%}, fns=[{', '.join(f.get('functions',[])[:4])}])"
        for f in targets
    )

    code_snippets = ""
    for f in targets[:3]:
        try:
            fpath = repo_dir / f["path"]
            if fpath.exists():
                snippet = fpath.read_text(encoding="utf-8", errors="ignore")[:1800]
                code_snippets += f"\n\n--- {f['path']} ---\n```\n{snippet}\n```"
        except Exception:
            pass

    edges_info = f"{len(graph.get('edges',[]))} dependency edges"
    dead_info = f"{len(dead_code.get('dead_files',[]))} dead files, {len(dead_code.get('dead_exports',[]))} dead exports"

    pr_prompt = (
        f"You are a staff engineer doing a thorough PR review for '{repo_name}'.\n\n"
        f"=== FILES UNDER REVIEW ===\n{file_summary}\n\n"
        f"=== GRAPH ===\n{edges_info}  |  {dead_info}\n"
        f"{code_snippets}\n\n"
        f"=== TASK ===\n"
        f"Write a detailed, actionable PR review:\n\n"
        f"## Change Summary\n"
        f"What do these files do? Their role in the system.\n\n"
        f"## Risk Assessment\n"
        f"For EACH file: risk level (HIGH/MEDIUM/LOW) with specific reasoning. "
        f"Consider complexity, dependant count, and code patterns.\n\n"
        f"## Impact Analysis\n"
        f"What other parts of the system could break? List specific downstream effects.\n\n"
        f"## Issues Found\n"
        f"Specific bugs, anti-patterns, security issues, performance problems. "
        f"Reference actual function names and code patterns.\n\n"
        f"## Per-File Review\n"
        f"For each file: quality assessment + specific concerns + suggestions.\n\n"
        f"## Verdict\n"
        f"✅ Approve / 🟡 Approve with caution / 🔴 Request changes\n"
        f"With a checklist of required actions before merge.\n\n"
        f"Be SPECIFIC. Reference actual file names and function names."
    )

    return StreamingResponse(_stream_prompt(pr_prompt), media_type="text/event-stream", headers=_SSE_HEADERS)
