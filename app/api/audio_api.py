"""
This module contains the FastAPI routes for speech-to-text processing.

It includes endpoints for processing uploaded audio files and audio files from URLs.
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    UploadFile,
)

from app.api.dependencies import (
    authenticated_user,
    current_api_key_id,
    current_api_key_unlimited,
    get_free_tier_gate,
    get_scoped_task_repository,
)
from app.api.submission_response import submission_response
from app.core.services import get_file_service
from app.core.exceptions import FileValidationError
from app.core.logging import logger
from app.domain.entities.task import Task as DomainTask
from app.domain.entities.user import User
from app.domain.repositories.task_repository import ITaskRepository
from app.services.free_tier_gate import FreeTierGate
from app.files import ALLOWED_EXTENSIONS
from app.schemas import (
    AlignmentParams,
    ASROptions,
    DiarizationParams,
    Response,
    SpeechToTextProcessingParams,
    TaskStatus,
    TaskType,
    VADOptions,
    WhisperModelParams,
)
from app.services import process_audio_common
from app.services.file_service import FileService
from app.services.task_submission_service import (
    FreeTierAdmission,
    TaskSubmissionService,
)

from app.api.callbacks import task_callback_router
from app.callbacks import validate_callback_url_dependency


# Configure logging
logging.basicConfig(level=logging.INFO)

stt_router = APIRouter()


@stt_router.post("/speech-to-text", tags=["Speech-2-Text"])
def speech_to_text(
    background_tasks: BackgroundTasks,
    model_params: WhisperModelParams = Depends(),
    align_params: AlignmentParams = Depends(),
    diarize_params: DiarizationParams = Depends(),
    asr_options_params: ASROptions = Depends(),
    vad_options_params: VADOptions = Depends(),
    file: UploadFile = File(...),
    callback_url: str | None = Depends(validate_callback_url_dependency),
    repository: ITaskRepository = Depends(get_scoped_task_repository),
    file_service: FileService = Depends(get_file_service),
    user: User = Depends(authenticated_user),
    free_tier_gate: FreeTierGate = Depends(get_free_tier_gate),
    api_key_id: int | None = Depends(current_api_key_id),
    api_key_unlimited: bool = Depends(current_api_key_unlimited),
) -> Response:
    """
    Process an uploaded audio file for speech-to-text conversion.

    Sync ``def`` so FastAPI runs it in the threadpool: saving and hashing the
    upload never block the event loop. Decoding runs in the background job.

    Args:
        background_tasks (BackgroundTasks): Background tasks dependency.
        model_params (WhisperModelParams): Whisper model parameters.
        align_params (AlignmentParams): Alignment parameters.
        diarize_params (DiarizationParams): Diarization parameters.
        asr_options_params (ASROptions): ASR options parameters.
        vad_options_params (VADOptions): VAD options parameters.
        file (UploadFile): Uploaded audio file.
        callback_url (str | None): Optional URL to call back when processing is complete.
        repository (ITaskRepository): Task repository dependency.
        file_service (FileService): File service dependency.

    Returns:
        Response: The queued task, or the in-flight task an identical
        earlier submit created.
    """
    logger.info("Received file upload request: %s", file.filename)

    if file.filename is None:
        raise FileValidationError(filename="unknown", reason="Filename is missing")

    file_service.validate_file_extension(file.filename, ALLOWED_EXTENSIONS)

    audio_path = file_service.save_upload(file)
    logger.info("%s saved as temporary file: %s", file.filename, audio_path)

    return _submit_full_process(
        audio_path=audio_path,
        file_name=file.filename,
        url=None,
        callback_url=callback_url,
        model_params=model_params,
        align_params=align_params,
        diarize_params=diarize_params,
        asr_options_params=asr_options_params,
        vad_options_params=vad_options_params,
        background_tasks=background_tasks,
        repository=repository,
        user=user,
        free_tier_gate=free_tier_gate,
        api_key_id=api_key_id,
        api_key_unlimited=api_key_unlimited,
    )


@stt_router.post(
    "/speech-to-text-url", callbacks=task_callback_router.routes, tags=["Speech-2-Text"]
)
def speech_to_text_url(
    background_tasks: BackgroundTasks,
    model_params: WhisperModelParams = Depends(),
    align_params: AlignmentParams = Depends(),
    diarize_params: DiarizationParams = Depends(),
    asr_options_params: ASROptions = Depends(),
    vad_options_params: VADOptions = Depends(),
    url: str = Form(...),
    callback_url: str | None = Depends(validate_callback_url_dependency),
    repository: ITaskRepository = Depends(get_scoped_task_repository),
    file_service: FileService = Depends(get_file_service),
    user: User = Depends(authenticated_user),
    free_tier_gate: FreeTierGate = Depends(get_free_tier_gate),
    api_key_id: int | None = Depends(current_api_key_id),
    api_key_unlimited: bool = Depends(current_api_key_unlimited),
) -> Response:
    """
    Process an audio file from a URL for speech-to-text conversion.

    Sync ``def`` so FastAPI runs it in the threadpool: the download never
    blocks the event loop. Decoding runs in the background job.

    Args:
        background_tasks (BackgroundTasks): Background tasks dependency.
        model_params (WhisperModelParams): Whisper model parameters.
        align_params (AlignmentParams): Alignment parameters.
        diarize_params (DiarizationParams): Diarization parameters.
        asr_options_params (ASROptions): ASR options parameters.
        vad_options_params (VADOptions): VAD options parameters.
        url (str): URL of the audio file.
        callback_url (str | None): Optional URL to call back when processing is complete.
        repository (ITaskRepository): Task repository dependency.
        file_service (FileService): File service dependency.

    Returns:
        Response: The queued task, or the in-flight task an identical
        earlier submit created.
    """
    logger.info("Received URL for processing: %s", url)

    audio_path, filename = file_service.download_from_url(url)
    logger.info("File downloaded and saved temporarily: %s", audio_path)

    file_service.validate_file_extension(audio_path, ALLOWED_EXTENSIONS)

    return _submit_full_process(
        audio_path=audio_path,
        file_name=filename,
        url=url,
        callback_url=callback_url,
        model_params=model_params,
        align_params=align_params,
        diarize_params=diarize_params,
        asr_options_params=asr_options_params,
        vad_options_params=vad_options_params,
        background_tasks=background_tasks,
        repository=repository,
        user=user,
        free_tier_gate=free_tier_gate,
        api_key_id=api_key_id,
        api_key_unlimited=api_key_unlimited,
    )


def _submit_full_process(
    *,
    audio_path: str,
    file_name: str,
    url: str | None,
    callback_url: str | None,
    model_params: WhisperModelParams,
    align_params: AlignmentParams,
    diarize_params: DiarizationParams,
    asr_options_params: ASROptions,
    vad_options_params: VADOptions,
    background_tasks: BackgroundTasks,
    repository: ITaskRepository,
    user: User,
    free_tier_gate: FreeTierGate,
    api_key_id: int | None,
    api_key_unlimited: bool,
) -> Response:
    """Create (or match the in-flight twin of) a full-process task and queue it."""
    task = DomainTask(
        uuid=str(uuid4()),
        status=TaskStatus.processing,
        file_name=file_name,
        language=model_params.language,
        task_type=TaskType.full_process,
        task_params={
            **model_params.model_dump(),
            **align_params.model_dump(),
            "asr_options": asr_options_params.model_dump(),
            "vad_options": vad_options_params.model_dump(),
            **diarize_params.model_dump(),
        },
        url=url,
        callback_url=callback_url,
        start_time=datetime.now(tz=timezone.utc),
        user_id=int(user.id) if user.id is not None else None,
        api_key_id=api_key_id,
    )

    def schedule(identifier: str) -> None:
        background_tasks.add_task(
            process_audio_common,
            SpeechToTextProcessingParams(
                audio_path=audio_path,
                identifier=identifier,
                vad_options=vad_options_params,
                asr_options=asr_options_params,
                whisper_model_params=model_params,
                alignment_params=align_params,
                diarization_params=diarize_params,
                callback_url=callback_url,
            ),
        )

    # Phase 13-08 free-tier gate (RATE-01..10). `diarize` is True when the
    # caller set speaker bounds; DiarizationParams has no boolean flag.
    # Slot held until process_audio_common's finally releases it (W1).
    diarize_requested = (
        diarize_params.min_speakers is not None
        or diarize_params.max_speakers is not None
    )
    outcome = TaskSubmissionService(repository).submit(
        audio_path=audio_path,
        task=task,
        admission=FreeTierAdmission(
            gate=free_tier_gate,
            user=user,
            model=model_params.model.value,
            diarize=diarize_requested,
            unlimited=api_key_unlimited,
        ),
        schedule=schedule,
    )
    return submission_response(outcome)
