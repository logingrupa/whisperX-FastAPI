"""TUS protocol upload router for chunked file uploads.

Provides a TUS-compliant upload endpoint at /uploads/files/ using tuspyserver.
Supports resumable uploads up to 5GB with automatic expiry cleanup.
On upload completion, triggers transcription via UploadSessionService.
"""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends
from tuspyserver import create_tus_router

from app.api.dependencies import get_task_repository
from app.core.logging import logger
from app.core.upload_config import UPLOAD_DIR
from app.domain.repositories.task_repository import ITaskRepository
from app.services.upload_session_service import UploadSessionService

# TUS-specific storage directory (separate from streaming uploads)
TUS_UPLOAD_DIR: Path = UPLOAD_DIR / "tus"


async def create_upload_complete_hook(
    background_tasks: BackgroundTasks,
    repository: ITaskRepository = Depends(get_task_repository),
):
    """FastAPI dependency that provides the TUS upload completion handler.

    tuspyserver resolves this via FastAPI's DI system, injecting
    BackgroundTasks and the task repository automatically.

    Args:
        background_tasks: FastAPI background tasks for scheduling transcription.
        repository: Task repository from DI container.

    Returns:
        Async handler function matching tuspyserver's expected signature.
    """
    service = UploadSessionService(repository)

    async def handler(file_path: str, metadata: dict) -> None:
        """Handle TUS upload completion by triggering transcription.

        Args:
            file_path: Path to the assembled file on disk.
            metadata: TUS client metadata dict.
        """
        logger.info("TUS upload complete: %s, triggering transcription", file_path)
        await service.start_transcription(file_path, metadata, background_tasks)

    return handler


# Create TUS protocol router via tuspyserver
tus_router: APIRouter = create_tus_router(
    prefix="files",
    files_dir=str(TUS_UPLOAD_DIR),
    max_size=5 * 1024 * 1024 * 1024,  # 5GB max (matches MAX_FILE_SIZE)
    days_to_keep=1,
    upload_complete_dep=create_upload_complete_hook,
)

# Wrapper router with /uploads prefix for mounting in main app
tus_upload_router: APIRouter = APIRouter(
    prefix="/uploads",
    tags=["TUS Upload"],
)
tus_upload_router.include_router(tus_router)
