"""Main entry point for the FastAPI application."""

import asyncio
from collections.abc import AsyncGenerator

from app.core.warnings_filter import filter_warnings

filter_warnings()

import logging  # noqa: E402
import time  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

from dotenv import load_dotenv  # noqa: E402
from fastapi import FastAPI, status  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse, RedirectResponse  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.api import service_router, stt_router, task_router, websocket_router  # noqa: E402
from app.api.streaming_upload_api import streaming_upload_router  # noqa: E402
from app.api.tus_upload_api import tus_upload_router, TUS_UPLOAD_DIR  # noqa: E402
from app.api.exception_handlers import (  # noqa: E402
    domain_error_handler,
    generic_error_handler,
    infrastructure_error_handler,
    task_not_found_handler,
    validation_error_handler,
)
from app.core.config import Config  # noqa: E402
from app.core.container import Container  # noqa: E402
from app.core.exceptions import (  # noqa: E402
    DomainError,
    InfrastructureError,
    TaskNotFoundError,
    ValidationError,
)
from app.docs import generate_db_schema, save_openapi_json  # noqa: E402
from app.infrastructure.scheduler import start_cleanup_scheduler, stop_cleanup_scheduler  # noqa: E402
from app.infrastructure.database import Base, engine  # noqa: E402
from app.infrastructure.websocket import set_main_loop  # noqa: E402
from app.spa_handler import setup_spa_routes  # noqa: E402

# Load environment variables from .env
load_dotenv()

Base.metadata.create_all(bind=engine)

# Create dependency injection container
container = Container()

# Set container in dependencies module
from app.api import dependencies  # noqa: E402

dependencies.set_container(container)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Lifespan context manager for the FastAPI application.

    This function is used to perform startup and shutdown tasks for the FastAPI application.
    It saves the OpenAPI JSON and generates the database schema.

    Args:
        app (FastAPI): The FastAPI application instance.
    """
    # Store main event loop for WebSocket progress emission from background tasks
    set_main_loop(asyncio.get_running_loop())

    # Ensure TUS upload directory exists
    TUS_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    logging.info("Application lifespan started - dependency container initialized")

    save_openapi_json(app)
    generate_db_schema(Base.metadata.tables.values())
    start_cleanup_scheduler()
    yield
    stop_cleanup_scheduler()

    # Clean up container on shutdown
    logging.info("Shutting down application")


tags_metadata = [
    {
        "name": "Speech-2-Text",
        "description": "Operations related to transcript",
    },
    {
        "name": "Speech-2-Text services",
        "description": "Individual services for transcript",
    },
    {
        "name": "Tasks Management",
        "description": "Manage tasks.",
    },
    {
        "name": "TUS Upload",
        "description": "TUS protocol resumable upload endpoints for chunked file uploads",
    },
    {
        "name": "Health",
        "description": "Health check endpoints to monitor application status",
    },
]


app = FastAPI(
    title="whisperX REST service",
    description=f"""
    # whisperX RESTful API

    Welcome to the whisperX RESTful API! This API provides a suite of audio processing services to enhance and analyze your audio content.

    ## Documentation:

    For detailed information on request and response formats, consult the [WhisperX Documentation](https://github.com/m-bain/whisperX).

    ## Services:

    Speech-2-Text provides a suite of audio processing services to enhance and analyze your audio content. The following services are available:

    1. Transcribe: Transcribe an audio/video  file into text.
    2. Align: Align the transcript to the audio/video file.
    3. Diarize: Diarize an audio/video file into speakers.
    4. Combine Transcript and Diarization: Combine the transcript and diarization results.

    ## Supported file extensions:
    AUDIO_EXTENSIONS = {Config.AUDIO_EXTENSIONS}

    VIDEO_EXTENSIONS = {Config.VIDEO_EXTENSIONS}

    """,
    version="0.0.1",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

# TUS protocol headers that must be exposed via CORS for browser clients
TUS_HEADERS: list[str] = [
    "Location",
    "Upload-Offset",
    "Upload-Length",
    "Tus-Resumable",
    "Tus-Version",
    "Tus-Extension",
    "Tus-Max-Size",
    "Upload-Expires",
]

# CORS middleware - must be added before routers for TUS header exposure
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=TUS_HEADERS,
)

# Register exception handlers
app.add_exception_handler(TaskNotFoundError, task_not_found_handler)
app.add_exception_handler(ValidationError, validation_error_handler)
app.add_exception_handler(DomainError, domain_error_handler)
app.add_exception_handler(InfrastructureError, infrastructure_error_handler)
app.add_exception_handler(Exception, generic_error_handler)

# Include routers
app.include_router(stt_router)
app.include_router(task_router)
app.include_router(service_router)
app.include_router(websocket_router)
app.include_router(streaming_upload_router)
app.include_router(tus_upload_router)


@app.get("/", include_in_schema=False)
async def index() -> RedirectResponse:
    """Redirect to the documentation."""
    return RedirectResponse(url="/docs", status_code=307)


# Health check endpoints
@app.get("/health", tags=["Health"], summary="Simple health check")
async def health_check() -> JSONResponse:
    """Verify the service is up and running.

    Returns a simple status response to confirm the API service is operational.
    """
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "ok", "message": "Service is running"},
    )


@app.get("/health/live", tags=["Health"], summary="Liveness check")
async def liveness_check() -> JSONResponse:
    """Check if the application is running.

    Used by orchestration systems like Kubernetes to detect if the app is alive.
    Returns timestamp along with status information.
    """
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "ok",
            "timestamp": time.time(),
            "message": "Application is live",
        },
    )


@app.get("/health/ready", tags=["Health"], summary="Readiness check")
async def readiness_check() -> JSONResponse:
    """Check if the application is ready to accept requests.

    Verifies dependencies like the database are connected and ready.
    Returns HTTP 200 if all systems are operational, HTTP 503 if any dependency
    has failed.
    """
    try:
        # Check database connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "ok",
                "database": "connected",
                "message": "Application is ready to accept requests",
            },
        )
    except Exception:
        logging.exception("Readiness check failed:")

        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "error",
                "database": "disconnected",
                "message": "Application is not ready due to an internal error.",
            },
        )


# Setup SPA routes (must be last - catch-all for client-side routing)
setup_spa_routes(app)
