"""This module provides services for transcribing, diarizing, and aligning audio using Whisper and other models."""

import gc
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import torch
from whisperx import (
    align,
    load_align_model,
    load_model,
)
from whisperx.diarize import DiarizationPipeline

from app.callbacks import post_task_callback
from app.core.config import Config, get_settings
from app.core.logging import logger
from app.domain.entities.user import User
from app.domain.repositories.task_repository import ITaskRepository
from app.domain.services.alignment_service import IAlignmentService
from app.domain.services.diarization_service import IDiarizationService
from app.domain.services.speaker_assignment_service import ISpeakerAssignmentService
from app.domain.services.transcription_service import ITranscriptionService
from app.infrastructure.database.connection import SessionLocal
from app.infrastructure.database.repositories.sqlalchemy_task_repository import (
    SQLAlchemyTaskRepository,
)
from app.infrastructure.websocket import get_progress_emitter
from app.schemas import (
    AlignedTranscription,
    ComputeType,
    Device,
    Metadata,
    Result,
    SpeechToTextProcessingParams,
    TaskProgressStage,
    TaskStatus,
    WhisperModel,
)
from app.transcript import filter_aligned_transcription


def _update_progress(
    repository: ITaskRepository,
    identifier: str,
    stage: TaskProgressStage,
    percentage: int,
) -> None:
    """Update progress in database and emit to WebSocket clients."""
    # Update database for polling fallback
    repository.update(
        identifier=identifier,
        update_data={
            "progress_stage": stage.value,
            "progress_percentage": percentage,
        },
    )
    # Emit to WebSocket clients
    progress_emitter = get_progress_emitter()
    progress_emitter.emit_progress(identifier, stage, percentage)


def transcribe_with_whisper(
    audio: np.ndarray[Any, np.dtype[np.float32]],
    task: str,
    asr_options: dict[str, Any],
    vad_options: dict[str, Any],
    language: str,
    batch_size: int = 16,
    chunk_size: int = 20,
    model: WhisperModel = Config.WHISPER_MODEL,
    device: Device = Config.DEVICE,
    device_index: int = 0,
    compute_type: ComputeType = Config.COMPUTE_TYPE,
    threads: int = 0,
) -> dict[str, Any]:
    """
    Transcribe an audio file using the Whisper model.

    Args:
       audio (Audio): The audio to transcribe.
       batch_size (int): Batch size for transcription (default 16).
       chunk_size (int): Chunk size for transcription (default 20).
       model (WhisperModel): Name of the Whisper model to use.
       device (Device): Device to use for PyTorch inference.
       device_index (int): Device index to use for FasterWhisper inference.
       compute_type (ComputeType): Compute type for computation.

    Returns:
       Transcript: The transcription result.
    """
    logger.debug(
        "Starting transcription with Whisper model: %s on device: %s",
        model.value,
        device.value,
    )
    # Log GPU memory before loading model
    if torch.cuda.is_available():
        logger.debug(
            f"GPU memory before loading model - used: {torch.cuda.memory_allocated() / 1024**2:.2f} MB, available: {torch.cuda.get_device_properties(0).total_memory / 1024**2:.2f} MB"
        )
    faster_whisper_threads = 4
    if threads > 0:
        torch.set_num_threads(threads)
        faster_whisper_threads = threads

    # Resolve language-specific model override (e.g. fine-tuned Latvian model)
    settings = get_settings()
    resolved_model, resolved_compute = settings.whisper.resolve_model_for_language(
        model.value, language
    )
    if resolved_model != model.value:
        logger.info(
            "Language override active: language=%s, model=%s -> %s, compute=%s -> %s",
            language, model.value, resolved_model, compute_type.value, resolved_compute,
        )

    logger.debug(
        "Loading model with config - model: %s, device: %s, compute_type: %s, threads: %d, task: %s, language: %s",
        resolved_model,
        device.value,
        resolved_compute,
        faster_whisper_threads,
        task,
        language,
    )
    loaded_model = load_model(
        resolved_model,
        device.value,
        device_index=device_index,
        compute_type=resolved_compute,
        asr_options=asr_options,
        vad_options=vad_options,
        language=language,
        task=task,
        threads=faster_whisper_threads,
    )
    logger.debug("Transcription model loaded successfully")
    result = loaded_model.transcribe(
        audio=audio, batch_size=batch_size, chunk_size=chunk_size, language=language
    )

    # Log GPU memory before cleanup
    if torch.cuda.is_available():
        logger.debug(
            f"GPU memory before cleanup: {torch.cuda.memory_allocated() / 1024**2:.2f} MB, available: {torch.cuda.get_device_properties(0).total_memory / 1024**2:.2f} MB"
        )

    # delete model
    gc.collect()
    torch.cuda.empty_cache()
    del loaded_model

    # Log GPU memory after cleanup
    if torch.cuda.is_available():
        logger.debug(
            f"GPU memory after cleanup: {torch.cuda.memory_allocated() / 1024**2:.2f} MB, available: {torch.cuda.get_device_properties(0).total_memory / 1024**2:.2f} MB"
        )

    logger.debug("Completed transcription")
    return result  # type: ignore[no-any-return]


def diarize(
    audio: np.ndarray[Any, np.dtype[np.float32]],
    device: Device = Config.DEVICE,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> pd.DataFrame:
    """
    Diarize an audio file using the PyAnnotate model.

    Args:
       audio (Audio): The audio to diarize.
       device (Device): Device to use for PyTorch inference.

    Returns:
       Diarizartion: The diarization result.
    """
    logger.debug("Starting diarization with device: %s", device.value)

    # Log GPU memory before loading model
    if torch.cuda.is_available():
        logger.debug(
            f"GPU memory before loading model - used: {torch.cuda.memory_allocated() / 1024**2:.2f} MB, available: {torch.cuda.get_device_properties(0).total_memory / 1024**2:.2f} MB"
        )

    model = DiarizationPipeline(use_auth_token=Config.HF_TOKEN, device=device.value)
    result = model(audio=audio, min_speakers=min_speakers, max_speakers=max_speakers)

    # Log GPU memory before cleanup
    if torch.cuda.is_available():
        logger.debug(
            f"GPU memory before cleanup: {torch.cuda.memory_allocated() / 1024**2:.2f} MB, available: {torch.cuda.get_device_properties(0).total_memory / 1024**2:.2f} MB"
        )

    # delete model
    gc.collect()
    torch.cuda.empty_cache()
    del model

    # Log GPU memory after cleanup
    if torch.cuda.is_available():
        logger.debug(
            f"GPU memory after cleanup: {torch.cuda.memory_allocated() / 1024**2:.2f} MB, available: {torch.cuda.get_device_properties(0).total_memory / 1024**2:.2f} MB"
        )

    logger.debug("Completed diarization with device: %s", device.value)
    return result  # type: ignore[no-any-return]


def align_whisper_output(
    transcript: list[dict[str, Any]],
    audio: np.ndarray[Any, np.dtype[np.float32]],
    language_code: str,
    device: Device = Config.DEVICE,
    align_model: str | None = None,
    interpolate_method: str = "nearest",
    return_char_alignments: bool = False,
) -> dict[str, Any]:
    """
    Align the transcript to the original audio.

    Args:
       transcript: The text transcript.
       audio: The original audio.
       language_code: The language code.
       device (Device): Device to use for PyTorch inference.
       align_model: Name of phoneme-level ASR model to do alignment.
       interpolate_method: For word .srt, method to assign timestamps to non-aligned words, or merge them into neighboring.
       return_char_alignments: Whether to return character-level alignments in the output json file.

    Returns:
       The aligned transcript.
    """
    logger.debug(
        "Starting alignment for language code: %s on device: %s",
        language_code,
        device.value,
    )

    # Log GPU memory before loading model
    if torch.cuda.is_available():
        logger.debug(
            f"GPU memory before loading model - used: {torch.cuda.memory_allocated() / 1024**2:.2f} MB, available: {torch.cuda.get_device_properties(0).total_memory / 1024**2:.2f} MB"
        )

    logger.debug(
        "Loading align model with config - language_code: %s, device: %s, interpolate_method: %s, return_char_alignments: %s",
        language_code,
        device.value,
        interpolate_method,
        return_char_alignments,
    )
    align_model, align_metadata = load_align_model(
        language_code=language_code, device=device.value, model_name=align_model
    )

    result = align(
        transcript,
        align_model,
        align_metadata,
        audio,
        device.value,
        interpolate_method=interpolate_method,
        return_char_alignments=return_char_alignments,
    )

    # Log GPU memory before cleanup
    if torch.cuda.is_available():
        logger.debug(
            f"GPU memory before cleanup: {torch.cuda.memory_allocated() / 1024**2:.2f} MB, available: {torch.cuda.get_device_properties(0).total_memory / 1024**2:.2f} MB"
        )

    # delete model
    gc.collect()
    torch.cuda.empty_cache()
    del align_model
    del align_metadata

    # Log GPU memory after cleanup
    if torch.cuda.is_available():
        logger.debug(
            f"GPU memory after cleanup: {torch.cuda.memory_allocated() / 1024**2:.2f} MB, available: {torch.cuda.get_device_properties(0).total_memory / 1024**2:.2f} MB"
        )

    logger.debug("Completed alignment")
    return result  # type: ignore[no-any-return]


def _resolve_user_for_task(task_user_id: int | None) -> User | None:
    """Look up the User domain entity for a completed task (W1 release path).

    Returns None if the task has no owner (legacy unscoped path) or if
    DI/container is unavailable — in those cases there's no concurrency
    slot to release (free-tier gate never consumed one).
    """
    if task_user_id is None:
        return None
    try:
        from app.api.dependencies import _container

        if _container is None:
            return None
        # Factory-provided repo owns a fresh DB Session — close in finally
        # to keep the engine pool alive (see app/api/dependencies.py
        # ::get_task_repository for the failure mode).
        user_repo = _container.user_repository()
        try:
            return user_repo.get_by_id(task_user_id)
        finally:
            user_repo.session.close()
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning(
            "Failed to resolve user for task user_id=%s: %s", task_user_id, exc
        )
        return None


def process_audio_common(
    params: SpeechToTextProcessingParams,
    transcription_service: ITranscriptionService | None = None,
    alignment_service: IAlignmentService | None = None,
    diarization_service: IDiarizationService | None = None,
    speaker_service: ISpeakerAssignmentService | None = None,
) -> None:
    """
    Process an audio clip to generate a transcript with speaker labels.

    Args:
        params (SpeechToTextProcessingParams): The speech-to-text processing parameters
        transcription_service: Transcription service (defaults to WhisperX if None)
        alignment_service: Alignment service (defaults to WhisperX if None)
        diarization_service: Diarization service (defaults to WhisperX if None)
        speaker_service: Speaker assignment service (defaults to WhisperX if None)

    Returns:
        None: The result is saved in the transcription requests dict.

    Phase 13-08 W1: completion hook (success AND failure) writes a
    usage_events row and releases the user's concurrency slot via
    FreeTierGate.release_concurrency. Both wrapped in try/finally so a
    transcription crash never locks the user out indefinitely.
    """
    # Import here to avoid circular dependency
    from app.infrastructure.ml import (
        WhisperXAlignmentService,
        WhisperXDiarizationService,
        WhisperXSpeakerAssignmentService,
        WhisperXTranscriptionService,
    )

    # Use provided services or create default WhisperX implementations
    transcription_svc = transcription_service or WhisperXTranscriptionService()
    alignment_svc = alignment_service or WhisperXAlignmentService()
    diarization_svc = diarization_service or WhisperXDiarizationService(
        hf_token=Config.HF_TOKEN or ""
    )
    speaker_svc = speaker_service or WhisperXSpeakerAssignmentService()

    # Create repository for this background task
    session = SessionLocal()
    repository: ITaskRepository = SQLAlchemyTaskRepository(session)

    # Phase 13-08 — resolve DI services for usage_events + slot release.
    # Best-effort: if container is unavailable (test bypass) we degrade
    # gracefully. The W1 finally block tolerates None.
    free_tier_gate = None
    usage_writer = None
    try:
        from app.api.dependencies import _container

        if _container is not None:
            free_tier_gate = _container.free_tier_gate()
            usage_writer = _container.usage_event_writer()
    except Exception as exc:
        logger.warning("DI unavailable in process_audio_common: %s", exc)

    # Track success-only state for usage_events write
    transcription_succeeded = False
    duration_observed: float = 0.0
    task_user_id: int | None = None
    task_uuid: str = ""
    task_audio_duration: float = 0.0
    task_model: str = "unknown"

    # Initial progress: queued
    _update_progress(repository, params.identifier, TaskProgressStage.queued, 0)

    try:
        start_time = datetime.now()
        logger.info(
            "Starting speech-to-text processing for identifier: %s",
            params.identifier,
        )

        # Progress: starting transcription
        _update_progress(repository, params.identifier, TaskProgressStage.transcribing, 10)

        logger.debug(
            "Transcription parameters - task: %s, language: %s, batch_size: %d, chunk_size: %d, model: %s, device: %s, device_index: %d, compute_type: %s, threads: %d",
            params.whisper_model_params.task.value,
            params.whisper_model_params.language,
            params.whisper_model_params.batch_size,
            params.whisper_model_params.chunk_size,
            params.whisper_model_params.model.value,
            params.whisper_model_params.device.value,
            params.whisper_model_params.device_index,
            params.whisper_model_params.compute_type.value,
            params.whisper_model_params.threads,
        )

        segments_before_alignment = transcription_svc.transcribe(
            audio=params.audio,
            task=params.whisper_model_params.task.value,
            asr_options=params.asr_options.model_dump(),
            vad_options=params.vad_options.model_dump(),
            language=params.whisper_model_params.language,
            batch_size=params.whisper_model_params.batch_size,
            chunk_size=params.whisper_model_params.chunk_size,
            model=params.whisper_model_params.model.value,
            device=params.whisper_model_params.device.value,
            device_index=params.whisper_model_params.device_index,
            compute_type=params.whisper_model_params.compute_type.value,
            threads=params.whisper_model_params.threads,
        )

        # Progress: transcription complete, starting alignment
        _update_progress(repository, params.identifier, TaskProgressStage.aligning, 40)

        logger.debug(
            "Alignment parameters - align_model: %s, interpolate_method: %s, return_char_alignments: %s, language_code: %s",
            params.alignment_params.align_model,
            params.alignment_params.interpolate_method,
            params.alignment_params.return_char_alignments,
            segments_before_alignment["language"],
        )
        segments_transcript = alignment_svc.align(
            transcript=segments_before_alignment["segments"],
            audio=params.audio,
            language_code=segments_before_alignment["language"],
            device=params.whisper_model_params.device.value,
            align_model=params.alignment_params.align_model,
            interpolate_method=params.alignment_params.interpolate_method,
            return_char_alignments=params.alignment_params.return_char_alignments,
        )
        transcript = AlignedTranscription(**segments_transcript)
        # removing words within each segment that have missing start, end, or score values
        filtered_transcript = filter_aligned_transcription(transcript)
        transcript_dict = filtered_transcript.model_dump()

        # Progress: alignment complete, starting diarization
        _update_progress(repository, params.identifier, TaskProgressStage.diarizing, 60)

        logger.debug(
            "Diarization parameters - device: %s, min_speakers: %s, max_speakers: %s",
            params.whisper_model_params.device.value,
            params.diarization_params.min_speakers,
            params.diarization_params.max_speakers,
        )
        diarization_segments = diarization_svc.diarize(
            audio=params.audio,
            device=params.whisper_model_params.device.value,
            min_speakers=params.diarization_params.min_speakers,
            max_speakers=params.diarization_params.max_speakers,
        )

        # Progress: diarization complete, combining results
        _update_progress(repository, params.identifier, TaskProgressStage.diarizing, 80)

        logger.debug("Starting to combine transcript with diarization results")
        result = speaker_svc.assign_speakers(diarization_segments, transcript_dict)

        logger.debug("Completed combining transcript with diarization results")

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(
            "Completed speech-to-text processing for identifier: %s. Duration: %ss",
            params.identifier,
            duration,
        )

        # Progress: complete
        _update_progress(repository, params.identifier, TaskProgressStage.complete, 100)

        repository.update(
            identifier=params.identifier,
            update_data={
                "status": TaskStatus.completed,
                "result": result,
                "duration": duration,
                "start_time": start_time,
                "end_time": end_time,
            },
        )

        # Phase 13-08 success-path snapshot — usage_events written in finally
        transcription_succeeded = True
        duration_observed = duration

    except (RuntimeError, ValueError, KeyError) as e:
        logger.error(
            "Speech-to-text processing failed for identifier: %s. Error: %s",
            params.identifier,
            str(e),
        )
        # Emit error to WebSocket clients
        progress_emitter = get_progress_emitter()
        progress_emitter.emit_error(
            params.identifier,
            error_code="PROCESSING_FAILED",
            user_message="Transcription processing failed. Please try again.",
            technical_detail=str(e),
        )
        repository.update(
            identifier=params.identifier,
            update_data={
                "status": TaskStatus.failed,
                "error": str(e),
            },
        )

    except MemoryError as e:
        logger.error(
            f"Task failed for identifier {params.identifier} due to out of memory. Error: {str(e)}"
        )
        # Emit error to WebSocket clients
        progress_emitter = get_progress_emitter()
        progress_emitter.emit_error(
            params.identifier,
            error_code="PROCESSING_FAILED",
            user_message="Transcription processing failed due to memory constraints. Please try with a smaller file.",
            technical_detail=str(e),
        )
        repository.update(
            identifier=params.identifier,
            update_data={"status": TaskStatus.failed, "error": str(e)},
        )

    finally:
        # Capture per-task data needed for usage_events + slot release.
        # Single repo lookup serves callback + W1 release paths (DRT).
        completed_task = None
        try:
            completed_task = repository.get_by_id(params.identifier)
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                "Failed to load completed task %s: %s",
                params.identifier,
                exc,
            )

        if completed_task is not None:
            task_user_id = completed_task.user_id
            task_uuid = completed_task.uuid
            task_audio_duration = completed_task.audio_duration or 0.0
            params_dict = completed_task.task_params or {}
            model_value = params_dict.get("model", "unknown")
            task_model = (
                model_value.value if hasattr(model_value, "value") else str(model_value)
            )

        # Existing callback path — unchanged behavior, reusing completed_task.
        try:
            if params.callback_url and completed_task is not None:
                metadata = Metadata(
                    task_type=completed_task.task_type,
                    task_params=completed_task.task_params,
                    language=completed_task.language,
                    file_name=completed_task.file_name,
                    url=completed_task.url,
                    callback_url=completed_task.callback_url,
                    duration=completed_task.duration,
                    audio_duration=completed_task.audio_duration,
                    start_time=completed_task.start_time,
                    end_time=completed_task.end_time,
                )
                result_payload = Result(
                    status=completed_task.status,
                    result=completed_task.result,
                    metadata=metadata,
                    error=completed_task.error,
                )
                post_task_callback(params.callback_url, result_payload.model_dump())
        except Exception as e:
            logger.error(
                "Failed to send callback for identifier %s: %s",
                params.identifier,
                str(e),
            )

        # Phase 13-08 — write usage_events row on success-only path
        # (idempotent: duplicate task_uuid replays are silent no-ops).
        if (
            transcription_succeeded
            and usage_writer is not None
            and task_user_id is not None
            and task_uuid
        ):
            try:
                usage_writer.record(
                    user_id=task_user_id,
                    task_uuid=task_uuid,
                    gpu_seconds=duration_observed,
                    file_seconds=task_audio_duration,
                    model=task_model,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to record usage_events for task %s: %s",
                    params.identifier,
                    exc,
                )

        # Phase 13-08 W1 — ALWAYS release the concurrency slot (success
        # OR failure). Slot was consumed at transcribe-start by
        # FreeTierGate.check; without this release the user is locked
        # out of further transcribes until the bucket resets.
        if free_tier_gate is not None and task_user_id is not None:
            user_for_release = _resolve_user_for_task(task_user_id)
            if user_for_release is not None:
                try:
                    free_tier_gate.release_concurrency(user_for_release)
                except Exception as exc:
                    logger.warning(
                        "Failed to release concurrency slot user_id=%s task=%s: %s",
                        task_user_id,
                        params.identifier,
                        exc,
                    )

        # Close every Session checked out via Factory providers. Without
        # these closes the engine pool exhausts after a handful of
        # transcribe jobs (see app/api/dependencies.py::get_task_repository
        # for the failure mode).
        if free_tier_gate is not None:
            free_tier_gate.rate_limit_service.repository.session.close()
        if usage_writer is not None:
            usage_writer.session.close()
        session.close()
