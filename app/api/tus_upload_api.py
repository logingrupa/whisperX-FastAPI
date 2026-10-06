"""TUS protocol upload router for chunked file uploads.

Provides a TUS-compliant upload endpoint at /uploads/files/ using tuspyserver.
Supports resumable uploads up to 5GB with automatic expiry cleanup.
On upload completion, runs the free-tier gate and triggers transcription via
UploadSessionService.
"""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends
from starlette.concurrency import run_in_threadpool
from tuspyserver import create_tus_router

from app.api.dependencies import (
    authenticated_user,
    current_api_key_id,
    current_api_key_unlimited,
    get_free_tier_gate,
    get_scoped_task_repository,
)
from app.core.logging import logger
from app.core.upload_config import UPLOAD_DIR
from app.domain.entities.user import User
from app.domain.repositories.task_repository import ITaskRepository
from app.services.free_tier_gate import FreeTierGate
from app.services.upload_session_service import UploadSessionService, tus_whisper_model

# TUS-specific storage directory (separate from streaming uploads)
TUS_UPLOAD_DIR: Path = UPLOAD_DIR / "tus"


async def create_upload_complete_hook(
    background_tasks: BackgroundTasks,
    repository: ITaskRepository = Depends(get_scoped_task_repository),
    user: User = Depends(authenticated_user),
    free_tier_gate: FreeTierGate = Depends(get_free_tier_gate),
    api_key_id: int | None = Depends(current_api_key_id),
    api_key_unlimited: bool = Depends(current_api_key_unlimited),
):
    """FastAPI dependency that provides the TUS upload completion handler.

    tuspyserver resolves this via FastAPI's DI system, injecting
    BackgroundTasks, the task repository and the caller's gate inputs.
    tuspyserver awaits the handler without catching, so a gate rejection
    becomes the final PATCH's 403/402/429 (the SPA's tusErrorClassifier
    maps those).

    Args:
        background_tasks: FastAPI background tasks for scheduling transcription.
        repository: Task repository from DI container.
        user: The authenticated uploader.
        free_tier_gate: FreeTierGate bound to the request's rate-limit store.
        api_key_id: The API key that authenticated the request, if any.
        api_key_unlimited: True when that key bypasses the gate.

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
        await run_in_threadpool(
            service.start_transcription,
            file_path,
            metadata,
            background_tasks,
            gate=free_tier_gate,
            user=user,
            unlimited=api_key_unlimited,
            api_key_id=api_key_id,
        )

    return handler


async def create_upload_precheck_hook(
    user: User = Depends(authenticated_user),
    free_tier_gate: FreeTierGate = Depends(get_free_tier_gate),
    api_key_unlimited: bool = Depends(current_api_key_unlimited),
):
    """FastAPI dependency that provides the TUS upload-creation check.

    Rejects (402/403) uploads the completion gate would refuse no matter
    their length, before the client sends a byte. Unlimited keys skip it.

    Args:
        user: The authenticated uploader.
        free_tier_gate: FreeTierGate bound to the request's rate-limit store.
        api_key_unlimited: True when the request's API key bypasses the gate.

    Returns:
        Handler matching tuspyserver's pre-create signature.
    """

    def handler(metadata: dict, upload_info: dict) -> None:
        if api_key_unlimited:
            return
        free_tier_gate.check_upload_allowed(user, tus_whisper_model())

    return handler


# Create TUS protocol router via tuspyserver
tus_router: APIRouter = create_tus_router(
    prefix="files",
    files_dir=str(TUS_UPLOAD_DIR),
    max_size=5 * 1024 * 1024 * 1024,  # 5GB max (matches MAX_FILE_SIZE)
    days_to_keep=1,
    pre_create_dep=create_upload_precheck_hook,
    upload_complete_dep=create_upload_complete_hook,
)

# Wrapper router with /uploads prefix for mounting in main app
tus_upload_router: APIRouter = APIRouter(
    prefix="/uploads",
    tags=["TUS Upload"],
)
tus_upload_router.include_router(tus_router)
