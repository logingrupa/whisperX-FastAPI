"""WhisperX implementation of diarization service."""

from typing import Any

import numpy as np
import pandas as pd
from whisperx.diarize import DiarizationPipeline

from app.core.exceptions import DiarizationFailedError
from app.core.logging import logger
from app.infrastructure.ml.model_registry import lease

# Pin the model explicitly: whisperX main defaults to
# pyannote/speaker-diarization-community-1, which is gated and NOT what we
# validated. 3.1 runs fine under pyannote.audio 4.x, but 4.x eagerly loads the
# PLDA npz files from the community-1 repo even for 3.1 — those two files must
# be warm-cached once (gate accepted) for HF_HUB_OFFLINE=1 boots to work.
_DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"

# pyannote's Pipeline.from_pretrained swallows the underlying HTTP/cache error
# and returns None, so whisperx's `.to(device)` blows up with an opaque
# AttributeError. Guard the load and raise a domain error naming the two real
# causes: a token that cannot read the gated repo, or a HF cache the service
# account cannot populate (the SYSTEM-run boot task has its own cache dir).
_GATED_MODEL_HINT = (
    f"{_DIARIZATION_MODEL} could not be loaded (gated model). "
    "Verify HF_TOKEN has accepted the model conditions (including the "
    "pyannote/speaker-diarization-community-1 gate — pyannote 4.x loads its "
    "PLDA files even for 3.1) and that HF_HOME points at a cache the server "
    "process can write."
)


def _load_pipeline(hf_token: str, device: str) -> DiarizationPipeline:
    """Load the diarization pipeline, failing loudly instead of returning None."""
    try:
        pipeline = DiarizationPipeline(
            model_name=_DIARIZATION_MODEL,
            token=hf_token,
            device=device,
        )
    except AttributeError as exc:
        # `.to(None)` — from_pretrained returned None.
        raise DiarizationFailedError(_GATED_MODEL_HINT, exc) from exc

    if pipeline is None or getattr(pipeline, "model", None) is None:
        raise DiarizationFailedError(_GATED_MODEL_HINT)

    return pipeline


class WhisperXDiarizationService:
    """
    WhisperX/PyAnnote-based implementation of diarization service.

    This service wraps the WhisperX diarization pipeline (PyAnnote) to provide
    speaker diarization functionality following the IDiarizationService
    interface. Model residency is owned by model_registry — the pipeline is
    leased per call and stays warm in VRAM across jobs.
    """

    def __init__(self, hf_token: str) -> None:
        """
        Initialize the diarization service.

        Args:
            hf_token: HuggingFace authentication token for model access
        """
        self.hf_token = hf_token
        self.logger = logger

    def diarize(
        self,
        audio: np.ndarray[Any, np.dtype[np.float32]],
        device: str,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> pd.DataFrame:
        """
        Identify speakers using PyAnnote diarization model.

        Args:
            audio: Audio data as numpy array (float32)
            device: Device to use ('cpu' or 'cuda')
            min_speakers: Minimum number of speakers (optional)
            max_speakers: Maximum number of speakers (optional)

        Returns:
            DataFrame with speaker segments
        """
        self.logger.debug("Starting diarization with device: %s", device)

        # Model name is the pinned _DIARIZATION_MODEL constant — key on
        # device only.
        with lease(
            ("diarize", device),
            loader=lambda: _load_pipeline(self.hf_token, device),
        ) as pipeline:
            result = pipeline(
                audio=audio, min_speakers=min_speakers, max_speakers=max_speakers
            )

        self.logger.debug("Completed diarization with device: %s", device)
        return result  # type: ignore[no-any-return]
