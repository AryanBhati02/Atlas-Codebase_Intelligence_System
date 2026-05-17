import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from core.ingest.git_ingest import GitIngestError, clone_repository_async
from core.ingest.zip_ingest import extract_zip_async
from models.schemas import GitHubIngestRequest, IngestResponse
from utils.session import create_session

logger = logging.getLogger("codebase-intel.routes.ingest")

_INGEST_READY = ".ingest_ready"
_INGEST_FAILED = ".ingest_failed"


def _mark_ready(session_dir: Path) -> None:
    """Write the readiness sentinel so the Celery task can proceed."""
    ready_path = session_dir / _INGEST_READY
    ready_path.write_text(str(time.time()), encoding="utf-8")
    logger.info(
        "[INGEST_READY] Sentinel written: %s (exists=%s)",
        ready_path.resolve(),
        ready_path.exists(),
    )


def _mark_failed(session_dir: Path, reason: str) -> None:
    """Write the failure sentinel so the Celery task bails immediately."""
    try:
        failed_path = session_dir / _INGEST_FAILED
        failed_path.write_text(reason[:300], encoding="utf-8")
        logger.error(
            "[INGEST_FAILED] Failure sentinel written: %s reason=%r",
            failed_path.resolve(),
            reason[:120],
        )
    except Exception as write_exc:
        logger.error("[INGEST_FAILED] Could not write failure sentinel: %s", write_exc)


router = APIRouter(prefix="/ingest", tags=["Ingest"])


def _save_session_meta(session_dir: Path, repo_name: str, files: list, source_type: str) -> None:
    meta = {"repo_name": repo_name, "source_type": source_type}
    (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    entries = [f.model_dump() for f in files]
    (session_dir / "file_entries.json").write_text(json.dumps(entries), encoding="utf-8")


@router.post("/github", response_model=IngestResponse)
async def ingest_github(request: GitHubIngestRequest):
    session_id, session_dir = create_session()

    logger.info(
        "[INGEST_START] [%s] GitHub ingest requested: %s  |  session_dir=%s",
        session_id, request.url, session_dir.resolve(),
    )

    repo_dir = session_dir / "repo"

    try:

        logger.info(
            "[INGEST_CLONE_START] [%s] Calling clone_repository_async  |  repo_dir=%s",
            session_id, repo_dir.resolve(),
        )

        repo_name, files = await clone_repository_async(request.url, session_dir)

        file_count_on_disk = sum(1 for _ in repo_dir.rglob("*") if _.is_file())
        logger.info(
            "[INGEST_CLONE_DONE] [%s] Clone finished: %s  |  "
            "files_from_scan=%d  files_on_disk=%d  repo_dir=%s",
            session_id, repo_name, len(files), file_count_on_disk, repo_dir.resolve(),
        )

        if not repo_dir.exists() or not any(repo_dir.iterdir()):
            raise RuntimeError(
                f"Clone reported success but repo_dir is empty: {repo_dir.resolve()}"
            )

    except ValueError as exc:
        logger.warning("[INGEST_FAILED] [%s] Invalid URL: %s", session_id, exc)
        _mark_failed(session_dir, f"INVALID_URL: {exc}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": str(exc),
                "error_code": "INVALID_URL",
                "session_id": session_id,
            },
        )

    except GitIngestError as exc:
        logger.error(
            "[INGEST_FAILED] [%s] Clone error [%s]: %s",
            session_id, exc.error_code, exc,
        )
        _mark_failed(session_dir, f"{exc.error_code}: {exc}")
        status = 404 if exc.error_code == "REPO_NOT_FOUND" else 500
        raise HTTPException(
            status_code=status,
            detail={
                "error": str(exc),
                "error_code": exc.error_code,
                "session_id": session_id,
            },
        )

    except Exception as exc:
        logger.error(
            "[INGEST_FAILED] [%s] Unexpected ingest error: %s",
            session_id, exc, exc_info=True,
        )
        _mark_failed(session_dir, f"INGEST_FAILED: {exc}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "An unexpected error occurred during repository ingestion.",
                "error_code": "INGEST_FAILED",
                "session_id": session_id,
            },
        )
        
    _save_session_meta(session_dir, repo_name, files, "github")
    logger.info(
        "[INGEST_SCAN_DONE] [%s] Metadata saved  |  "
        "file_entries=%d  session_dir=%s",
        session_id, len(files), session_dir.resolve(),
    )

    _mark_ready(session_dir)
    logger.info(
        "[INGEST_READY] [%s] Ingested %d files from %s  |  "
        "sentinel=%s  repo_dir=%s",
        session_id, len(files), repo_name,
        (session_dir / _INGEST_READY).resolve(),
        repo_dir.resolve(),
    )

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
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Only .zip files are accepted.",
                "error_code": "INVALID_FILE_TYPE",
            },
        )

    session_id, session_dir = create_session()
    zip_path = session_dir / "upload.zip"
    logger.info(
        "[INGEST_START] [%s] ZIP upload started: %s  |  session_dir=%s",
        session_id, file.filename, session_dir.resolve(),
    )

    try:
        with open(zip_path, "wb") as fh:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
    except OSError as exc:
        logger.error("[INGEST_FAILED] [%s] Failed to write upload: %s", session_id, exc)
        _mark_failed(session_dir, f"UPLOAD_WRITE_ERROR: {exc}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to save uploaded file.",
                "error_code": "UPLOAD_WRITE_ERROR",
                "session_id": session_id,
            },
        )

    try:
        logger.info("[INGEST_CLONE_START] [%s] Starting ZIP extraction", session_id)
        repo_name, files = await extract_zip_async(zip_path, session_dir)
        repo_dir = session_dir / "repo"
        file_count_on_disk = sum(1 for _ in repo_dir.rglob("*") if _.is_file())
        logger.info(
            "[INGEST_CLONE_DONE] [%s] ZIP extracted: %s  |  "
            "files_from_scan=%d  files_on_disk=%d",
            session_id, repo_name, len(files), file_count_on_disk,
        )

    except ValueError as exc:
        logger.warning("[INGEST_FAILED] [%s] ZIP validation failed: %s", session_id, exc)
        _mark_failed(session_dir, f"ZIP_INVALID: {exc}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": str(exc),
                "error_code": "ZIP_INVALID",
                "session_id": session_id,
            },
        )

    except Exception as exc:
        logger.error("[INGEST_FAILED] [%s] ZIP extraction failed: %s", session_id, exc, exc_info=True)
        _mark_failed(session_dir, f"ZIP_EXTRACT_FAILED: {exc}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Failed to extract ZIP archive.",
                "error_code": "ZIP_EXTRACT_FAILED",
                "session_id": session_id,
            },
        )

    _save_session_meta(session_dir, repo_name, files, "zip")
    logger.info("[INGEST_SCAN_DONE] [%s] Metadata saved for %d files", session_id, len(files))

    _mark_ready(session_dir)
    logger.info(
        "[INGEST_READY] [%s] Extracted %d files from %s  |  sentinel=%s",
        session_id, len(files), repo_name,
        (session_dir / _INGEST_READY).resolve(),
    )

    return IngestResponse(
        session_id=session_id,
        repo_name=repo_name,
        total_files=len(files),
        files=files,
        ingested_at=datetime.now(timezone.utc).isoformat(),
        source_type="zip",
    )
