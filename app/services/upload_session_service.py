"""Service bridging TUS upload completion to the transcription pipeline.

Handles file validation, task creation, and background transcription scheduling
when a TUS chunked upload completes. This is the single integration point between
tuspyserver's upload completion hook and the existing speech-to-text pipeline.
"""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks

from app.audio import get_audio_duration, process_audio_file
from app.core.logging import logger
from app.domain.entities.task import Task as DomainTask
from app.domain.repositories.task_repository import ITaskRepository
from app.infrastructure.storage.magic_validator import validate_magic_bytes
from app.schemas import (
    AlignmentParams,
    ASROptions,
    DiarizationParams,
    SpeechToTextProcessingParams,
    TaskStatus,
    TaskType,
    VADOptions,
    WhisperModelParams,
)
from app.services.whisperx_wrapper_service import process_audio_common


class UploadSessionService:
    """Bridges TUS upload completion to the existing transcription pipeline.

    Responsibilities:
        - Validate assembled file via magic bytes
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

    async def start_transcription(
        self,
        file_path: str,
        metadata: dict,
        background_tasks: BackgroundTasks,
    ) -> str:
        """Validate an assembled file and schedule transcription.

        Called by the TUS upload completion hook after all chunks are assembled.
        Returns quickly after scheduling -- transcription runs in the background.

        Args:
            file_path: Absolute path to the assembled file on disk.
            metadata: TUS client metadata dict (expects 'filename', optionally 'language').
            background_tasks: FastAPI BackgroundTasks for scheduling work.

        Returns:
            The task identifier string (UUID).

        Raises:
            ValueError: If magic bytes validation fails.
            Exception: If audio loading or task creation fails (re-raised after logging).
        """
        try:
            # 1. Derive extension and validate magic bytes
            filename = metadata.get("filename", Path(file_path).name)
            extension = Path(filename).suffix
            is_valid, message, _ = validate_magic_bytes(Path(file_path), extension)
            if not is_valid:
                raise ValueError(f"Invalid file type: magic bytes validation failed - {message}")

            # 2. Load audio and measure duration
            audio = process_audio_file(file_path)
            audio_duration = get_audio_duration(audio)
            logger.info(
                "TUS upload audio loaded: %s, duration: %.2fs",
                filename,
                audio_duration,
            )

            # 3. Create domain task (use client-provided taskId if available)
            language = metadata.get("language", "auto")
            task_id = metadata.get("taskId") or str(uuid4())
            task = DomainTask(
                uuid=task_id,
                status=TaskStatus.processing,
                file_name=filename,
                audio_duration=audio_duration,
                language=language,
                task_type=TaskType.full_process,
                start_time=datetime.now(tz=timezone.utc),
            )

            identifier = self._repository.add(task)
            logger.info("TUS upload task created: ID %s for file %s", identifier, filename)

            # 4. Build processing params with defaults
            model_params = WhisperModelParams()
            if language and language != "auto":
                model_params.language = language

            params = SpeechToTextProcessingParams(
                audio=audio,
                identifier=identifier,
                vad_options=VADOptions(),
                asr_options=ASROptions(),
                whisper_model_params=model_params,
                alignment_params=AlignmentParams(),
                diarization_params=DiarizationParams(),
                callback_url=None,
            )

            # 5. Schedule background transcription (non-blocking)
            background_tasks.add_task(process_audio_common, params)
            logger.info("Background transcription scheduled for task %s", identifier)

            return identifier

        except ValueError:
            raise
        except Exception:
            logger.error(
                "Failed to start transcription for TUS upload: %s",
                file_path,
                exc_info=True,
            )
            raise
