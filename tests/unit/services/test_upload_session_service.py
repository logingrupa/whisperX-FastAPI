"""Unit tests for the TUS upload -> transcription bridge."""

from pathlib import Path
from typing import Any
from uuid import UUID
from unittest.mock import MagicMock, patch

import pytest
from fastapi import BackgroundTasks

from app.core.exceptions import FreeTierViolationError
from app.domain.entities.user import User
from app.schemas import ComputeType, Device, WhisperModel
from app.services.free_tier_gate import FreeTierGate
from app.services.upload_session_service import UploadSessionService


UPLOADER = User(id=3, email="owner@x.com", password_hash="x", plan_tier="pro")
CLIENT_TASK_ID = "6f1c2b9e-3d4a-4c5b-9a8e-7f6d5c4b3a21"
TUS_FILE = "C:/tmp/tus-upload"
RENAMED_FILE = str(Path(TUS_FILE + ".wav"))


def _run_completion(
    repository: MagicMock,
    gate: MagicMock,
    background_tasks: BackgroundTasks,
    *,
    unlimited: bool = False,
    task_id: str = CLIENT_TASK_ID,
) -> MagicMock:
    """Run start_transcription with every I/O boundary stubbed; return the os.remove mock."""
    service = UploadSessionService(repository=repository)
    with (
        patch(
            "app.services.upload_session_service.validate_magic_bytes",
            return_value=(True, "ok", "audio/wav"),
        ),
        patch("app.services.upload_session_service.shutil.move"),
        patch(
            "app.services.upload_session_service.probe_audio_duration",
            return_value=1.0,
        ),
        patch("app.services.upload_session_service.os.remove") as remove_upload,
    ):
        service.start_transcription(
            file_path=TUS_FILE,
            metadata={"filename": "sermon.wav", "language": "lv", "taskId": task_id},
            background_tasks=background_tasks,
            gate=gate,
            user=UPLOADER,
            unlimited=unlimited,
            api_key_id=5,
        )
    return remove_upload


@pytest.fixture
def repository() -> MagicMock:
    repository = MagicMock()
    repository.add.side_effect = lambda task: task.uuid
    return repository


@pytest.fixture
def scheduled_params(repository: MagicMock) -> Any:
    """The SpeechToTextProcessingParams handed to the background task."""
    background_tasks = BackgroundTasks()
    _run_completion(repository, MagicMock(spec=FreeTierGate), background_tasks)
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

    def test_worker_gets_the_saved_file_not_decoded_audio(self, scheduled_params) -> None:
        """Completion only probes the duration; the background job decodes."""
        assert Path(scheduled_params.audio_path) == Path(RENAMED_FILE)


@pytest.mark.unit
class TestTusFreeTierGate:
    """TUS completion runs FreeTierGate like the multipart submit routes."""

    def test_gate_checks_the_probed_length_and_the_model_that_will_run(
        self, repository: MagicMock
    ) -> None:
        from app.core.config import get_settings

        gate = MagicMock(spec=FreeTierGate)
        _run_completion(repository, gate, BackgroundTasks())

        gate.check.assert_called_once_with(
            user=UPLOADER,
            file_seconds=1.0,
            model=get_settings().whisper.WHISPER_MODEL.value,
            diarize=False,
            unlimited=False,
        )

    def test_task_records_owner_key_and_client_task_id(self, repository: MagicMock) -> None:
        _run_completion(repository, MagicMock(spec=FreeTierGate), BackgroundTasks())

        created = repository.add.call_args.args[0]
        assert (created.uuid, created.user_id, created.api_key_id) == (CLIENT_TASK_ID, 3, 5)

    def test_a_task_id_that_is_not_a_uuid_is_replaced(self, repository: MagicMock) -> None:
        _run_completion(
            repository, MagicMock(spec=FreeTierGate), BackgroundTasks(), task_id="job-x"
        )

        created = repository.add.call_args.args[0]
        assert created.uuid != "job-x"
        assert str(UUID(created.uuid)) == created.uuid

    def test_rejected_upload_creates_no_task(self, repository: MagicMock) -> None:
        gate = MagicMock(spec=FreeTierGate)
        gate.check.side_effect = FreeTierViolationError("File duration 600s exceeds tier limit 300s")
        background_tasks = BackgroundTasks()

        with pytest.raises(FreeTierViolationError):
            _run_completion(repository, gate, background_tasks)
        repository.add.assert_not_called()
        assert background_tasks.tasks == []

    def test_rejected_upload_file_is_removed(self, repository: MagicMock) -> None:
        gate = MagicMock(spec=FreeTierGate)
        gate.check.side_effect = FreeTierViolationError("File duration 600s exceeds tier limit 300s")
        service = UploadSessionService(repository=repository)

        with (
            patch(
                "app.services.upload_session_service.validate_magic_bytes",
                return_value=(True, "ok", "audio/wav"),
            ),
            patch("app.services.upload_session_service.shutil.move"),
            patch("app.services.upload_session_service.probe_audio_duration", return_value=600.0),
            patch("app.services.upload_session_service.os.remove") as remove_upload,
            pytest.raises(FreeTierViolationError),
        ):
            service.start_transcription(
                file_path=TUS_FILE,
                metadata={"filename": "sermon.wav"},
                background_tasks=BackgroundTasks(),
                gate=gate,
                user=UPLOADER,
                unlimited=False,
                api_key_id=None,
            )

        remove_upload.assert_called_once_with(RENAMED_FILE)

    def test_failed_insert_refunds_the_gate(self, repository: MagicMock) -> None:
        gate = MagicMock(spec=FreeTierGate)
        repository.add.side_effect = RuntimeError("database is locked")

        with pytest.raises(RuntimeError):
            _run_completion(repository, gate, BackgroundTasks())

        gate.release_admission.assert_called_once_with(UPLOADER, 1.0)
