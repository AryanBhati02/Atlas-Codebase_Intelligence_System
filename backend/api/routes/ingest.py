"""Ingest API routes — GitHub clone and ZIP upload endpoints."""

import json
from fastapi import APIRouter, UploadFile, File, HTTPException
from datetime import datetime, timezone

from models.schemas import GitHubIngestRequest, IngestResponse
from core.ingest.git_ingest import clone_repository_async
from core.ingest.zip_ingest import extract_zip
from utils.session import create_session

router = APIRouter(prefix="/ingest", tags=["Ingest"])


def _save_session_meta(session_dir, repo_name, files, source_type):
    """Persist session metadata and file entries for the analyze pipeline."""
    meta = {"repo_name": repo_name, "source_type": source_type}
    (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    entries = [f.model_dump() for f in files]
    (session_dir / "file_entries.json").write_text(json.dumps(entries), encoding="utf-8")


@router.post("/github", response_model=IngestResponse)
async def ingest_github(request: GitHubIngestRequest):
    session_id, session_dir = create_session()

    try:
        repo_name, files = await clone_repository_async(request.url, session_dir)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    _save_session_meta(session_dir, repo_name, files, "github")

    return IngestResponse(
        session_id=session_id,
        repo_name=repo_name,
        total_files=len(files),
        files=files,
        ingested_at=datetime.now(timezone.utc).isoformat(),
        source_type="github",
    )


@router.post("/upload", response_model=IngestResponse)
async def ingest_upload(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted.")

    session_id, session_dir = create_session()
    zip_path = session_dir / "upload.zip"

    try:
        
        with open(zip_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)  
                if not chunk:
                    break
                f.write(chunk)
        repo_name, files = extract_zip(zip_path, session_dir)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

    _save_session_meta(session_dir, repo_name, files, "zip")

    return IngestResponse(
        session_id=session_id,
        repo_name=repo_name,
        total_files=len(files),
        files=files,
        ingested_at=datetime.now(timezone.utc).isoformat(),
        source_type="zip",
    )
