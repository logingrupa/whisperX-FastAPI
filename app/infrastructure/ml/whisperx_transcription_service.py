"""WhisperX implementation of transcription service."""

from typing import Any

import numpy as np
import torch
from whisperx import load_model

from app.core.config import get_settings
from app.core.logging import logger
from app.infrastructure.ml.model_registry import _opts_hash, lease


class WhisperXTranscriptionService:
    """
    WhisperX-based implementation of transcription service.

    This service wraps the WhisperX library to provide transcription
    functionality following the ITranscriptionService interface contract.
    Model residency is owned by model_registry — the pipeline is leased
    per call and stays warm in VRAM across jobs.
    """

    def __init__(self) -> None:
        """Initialize the transcription service."""
        self.logger = logger

    def transcribe(
        self,
        audio: np.ndarray[Any, np.dtype[np.float32]],
        task: str,
        asr_options: dict[str, Any],
        vad_options: dict[str, Any],
        language: str,
        batch_size: int,
        chunk_size: int,
        model: str,
        device: str,
        device_index: int,
        compute_type: str,
        threads: int,
    ) -> dict[str, Any]:
        """
        Transcribe audio using WhisperX model.

        Args:
            audio: Audio data as numpy array (float32)
            task: Transcription task type ('transcribe' or 'translate')
            asr_options: ASR model options
            vad_options: Voice Activity Detection options
            language: Language code for transcription
            batch_size: Batch size for processing
            chunk_size: Chunk size for processing
            model: Model name/size to use
            device: Device to use ('cpu' or 'cuda')
            device_index: Device index for multi-GPU setups
            compute_type: Computation precision ('float16', 'int8', etc.)
            threads: Number of threads to use

        Returns:
            Dictionary containing transcription results
        """
        self.logger.debug(
            "Starting transcription with Whisper model: %s on device: %s",
            model,
            device,
        )

        # Set thread count
        faster_whisper_threads = 4
        if threads > 0:
            torch.set_num_threads(threads)
            faster_whisper_threads = threads

        # Resolve language-specific model override (e.g. fine-tuned Latvian model)
        settings = get_settings()
        resolved_model, resolved_compute = settings.whisper.resolve_model_for_language(
            model, language
        )
        if resolved_model != model:
            self.logger.info(
                "Language override active: language=%s, model=%s -> %s, compute=%s -> %s",
                language, model, resolved_model, compute_type, resolved_compute,
            )
            model = resolved_model
            compute_type = resolved_compute

        self.logger.debug(
            "Leasing model with config - model: %s, device: %s, compute_type: %s, "
            "threads: %d, task: %s, language: %s",
            model,
            device,
            compute_type,
            faster_whisper_threads,
            task,
            language,
        )

        # Cache key uses the RESOLVED model + compute_type (override applied
        # above). asr/vad options are baked into the pipeline at load time,
        # so they participate in the key. The VAD model rides inside the
        # cached pipeline — cached for free.
        cache_key = (
            "whisper",
            model,
            device,
            device_index,
            compute_type,
            language,
            task,
            faster_whisper_threads,
            _opts_hash(asr_options),
            _opts_hash(vad_options),
        )
        with lease(
            cache_key,
            loader=lambda: load_model(
                model,
                device,
                device_index=device_index,
                compute_type=compute_type,
                asr_options=asr_options,
                vad_options=vad_options,
                language=language,
                task=task,
                threads=faster_whisper_threads,
            ),
        ) as loaded_model:
            result = loaded_model.transcribe(
                audio=audio,
                batch_size=batch_size,
                chunk_size=chunk_size,
                language=language,
            )

        self.logger.debug("Completed transcription")
        return result  # type: ignore[no-any-return]
