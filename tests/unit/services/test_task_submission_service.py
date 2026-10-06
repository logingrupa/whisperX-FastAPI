"""Unit tests for TaskSubmissionService: in-flight dedupe, gating, races."""

import hashlib
from typing import Any
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import DatabaseOperationError
from app.domain.entities.task import Task
from app.services import live_jobs
from app.services import task_submission_service as submission_module
from app.services.free_tier_gate import FreeTierGate
from app.services.task_submission_service import (
    FreeTierAdmission,
    SubmissionOutcome,
    TaskSubmissionService,
    compute_submission_key,
)

UPLOAD_BYTES = b"two hours of sermon"
PROBED_SECONDS = 7131.0


def _draft_task(language: str = "ru", model: str = "large-v3") -> Task:
    return Task(
        uuid="new-uuid",
        status="processing",
        task_type="transcription",
        language=language,
        task_params={"model": model, "language": language},
        user_id=3,
    )


@pytest.fixture
def live_twin() -> Any:
    """Mark the twin's worker as running for the duration of a test."""
    live_jobs.mark_live("twin-uuid")
    yield
    live_jobs.mark_finished("twin-uuid")


@pytest.fixture(autouse=True)
def _new_task_never_stays_live() -> Any:
    yield
    live_jobs.mark_finished("new-uuid")


def _twin_task() -> Task:
    return Task(uuid="twin-uuid", status="processing", task_type="transcription", user_id=3)


@pytest.fixture
def upload(tmp_path: Path) -> Path:
    path = tmp_path / "upload.ogg"
    path.write_bytes(UPLOAD_BYTES)
    return path


@pytest.fixture(autouse=True)
def _stub_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(submission_module, "probe_audio_duration", lambda _path: PROBED_SECONDS)


@pytest.fixture
def repository() -> MagicMock:
    repository = MagicMock()
    repository.find_in_flight_by_submission_key.return_value = None
    repository.add.return_value = "new-uuid"
    return repository


@pytest.fixture
def admission() -> MagicMock:
    return MagicMock(spec=FreeTierAdmission)


@pytest.mark.unit
class TestSubmit:
    def test_new_submit_is_gated_persisted_and_scheduled(
        self, repository: MagicMock, admission: MagicMock, upload: Path
    ) -> None:
        schedule = MagicMock()
        task = _draft_task()

        outcome = TaskSubmissionService(repository).submit(
            audio_path=str(upload), task=task, admission=admission, schedule=schedule
        )

        assert outcome == SubmissionOutcome(identifier="new-uuid", is_duplicate=False)
        admission.check.assert_called_once_with(PROBED_SECONDS)
        repository.add.assert_called_once_with(task)
        schedule.assert_called_once_with("new-uuid")
        assert task.audio_duration == PROBED_SECONDS
        assert task.submission_key == compute_submission_key(
            hashlib.sha256(UPLOAD_BYTES).hexdigest(), task
        )
        assert upload.exists(), "the scheduled job owns the upload"

    def test_resubmit_returns_in_flight_twin_without_a_second_job(
        self, repository: MagicMock, admission: MagicMock, upload: Path, live_twin: None
    ) -> None:
        repository.find_in_flight_by_submission_key.return_value = _twin_task()
        schedule = MagicMock()

        outcome = TaskSubmissionService(repository).submit(
            audio_path=str(upload), task=_draft_task(), admission=admission, schedule=schedule
        )

        assert outcome == SubmissionOutcome(identifier="twin-uuid", is_duplicate=True)
        admission.check.assert_not_called()
        repository.add.assert_not_called()
        schedule.assert_not_called()
        assert not upload.exists(), "the duplicate upload is discarded"

    def test_lost_race_on_unique_index_returns_winner_and_refunds(
        self, repository: MagicMock, admission: MagicMock, upload: Path, live_twin: None
    ) -> None:
        repository.find_in_flight_by_submission_key.side_effect = [None, _twin_task()]
        repository.add.side_effect = DatabaseOperationError(
            operation="add", reason="UNIQUE constraint failed"
        )
        schedule = MagicMock()

        outcome = TaskSubmissionService(repository).submit(
            audio_path=str(upload), task=_draft_task(), admission=admission, schedule=schedule
        )

        assert outcome == SubmissionOutcome(identifier="twin-uuid", is_duplicate=True)
        admission.refund.assert_called_once_with(PROBED_SECONDS)
        schedule.assert_not_called()
        assert not upload.exists()

    def test_database_error_without_twin_refunds_and_raises(
        self, repository: MagicMock, admission: MagicMock, upload: Path
    ) -> None:
        repository.add.side_effect = DatabaseOperationError(operation="add", reason="disk full")

        with pytest.raises(DatabaseOperationError):
            TaskSubmissionService(repository).submit(
                audio_path=str(upload),
                task=_draft_task(),
                admission=admission,
                schedule=MagicMock(),
            )

        admission.refund.assert_called_once_with(PROBED_SECONDS)

    def test_schedule_failure_refunds_and_raises(
        self, repository: MagicMock, admission: MagicMock, upload: Path
    ) -> None:
        schedule = MagicMock(side_effect=RuntimeError("queue closed"))

        with pytest.raises(RuntimeError, match="queue closed"):
            TaskSubmissionService(repository).submit(
                audio_path=str(upload), task=_draft_task(), admission=admission, schedule=schedule
            )

        admission.refund.assert_called_once_with(PROBED_SECONDS)
        failed_update = repository.update.call_args
        assert failed_update.args[0] == "new-uuid"
        assert failed_update.args[1]["status"] == "failed", "an unqueued row must not stay a twin"

    def test_insert_that_committed_before_failing_is_scheduled_as_new(
        self, repository: MagicMock, admission: MagicMock, upload: Path
    ) -> None:
        own_row = Task(uuid="new-uuid", status="processing", task_type="transcription", user_id=3)
        repository.find_in_flight_by_submission_key.side_effect = [None, own_row]
        repository.add.side_effect = DatabaseOperationError(
            operation="add", reason="database is locked (refresh)"
        )
        schedule = MagicMock()

        outcome = TaskSubmissionService(repository).submit(
            audio_path=str(upload), task=_draft_task(), admission=admission, schedule=schedule
        )

        assert outcome == SubmissionOutcome(identifier="new-uuid", is_duplicate=False)
        schedule.assert_called_once_with("new-uuid")
        admission.refund.assert_not_called()
        assert upload.exists(), "the scheduled job owns the upload"

    def test_twin_without_a_live_worker_is_failed_and_replaced(
        self, repository: MagicMock, admission: MagicMock, upload: Path
    ) -> None:
        repository.find_in_flight_by_submission_key.return_value = _twin_task()
        schedule = MagicMock()

        outcome = TaskSubmissionService(repository).submit(
            audio_path=str(upload), task=_draft_task(), admission=admission, schedule=schedule
        )

        assert outcome == SubmissionOutcome(identifier="new-uuid", is_duplicate=False)
        repository.fail_if_processing.assert_called_once_with(
            "twin-uuid", submission_module.ORPHANED_TASK_ERROR
        )
        schedule.assert_called_once_with("new-uuid")

    def test_scheduled_job_is_live_until_its_worker_finishes(
        self, repository: MagicMock, admission: MagicMock, upload: Path
    ) -> None:
        TaskSubmissionService(repository).submit(
            audio_path=str(upload), task=_draft_task(), admission=admission, schedule=MagicMock()
        )

        assert live_jobs.is_live("new-uuid")

    def test_failed_submit_leaves_nothing_live(
        self, repository: MagicMock, admission: MagicMock, upload: Path
    ) -> None:
        repository.add.side_effect = DatabaseOperationError(operation="add", reason="disk full")

        with pytest.raises(DatabaseOperationError):
            TaskSubmissionService(repository).submit(
                audio_path=str(upload),
                task=_draft_task(),
                admission=admission,
                schedule=MagicMock(),
            )

        assert not live_jobs.is_live("new-uuid")

    def test_gate_rejection_creates_nothing(
        self, repository: MagicMock, admission: MagicMock, upload: Path
    ) -> None:
        admission.check.side_effect = PermissionError("file too long")

        with pytest.raises(PermissionError):
            TaskSubmissionService(repository).submit(
                audio_path=str(upload),
                task=_draft_task(),
                admission=admission,
                schedule=MagicMock(),
            )

        repository.add.assert_not_called()
        admission.refund.assert_not_called()

    def test_task_without_owner_is_rejected(
        self, repository: MagicMock, admission: MagicMock, upload: Path
    ) -> None:
        task = _draft_task()
        task.user_id = None

        with pytest.raises(ValueError, match="user_id"):
            TaskSubmissionService(repository).submit(
                audio_path=str(upload), task=task, admission=admission, schedule=MagicMock()
            )


@pytest.mark.unit
class TestComputeSubmissionKey:
    FILE_SHA256 = "a" * 64

    def test_same_file_and_inputs_give_same_key(self) -> None:
        assert compute_submission_key(self.FILE_SHA256, _draft_task()) == compute_submission_key(
            self.FILE_SHA256, _draft_task()
        )

    def test_language_change_is_a_different_job(self) -> None:
        assert compute_submission_key(self.FILE_SHA256, _draft_task(language="en")) != (
            compute_submission_key(self.FILE_SHA256, _draft_task(language="ru"))
        )

    def test_model_change_is_a_different_job(self) -> None:
        assert compute_submission_key(self.FILE_SHA256, _draft_task(model="tiny")) != (
            compute_submission_key(self.FILE_SHA256, _draft_task(model="large-v3"))
        )

    def test_different_file_is_a_different_job(self) -> None:
        assert compute_submission_key("a" * 64, _draft_task()) != compute_submission_key(
            "b" * 64, _draft_task()
        )

    def test_rejects_a_non_digest(self) -> None:
        with pytest.raises(ValueError, match="64-char"):
            compute_submission_key("abc", _draft_task())


@pytest.mark.unit
class TestFreeTierAdmission:
    def _admission(self, *, unlimited: bool) -> tuple[FreeTierAdmission, MagicMock, MagicMock]:
        gate = MagicMock(spec=FreeTierGate)
        user = MagicMock()
        admission = FreeTierAdmission(
            gate=gate, user=user, model="large-v3", diarize=False, unlimited=unlimited
        )
        return admission, gate, user

    def test_check_forwards_every_gate_input(self) -> None:
        admission, gate, user = self._admission(unlimited=False)

        admission.check(300.0)

        gate.check.assert_called_once_with(
            user=user, file_seconds=300.0, model="large-v3", diarize=False, unlimited=False
        )

    def test_refund_returns_everything_the_check_consumed(self) -> None:
        admission, gate, user = self._admission(unlimited=False)

        admission.refund(300.0)

        gate.release_admission.assert_called_once_with(user, 300.0)

    def test_unlimited_key_refunds_nothing(self) -> None:
        admission, gate, _user = self._admission(unlimited=True)

        admission.refund(300.0)

        gate.release_admission.assert_not_called()
