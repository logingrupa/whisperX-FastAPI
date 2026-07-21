"""WhisperX implementation of alignment service."""

from typing import Any

import numpy as np
from whisperx import align, load_align_model

from app.core.logging import logger
from app.infrastructure.ml.model_registry import lease


class WhisperXAlignmentService:
    """
    WhisperX-based implementation of alignment service.

    This service wraps the WhisperX alignment functionality to align
    transcripts to audio with precise word-level timestamps. Model
    residency is owned by model_registry — the (model, metadata) pair is
    leased per call and stays warm in VRAM across jobs.
    """

    def __init__(self) -> None:
        """Initialize the alignment service."""
        self.logger = logger

    def align(
        self,
        transcript: list[dict[str, Any]],
        audio: np.ndarray[Any, np.dtype[np.float32]],
        language_code: str,
        device: str,
        align_model: str | None = None,
        interpolate_method: str = "nearest",
        return_char_alignments: bool = False,
    ) -> dict[str, Any]:
        """
        Align transcript to audio using WhisperX alignment.

        Args:
            transcript: List of transcript segments to align
            audio: Audio data as numpy array (float32)
            language_code: Language code of the transcript
            device: Device to use ('cpu' or 'cuda')
            align_model: Specific alignment model to use (optional)
            interpolate_method: Method for handling non-aligned words
            return_char_alignments: Whether to return character-level alignments

        Returns:
            Dictionary containing aligned transcript
        """
        self.logger.debug(
            "Starting alignment for language code: %s on device: %s",
            language_code,
            device,
        )

        self.logger.debug(
            "Leasing align model with config - language_code: %s, device: %s, "
            "interpolate_method: %s, return_char_alignments: %s",
            language_code,
            device,
            interpolate_method,
            return_char_alignments,
        )

        cache_key = ("align", language_code, device, align_model)
        with lease(
            cache_key,
            loader=lambda: load_align_model(
                language_code=language_code, device=device, model_name=align_model
            ),
        ) as (align_model_loaded, align_metadata):
            result = align(
                transcript,
                align_model_loaded,
                align_metadata,
                audio,
                device,
                interpolate_method=interpolate_method,
                return_char_alignments=return_char_alignments,
            )

        self.logger.debug("Completed alignment")
        return result  # type: ignore[no-any-return]
