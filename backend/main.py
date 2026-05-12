import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import CORS_ORIGINS, SESSIONS_DIR
from core.logger import get_logger
from core.errors import AtlasError
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
from api.routes.function_graph import router as function_graph_router
from api.routes.search import router as search_router
from api.routes.mcp_status import router as mcp_status_router

logger = get_logger("atlas.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Atlas starting up", extra={"version": "2.1.0"})
    from utils.session import cleanup_expired_sessions
    cleaned = cleanup_expired_sessions()
    if cleaned:
        logger.info("Expired sessions cleaned", extra={"count": cleaned})

    # Pre-warm the retriever singleton so the first search request is instant
    try:
        import asyncio
        from core.retrieval.retriever_factory import get_retriever
        await asyncio.to_thread(get_retriever)
        logger.info("AgenticRetriever pre-warmed successfully")
    except Exception as exc:
        logger.warning(f"AgenticRetriever pre-warm skipped (index not yet built?): {exc}")

    yield
    from core.ai.free_api import async_cleanup
    await async_cleanup()
    logger.info("Atlas shutting down")

app = FastAPI(
    title="Codebase Intelligence Tool",
    version="2.1.0",
    description="AI-powered developer intelligence platform",
    lifespan=lifespan,
)

@app.exception_handler(AtlasError)
async def atlas_error_handler(request: Request, exc: AtlasError) -> JSONResponse:
    logger.error(
        "Atlas application error",
        extra={"code": exc.code, "path": str(request.url.path)},
    )
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled exception",
        extra={"path": str(request.url.path), "exc_type": type(exc).__name__},
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "code": "INTERNAL_ERROR"},
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
app.include_router(function_graph_router, prefix="/api")
app.include_router(search_router)
app.include_router(mcp_status_router)

@app.get("/api/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "version": "2.1.0"}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_excludes=[str(SESSIONS_DIR)],
    )
