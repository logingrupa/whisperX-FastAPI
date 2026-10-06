"""Service bridging TUS upload completion to the transcription pipeline.

Handles file validation, the free-tier gate, task creation, and background
transcription scheduling when a TUS chunked upload completes. This is the
single integration point between tuspyserver's upload completion hook and the
existing speech-to-text pipeline.
"""

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import BackgroundTasks

from app.audio import probe_audio_duration
from app.core.config import get_settings
from app.core.exceptions import ApplicationError
from app.core.logging import logger
from app.domain.entities.task import Task as DomainTask
from app.domain.entities.user import User
from app.domain.repositories.task_repository import ITaskRepository
from app.infrastructure.storage.magic_validator import validate_magic_bytes
from app.schemas import (
    AlignmentParams,
    ASROptions,
    DiarizationParams,
    InterpolateMethod,
    SpeechToTextProcessingParams,
    TaskEnum,
    TaskStatus,
    TaskType,
    VADOptions,
    WhisperModelParams,
)
from app.services.free_tier_gate import FreeTierGate
from app.services.task_submission_service import FreeTierAdmission
from app.services.whisperx_wrapper_service import process_audio_common


class UploadSessionService:
    """Bridges TUS upload completion to the existing transcription pipeline.

    Responsibilities:
        - Validate assembled file via magic bytes
        - Run FreeTierGate, as the multipart submit routes do
        - Create a domain task for tracking
        - Schedule background transcription via process_audio_common

    This service does NOT handle TUS protocol logic or chunk assembly.
    """

    def __init__(self, repository: ITaskRepository) -> None:
        """Initialize with a task repository for persistence.

        Args:
            repository: Task repository for creating and persisting tasks.
        """
        self._repository = repository

    def start_transcription(
        self,
        file_path: str,
        metadata: dict,
        background_tasks: BackgroundTasks,
        *,
        gate: FreeTierGate,
        user: User,
        unlimited: bool,
        api_key_id: int | None,
    ) -> str:
        """Validate an assembled file, gate it, and schedule transcription.

        Called by the TUS upload completion hook (in the threadpool) after all
        chunks are assembled. Reads the duration with ffprobe and returns after
        scheduling; decoding and transcription run in the background job. A
        gate rejection propagates to the final PATCH response (403/402/429)
        and the upload is deleted.

        Args:
            file_path: Absolute path to the assembled file on disk.
            metadata: TUS client metadata dict (expects 'filename', optionally
                'language' and a client-generated 'taskId').
            background_tasks: FastAPI BackgroundTasks for scheduling work.
            gate: FreeTierGate bound to the request's rate-limit store.
            user: The authenticated uploader.
            unlimited: True when the request used an unlimited API key.
            api_key_id: The API key that authenticated the request, if any.

        Returns:
            The task identifier string (UUID).

        Raises:
            ValueError: If magic bytes validation fails.
            ApplicationError: If the free-tier gate rejects the upload.
        """
        if user.id is None:
            raise ValueError("TUS upload completion requires an authenticated user")
        try:
            filename = metadata.get("filename", Path(file_path).name)
            audio_path = _validated_upload_path(file_path, filename)
            model_params = _model_params(metadata.get("language", "auto"))
            audio_duration = probe_audio_duration(audio_path)
            logger.info("TUS upload probed: %s, duration: %.2fs", filename, audio_duration)
            admission = FreeTierAdmission(
                gate=gate,
                user=user,
                model=model_params.model.value,
                diarize=False,
                unlimited=unlimited,
            )
            _admit_or_discard(admission, audio_duration, audio_path)
            task = DomainTask(
                uuid=_task_identifier(metadata),
                status=TaskStatus.processing,
                file_name=filename,
                audio_duration=audio_duration,
                language=metadata.get("language", "auto"),
                task_type=TaskType.full_process,
                start_time=datetime.now(tz=timezone.utc),
                user_id=int(user.id),
                api_key_id=api_key_id,
            )
            return self._create_and_schedule(
                task, audio_path, model_params, admission, background_tasks
            )
        except (ValueError, ApplicationError):
            raise
        except Exception:
            logger.error(
                "Failed to start transcription for TUS upload: %s",
                file_path,
                exc_info=True,
            )
            raise

    def _create_and_schedule(
        self,
        task: DomainTask,
        audio_path: str,
        model_params: WhisperModelParams,
        admission: FreeTierAdmission,
        background_tasks: BackgroundTasks,
    ) -> str:
        """Persist the task and queue the full pipeline; refund the gate on failure."""
        assert task.audio_duration is not None
        try:
            identifier = self._repository.add(task)
            background_tasks.add_task(
                process_audio_common,
                _processing_params(audio_path, identifier, model_params),
            )
        except Exception:
            admission.refund(task.audio_duration)
            raise
        logger.info("TUS upload task created and scheduled: ID %s for file %s", identifier, task.file_name)
        return identifier


def _validated_upload_path(file_path: str, filename: str) -> str:
    """Check the magic bytes, then give the TUS file its original extension.

    TUS stores the upload under its hash ID with no extension; ffmpeg and the
    extension checks downstream need one.
    """
    extension = Path(filename).suffix
    is_valid, message, _ = validate_magic_bytes(Path(file_path), extension)
    if not is_valid:
        raise ValueError(f"Invalid file type: magic bytes validation failed - {message}")
    renamed_path = str(Path(file_path).parent / (Path(file_path).name + extension))
    shutil.move(file_path, renamed_path)
    logger.info("Renamed TUS file: %s -> %s", file_path, renamed_path)
    return renamed_path


def _admit_or_discard(
    admission: FreeTierAdmission, audio_duration: float, audio_path: str
) -> None:
    """Run the gate; a rejected upload is deleted, not left in the TUS dir."""
    try:
        admission.check(audio_duration)
    except Exception:
        os.remove(audio_path)
        raise


def tus_whisper_model() -> str:
    """The model every TUS upload runs (the server default; TUS sends none)."""
    return get_settings().whisper.WHISPER_MODEL.value


def _task_identifier(metadata: dict) -> str:
    """The client's taskId when it is a real UUID, otherwise a fresh one.

    The SPA pre-generates a UUID so it can subscribe to progress before the
    upload finishes; anything else must not become a task identifier.
    """
    client_task_id = metadata.get("taskId")
    if not client_task_id:
        return str(uuid4())
    try:
        return str(UUID(client_task_id))
    except ValueError:
        logger.warning("TUS taskId %r is not a UUID; using a server-generated id", client_task_id)
        return str(uuid4())


def _model_params(language: str) -> WhisperModelParams:
    """Whisper params for a TUS upload.

    All schema classes use Field(Query(...)) for FastAPI DI, but Query objects
    don't resolve to actual values when constructed directly, so every field is
    explicit. Model/device/compute come from settings, NOT literals: a
    hardcoded WhisperModel.tiny once downgraded every TUS upload to the tiny
    model for any language without a LANGUAGE_MODEL_OVERRIDES entry.
    """
    whisper_settings = get_settings().whisper
    return WhisperModelParams(
        language=language if language and language != "auto" else "en",
        task=TaskEnum.TRANSCRIBE,
        model=whisper_settings.WHISPER_MODEL,
        device=whisper_settings.DEVICE,
        device_index=0,
        threads=0,
        batch_size=8,
        chunk_size=20,
        compute_type=whisper_settings.COMPUTE_TYPE,
    )


def _processing_params(
    audio_path: str, identifier: str, model_params: WhisperModelParams
) -> SpeechToTextProcessingParams:
    """Full-pipeline params with the explicit defaults the TUS path has always used."""
    return SpeechToTextProcessingParams(
        audio_path=audio_path,
        identifier=identifier,
        vad_options=VADOptions(vad_onset=0.5, vad_offset=0.363),
        asr_options=ASROptions(
            beam_size=5,
            best_of=5,
            patience=1.0,
            length_penalty=1.0,
            temperatures=0.0,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
            initial_prompt=None,
            suppress_tokens=[-1],
            suppress_numerals=False,
            hotwords=None,
        ),
        whisper_model_params=model_params,
        alignment_params=AlignmentParams(
            align_model=None,
            interpolate_method=InterpolateMethod.nearest,
            return_char_alignments=False,
        ),
        diarization_params=DiarizationParams(
            min_speakers=None,
            max_speakers=None,
        ),
        callback_url=None,
    )
