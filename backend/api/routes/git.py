"""Git Timeline + Coverage API endpoints."""

import json
from fastapi import APIRouter, HTTPException

from models.schemas import (
    TimelineResponse, CommitEntry,
    CommitDiffResponse, FileChange,
    CoverageResponse,
)
from core.analysis.git_timeline import (
    extract_timeline, get_commit_diff, parse_coverage,
    get_cached_timeline, cache_timeline,
)
from utils.session import get_session_dir

router = APIRouter(prefix="/git", tags=["Git Timeline"])


@router.get("/timeline/{session_id}", response_model=TimelineResponse)
async def git_timeline(session_id: str):
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    repo_dir = session_dir / "repo"
    if not repo_dir.exists():
        raise HTTPException(status_code=404, detail="Repository not found.")

    
    cached = get_cached_timeline(session_dir)
    if cached is not None:
        commits = [CommitEntry(**c) for c in cached]
        return TimelineResponse(commits=commits, total_commits=len(commits))

    
    
    import asyncio, subprocess
    try:
        await asyncio.to_thread(
            subprocess.run,
            ["git", "fetch", "--deepen=50"],
            capture_output=True, text=True, timeout=30,
            cwd=str(repo_dir),
        )
    except Exception:
        pass  

    
    raw_commits = extract_timeline(repo_dir)
    if not raw_commits:
        return TimelineResponse(commits=[], total_commits=0)

    
    cache_timeline(session_dir, raw_commits)

    commits = [CommitEntry(**c) for c in raw_commits]
    return TimelineResponse(commits=commits, total_commits=len(commits))


@router.get("/diff/{session_id}", response_model=CommitDiffResponse)
async def git_diff(session_id: str, commit: str):
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    repo_dir = session_dir / "repo"
    if not repo_dir.exists():
        raise HTTPException(status_code=404, detail="Repository not found.")

    result = get_commit_diff(repo_dir, commit)
    return CommitDiffResponse(
        hash=result["hash"],
        short_hash=result.get("short_hash", commit[:7]),
        message=result.get("message", ""),
        author=result.get("author", ""),
        timestamp=result.get("timestamp", ""),
        files=[FileChange(**f) for f in result.get("files", [])],
    )


@router.get("/coverage/{session_id}", response_model=CoverageResponse)
async def git_coverage(session_id: str):
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    result = parse_coverage(session_dir)
    return CoverageResponse(**result)
