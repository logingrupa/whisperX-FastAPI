"""Unit tests for the TUS upload -> transcription bridge."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi import BackgroundTasks

from app.schemas import ComputeType, Device, WhisperModel
from app.services.upload_session_service import UploadSessionService


@pytest.fixture
def scheduled_params() -> dict:
    """Run start_transcription with every I/O boundary stubbed.

    Returns the SpeechToTextProcessingParams handed to the background task, so
    tests can assert on what the worker would actually be told to do.
    """
    repository = MagicMock()
    repository.add.return_value = "task-abc"
    service = UploadSessionService(repository=repository)
    background_tasks = BackgroundTasks()

    with (
        patch(
            "app.services.upload_session_service.validate_magic_bytes",
            return_value=(True, "ok", "audio/wav"),
        ),
        patch("app.services.upload_session_service.shutil.move"),
        patch(
            "app.services.upload_session_service.process_audio_file",
            return_value=np.zeros(16000, dtype=np.float32),
        ),
        patch(
            "app.services.upload_session_service.get_audio_duration",
            return_value=1.0,
        ),
    ):
        import asyncio

        asyncio.run(
            service.start_transcription(
                file_path="C:/tmp/tus-upload",
                metadata={"filename": "sermon.wav", "language": "lv"},
                background_tasks=background_tasks,
            )
        )

    assert len(background_tasks.tasks) == 1
    return background_tasks.tasks[0].args[0]


@pytest.mark.unit
class TestUploadSessionService:
    """The TUS path carries all production traffic; pin what it schedules."""

    def test_model_comes_from_settings_not_a_literal(self, scheduled_params) -> None:
        """Regression: the model was hardcoded to `tiny`, ignoring WHISPER_MODEL.

        The literal silently downgraded every upload whose language had no
        LANGUAGE_MODEL_OVERRIDES entry, no matter what .env configured.
        """
        from app.core.config import get_settings

        expected = get_settings().whisper
        assert scheduled_params.whisper_model_params.model == expected.WHISPER_MODEL
        assert scheduled_params.whisper_model_params.model != WhisperModel.tiny

    def test_runs_on_the_configured_accelerator(self, scheduled_params) -> None:
        """Transcription must land on the GPU whenever CUDA is configured."""
        from app.core.config import get_settings

        expected = get_settings().whisper
        assert scheduled_params.whisper_model_params.device == expected.DEVICE
        assert scheduled_params.whisper_model_params.compute_type == expected.COMPUTE_TYPE
        if expected.DEVICE == Device.cuda:
            assert scheduled_params.whisper_model_params.compute_type == ComputeType.float16

    def test_client_language_is_carried_through(self, scheduled_params) -> None:
        """Language drives LANGUAGE_MODEL_OVERRIDES, so it must survive the hop."""
        assert scheduled_params.whisper_model_params.language == "lv"
