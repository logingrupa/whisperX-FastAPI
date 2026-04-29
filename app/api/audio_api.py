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
    get_authenticated_user,
    get_file_service,
    get_free_tier_gate,
    get_scoped_task_repository,
)
from app.audio import get_audio_duration, process_audio_file
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

from app.api.callbacks import task_callback_router
from app.callbacks import validate_callback_url_dependency


# Configure logging
logging.basicConfig(level=logging.INFO)

stt_router = APIRouter()


@stt_router.post("/speech-to-text", tags=["Speech-2-Text"])
async def speech_to_text(
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
    user: User = Depends(get_authenticated_user),
    free_tier_gate: FreeTierGate = Depends(get_free_tier_gate),
) -> Response:
    """
    Process an uploaded audio file for speech-to-text conversion.

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
        Response: Confirmation message of task queuing.
    """
    logger.info("Received file upload request: %s", file.filename)

    # Validate file using file service
    if file.filename is None:
        raise FileValidationError(filename="unknown", reason="Filename is missing")

    file_service.validate_file_extension(file.filename, ALLOWED_EXTENSIONS)

    # Save file using file service
    temp_file = file_service.save_upload(file)
    logger.info("%s saved as temporary file: %s", file.filename, temp_file)

    # Process audio
    audio = process_audio_file(temp_file)
    audio_duration = get_audio_duration(audio)
    logger.info("Audio file %s length: %s seconds", file.filename, audio_duration)

    # Phase 13-08 free-tier gate (RATE-01..10): rate, trial, file, model,
    # diarize, daily, concurrency — fail-fast. Slot is held until
    # process_audio_common completion try/finally releases it (W1).
    free_tier_gate.check(
        user=user,
        file_seconds=audio_duration,
        model=model_params.model.value,
        diarize=diarize_params.diarize,
    )

    # Create domain task
    task = DomainTask(
        uuid=str(uuid4()),
        status=TaskStatus.processing,
        file_name=file.filename,
        audio_duration=audio_duration,
        language=model_params.language,
        task_type=TaskType.full_process,
        task_params={
            **model_params.model_dump(),
            **align_params.model_dump(),
            "asr_options": asr_options_params.model_dump(),
            "vad_options": vad_options_params.model_dump(),
            **diarize_params.model_dump(),
        },
        callback_url=callback_url,
        start_time=datetime.now(tz=timezone.utc),
        user_id=int(user.id) if user.id is not None else None,
    )

    identifier = repository.add(task)
    logger.info("Task added to database: ID %s", identifier)

    audio_params = SpeechToTextProcessingParams(
        audio=audio,
        identifier=identifier,
        vad_options=vad_options_params,
        asr_options=asr_options_params,
        whisper_model_params=model_params,
        alignment_params=align_params,
        diarization_params=diarize_params,
        callback_url=callback_url,
    )

    background_tasks.add_task(process_audio_common, audio_params)
    logger.info("Background task scheduled for processing: ID %s", identifier)

    return Response(identifier=identifier, message="Task queued")


@stt_router.post(
    "/speech-to-text-url", callbacks=task_callback_router.routes, tags=["Speech-2-Text"]
)
async def speech_to_text_url(
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
    user: User = Depends(get_authenticated_user),
    free_tier_gate: FreeTierGate = Depends(get_free_tier_gate),
) -> Response:
    """
    Process an audio file from a URL for speech-to-text conversion.

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
        Response: Confirmation message of task queuing.
    """
    logger.info("Received URL for processing: %s", url)

    # Download file using file service
    temp_audio_file, filename = file_service.download_from_url(url)
    logger.info("File downloaded and saved temporarily: %s", temp_audio_file)

    # Validate extension
    file_service.validate_file_extension(temp_audio_file, ALLOWED_EXTENSIONS)

    # Process audio
    audio = process_audio_file(temp_audio_file)
    audio_duration = get_audio_duration(audio)
    logger.info("Audio file processed: duration %s seconds", audio_duration)

    # Phase 13-08 free-tier gate (RATE-01..10) — same fail-fast contract
    # as /speech-to-text. Slot released by process_audio_common finally.
    free_tier_gate.check(
        user=user,
        file_seconds=audio_duration,
        model=model_params.model.value,
        diarize=diarize_params.diarize,
    )

    # Create domain task
    task = DomainTask(
        uuid=str(uuid4()),
        status=TaskStatus.processing,
        file_name=filename,
        audio_duration=audio_duration,
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
    )

    identifier = repository.add(task)
    logger.info("Task added to database: ID %s", identifier)

    audio_params = SpeechToTextProcessingParams(
        audio=audio,
        identifier=identifier,
        vad_options=vad_options_params,
        asr_options=asr_options_params,
        whisper_model_params=model_params,
        alignment_params=align_params,
        diarization_params=diarize_params,
        callback_url=callback_url,
    )

    background_tasks.add_task(process_audio_common, audio_params)
    logger.info("Background task scheduled for processing: ID %s", identifier)

    return Response(identifier=identifier, message="Task queued")
