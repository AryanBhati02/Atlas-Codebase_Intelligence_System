from fastapi import APIRouter, HTTPException

from models.schemas import (
    CommentCreate,
    CommentResponse,
    CommentCountsResponse,
    ShareTokenResponse,
)
from core.collaboration import (
    add_comment,
    get_comments,
    resolve_comment,
    delete_comment,
    get_comment_counts,
    generate_share_token,
)
from utils.session import get_session_dir

router = APIRouter(prefix="/comments", tags=["Collaboration"])

@router.post("", response_model=CommentResponse)
async def create_comment(body: CommentCreate):
    try:
        session_dir = get_session_dir(body.session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    comment = add_comment(
        session_dir=session_dir,
        session_id=body.session_id,
        target_type=body.target_type,
        target_id=body.target_id,
        message=body.message,
        author=body.author,
        parent_id=body.parent_id,
    )
    return CommentResponse(**comment)

@router.get("/{session_id}", response_model=list[CommentResponse])
async def list_comments(
    session_id: str,
    target_id: str | None = None,
    target_type: str | None = None,
):
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    results = get_comments(session_dir, session_id, target_id, target_type)
    return [CommentResponse(**c) for c in results]

@router.get("/{session_id}/counts", response_model=CommentCountsResponse)
async def comment_counts(session_id: str):
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    counts = get_comment_counts(session_dir, session_id)
    return CommentCountsResponse(counts=counts)

@router.patch("/{session_id}/resolve/{comment_id}")
async def toggle_resolve(session_id: str, comment_id: str):
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    result = resolve_comment(session_dir, comment_id)
    if not result:
        raise HTTPException(status_code=404, detail="Comment not found.")
    return CommentResponse(**result)

@router.delete("/{session_id}/{comment_id}")
async def remove_comment(session_id: str, comment_id: str):
    try:
        session_dir = get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found.")

    deleted = delete_comment(session_dir, comment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Comment not found.")
    return {"status": "deleted"}

@router.get("/{session_id}/share", response_model=ShareTokenResponse)
async def share_session(session_id: str):
    
    raise HTTPException(
        status_code=501, 
        detail="Share session feature is not yet implemented. Shared view UI pending."
    )
