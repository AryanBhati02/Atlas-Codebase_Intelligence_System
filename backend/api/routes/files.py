"""File content endpoint — returns raw source code for Monaco editor."""

from fastapi import APIRouter, HTTPException, Query
from models.schemas import FileContentResponse
from core.ingest.file_filter import detect_language
from utils.session import get_session_dir
from pathlib import Path

router = APIRouter(prefix="/files", tags=["Files"])


@router.get("/content/{session_id}", response_model=FileContentResponse)
async def get_file_content(session_id: str, path: str = Query(...)):
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    file_path = session_dir / "repo" / path
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    
    try:
        file_path.resolve().relative_to((session_dir / "repo").resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Path traversal not allowed.")

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read file.")

    lines = content.split("\n")
    loc = sum(1 for l in lines if l.strip())
    lang = detect_language(file_path.suffix)

    return FileContentResponse(
        path=path,
        content=content,
        language=lang,
        loc=loc,
        size_bytes=file_path.stat().st_size,
    )
