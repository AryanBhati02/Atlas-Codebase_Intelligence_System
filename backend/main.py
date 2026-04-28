"""Codebase Intelligence Tool — FastAPI Backend Entry Point."""

import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import CORS_ORIGINS, SESSIONS_DIR
from api.routes.ingest import router as ingest_router
from api.routes.analyze import router as analyze_router
from api.routes.files import router as files_router
from api.routes.ai import router as ai_router
from api.routes.settings import router as settings_router
from api.routes.analysis import router as analysis_router
from api.routes.advanced_ai import router as advanced_ai_router
from api.routes.git import router as git_router
from api.routes.collaboration import router as collab_router
from api.routes.progress import router as progress_router


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("codebase-intel")



@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Codebase Intelligence Tool starting up (v2.1.0)")
    from utils.session import cleanup_expired_sessions
    cleaned = cleanup_expired_sessions()
    if cleaned:
        logger.info(f"🧹 Cleaned up {cleaned} expired sessions")
    yield
    
    from core.ai.free_api import async_cleanup
    await async_cleanup()
    logger.info("🛑 Codebase Intelligence Tool shutting down")


app = FastAPI(
    title="Codebase Intelligence Tool",
    version="2.1.0",
    description="AI-powered developer intelligence platform",
    lifespan=lifespan,
)



@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)[:200]},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest_router, prefix="/api")
app.include_router(analyze_router, prefix="/api")
app.include_router(files_router, prefix="/api")
app.include_router(ai_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(analysis_router, prefix="/api")
app.include_router(advanced_ai_router, prefix="/api")
app.include_router(git_router, prefix="/api")
app.include_router(collab_router, prefix="/api")
app.include_router(progress_router, prefix="/api")


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": "2.1.0"}


if __name__ == "__main__":
    # sessions/ is created by config.py at import time (above), so it exists
    # before the watcher starts and the exclusion takes effect immediately.
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_excludes=[str(SESSIONS_DIR)],
    )
