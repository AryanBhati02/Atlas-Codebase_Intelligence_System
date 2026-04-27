"""
Ingest API routes — GitHub shallow clone and ZIP upload.

Both endpoints are fully async:
  POST /ingest/github  — clones via asyncio.to_thread (never blocks event loop)
  POST /ingest/upload  — extracts ZIP via asyncio.to_thread

After ingestion the caller should POST to /analyze/start/{session_id} to trigger
the analysis pipeline (which runs as a Celery task or daemon thread).
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, UploadFile

from core.ingest.git_ingest import GitIngestError, clone_repository_async
from core.ingest.zip_ingest import extract_zip_async
from models.schemas import GitHubIngestRequest, IngestResponse
from utils.session import create_session

logger = logging.getLogger("codebase-intel.routes.ingest")

router = APIRouter(prefix="/ingest", tags=["Ingest"])


def _save_session_meta(session_dir, repo_name: str, files, source_type: str) -> None:
    """Persist session metadata and file entries for the analysis pipeline."""
    meta = {"repo_name": repo_name, "source_type": source_type}
    (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    entries = [f.model_dump() for f in files]
    (session_dir / "file_entries.json").write_text(json.dumps(entries), encoding="utf-8")


# ── GitHub clone ──────────────────────────────────────────────────────────────

@router.post("/github", response_model=IngestResponse)
async def ingest_github(request: GitHubIngestRequest):
    """
    Shallow-clone a public GitHub repository and return the file list.

    Uses depth=1 (single commit) for ~10× faster clones.
    The actual file parsing and graph construction is NOT done here —
    call POST /analyze/start/{session_id} after this endpoint returns.
    """
    session_id, session_dir = create_session()
    logger.info(f"[{session_id}] GitHub ingest requested: {request.url}")

    try:
        repo_name, files = await clone_repository_async(request.url, session_dir)

    except ValueError as exc:
        logger.warning(f"[{session_id}] Invalid URL: {exc}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": str(exc),
                "error_code": "INVALID_URL",
                "session_id": session_id,
            },
        )

    except GitIngestError as exc:
        logger.error(f"[{session_id}] Clone error [{exc.error_code}]: {exc}")
        status = 404 if exc.error_code == "REPO_NOT_FOUND" else 500
        raise HTTPException(
            status_code=status,
            detail={
                "error": str(exc),
                "error_code": exc.error_code,
                "session_id": session_id,
            },
        )

    except Exception as exc:  # noqa: BLE001
        logger.error(f"[{session_id}] Unexpected ingest error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "An unexpected error occurred during repository ingestion.",
                "error_code": "INGEST_FAILED",
                "session_id": session_id,
            },
        )

    _save_session_meta(session_dir, repo_name, files, "github")
    logger.info(f"[{session_id}] Ingested {len(files)} files from {repo_name}")

    return IngestResponse(
        session_id=session_id,
        repo_name=repo_name,
        total_files=len(files),
        files=files,
        ingested_at=datetime.now(timezone.utc).isoformat(),
        source_type="github",
    )


# ── ZIP upload ────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=IngestResponse)
async def ingest_upload(file: UploadFile = File(...)):
    """
    Accept a ZIP archive and extract it into a session directory.

    Extraction runs in asyncio.to_thread() so large archives don't block
    the event loop.  Zip-bomb and path-traversal protections are enforced
    before extraction begins.
    """
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Only .zip files are accepted.",
                "error_code": "INVALID_FILE_TYPE",
            },
        )

    session_id, session_dir = create_session()
    zip_path = session_dir / "upload.zip"
    logger.info(f"[{session_id}] ZIP upload started: {file.filename}")

    # Stream to disk in 1 MB chunks — avoids loading the whole file into RAM.
    try:
        with open(zip_path, "wb") as fh:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
    except OSError as exc:
        logger.error(f"[{session_id}] Failed to write upload: {exc}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to save uploaded file.",
                "error_code": "UPLOAD_WRITE_ERROR",
                "session_id": session_id,
            },
        )

    try:
        repo_name, files = await extract_zip_async(zip_path, session_dir)

    except ValueError as exc:
        logger.warning(f"[{session_id}] ZIP validation failed: {exc}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": str(exc),
                "error_code": "ZIP_INVALID",
                "session_id": session_id,
            },
        )

    except Exception as exc:  # noqa: BLE001
        logger.error(f"[{session_id}] ZIP extraction failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to extract ZIP archive.",
                "error_code": "ZIP_EXTRACT_FAILED",
                "session_id": session_id,
            },
        )

    _save_session_meta(session_dir, repo_name, files, "zip")
    logger.info(f"[{session_id}] Extracted {len(files)} files from {repo_name}")

    return IngestResponse(
        session_id=session_id,
        repo_name=repo_name,
        total_files=len(files),
        files=files,
        ingested_at=datetime.now(timezone.utc).isoformat(),
        source_type="zip",
    )
