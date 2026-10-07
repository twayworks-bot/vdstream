import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings, BASE_DIR
from app.database import init_db
from app.api.v1 import api_v1_router
from app.dashboard.routes import router as dashboard_router
from app.services.queue_manager import queue_manager
from app.services.stream_manager import stream_manager
from app.services.retention_service import retention_service

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("vdstream")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info("Initializing VDSTREAM database and storage...")
    init_db()
    settings.ensure_directories()

    logger.info("Starting QueueManager, StreamManager, and RetentionService...")
    await queue_manager.start()
    await stream_manager.start()
    await retention_service.start()
    logger.info("VDSTREAM services successfully started.")

    yield

    # --- Shutdown ---
    logger.info("Shutting down VDSTREAM services...")
    await queue_manager.stop()
    await stream_manager.stop()
    await retention_service.stop()
    logger.info("VDSTREAM shutdown complete.")

base_prefix = settings.base_prefix

app = FastAPI(
    title="VDSTREAM",
    description="Video Transcoding, HLS Streaming, and Retention Lifecycle Management Platform",
    version="1.0.0",
    docs_url=f"{base_prefix}/docs" if base_prefix else "/docs",
    redoc_url=f"{base_prefix}/redoc" if base_prefix else "/redoc",
    openapi_url=f"{base_prefix}/openapi.json" if base_prefix else "/openapi.json",
    lifespan=lifespan
)

# Enable CORS for external web applications
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static Files
static_dir = (BASE_DIR / "app" / "static").resolve()
if base_prefix:
    app.mount(f"{base_prefix}/static", StaticFiles(directory=str(static_dir)), name="prefix_static")
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include Routers with base_prefix
app.include_router(api_v1_router, prefix=f"{base_prefix}/api/v1")
app.include_router(dashboard_router, prefix=f"{base_prefix}/dashboard", tags=["Dashboard"])

# Health Check endpoints (Supports dynamic prefix for Docker container healthcheck)
@app.get("/api/status", tags=["Health"])
async def root_health_check():
    return {
        "status": "healthy",
        "service": "vdstream",
        "prefix": base_prefix,
        "queue_active": queue_manager.is_running,
        "stream_active": stream_manager.is_running,
    }

if base_prefix:
    @app.get(f"{base_prefix}/api/status", tags=["Health"])
    async def prefix_health_check():
        return {
            "status": "healthy",
            "service": "vdstream",
            "prefix": base_prefix,
            "queue_active": queue_manager.is_running,
            "stream_active": stream_manager.is_running,
        }



# Redirects to Dashboard
@app.get("/", include_in_schema=False)
async def root_redirect():
    target = f"{base_prefix}/dashboard" if base_prefix else "/dashboard"
    return RedirectResponse(url=target)

if base_prefix:
    @app.get(base_prefix, include_in_schema=False)
    @app.get(f"{base_prefix}/", include_in_schema=False)
    async def prefix_redirect():
        return RedirectResponse(url=f"{base_prefix}/dashboard")

