"""Turns a saved upload into a scheduled task, or returns its in-flight twin.

A client whose submit outlives Cloudflare's 100 s origin timeout sees a 524
and resubmits. The submission key (file bytes + task type + language +
params + callback) lets that resubmit return the task already processing
instead of queueing a second GPU job for the same work. The partial unique
index ``uq_tasks_in_flight_submission`` backs the lookup against races.
"""

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass

from app.audio import probe_audio_duration
from app.core.exceptions import DatabaseOperationError
from app.core.logging import logger
from app.domain.entities.task import Task
from app.domain.entities.user import User
from app.domain.repositories.task_repository import ITaskRepository
from app.schemas import TaskStatus
from app.services.file_service import FileService
from app.services.free_tier_gate import FreeTierGate


@dataclass(frozen=True)
class FreeTierAdmission:
    """One request's FreeTierGate inputs, checked once the duration is known."""

    gate: FreeTierGate
    user: User
    model: str
    diarize: bool
    unlimited: bool

    def check(self, file_seconds: float) -> None:
        """Run the gate; raises on the first failed limit."""
        self.gate.check(
            user=self.user,
            file_seconds=file_seconds,
            model=self.model,
            diarize=self.diarize,
            unlimited=self.unlimited,
        )

    def refund(self, file_seconds: float) -> None:
        """Return everything ``check`` consumed. Unlimited keys consumed nothing."""
        if self.unlimited:
            return
        self.gate.release_admission(self.user, file_seconds)


@dataclass(frozen=True)
class SubmissionOutcome:
    """The task a submit resolved to, and whether it already existed."""

    identifier: str
    is_duplicate: bool


def compute_submission_key(file_sha256: str, task: Task) -> str:
    """SHA-256 over everything that makes two submits the same job."""
    if len(file_sha256) != 64:
        raise ValueError(f"file_sha256 must be a 64-char hex digest, got: {file_sha256!r}")
    fingerprint = json.dumps(
        {
            "file_sha256": file_sha256,
            "task_type": task.task_type,
            "language": task.language,
            "task_params": task.task_params,
            "callback_url": task.callback_url,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()


class TaskSubmissionService:
    """Dedupe, gate, persist and schedule one uploaded file."""

    def __init__(self, repository: ITaskRepository) -> None:
        """Bind the request-scoped task repository."""
        self._repository = repository

    def submit(
        self,
        *,
        audio_path: str,
        task: Task,
        admission: FreeTierAdmission,
        schedule: Callable[[str], None],
    ) -> SubmissionOutcome:
        """Return the in-flight twin of ``task``, or create and schedule it.

        Args:
            audio_path: Saved upload. Deleted here when a twin is returned,
                otherwise owned by the scheduled job.
            task: Draft task with owner, type, language and params set.
                ``submission_key`` and ``audio_duration`` are filled in here.
            admission: FreeTierGate inputs. A twin skips the gate entirely.
            schedule: Queues the background job for the new identifier.

        Returns:
            SubmissionOutcome: the new task, or the twin it matched.
        """
        if task.user_id is None:
            raise ValueError("Submission requires task.user_id for the in-flight lookup")
        task.submission_key = compute_submission_key(
            FileService.sha256_of_file(audio_path), task
        )
        twin_identifier = self._find_in_flight_twin(task)
        if twin_identifier is not None:
            return self._return_twin(twin_identifier, audio_path)

        task.audio_duration = probe_audio_duration(audio_path)
        admission.check(task.audio_duration)
        try:
            identifier = self._insert(task)
        except Exception:
            admission.refund(task.audio_duration)
            raise
        if identifier != task.uuid:
            admission.refund(task.audio_duration)
            return self._return_twin(identifier, audio_path)
        self._schedule_or_fail(task, admission, schedule)
        return SubmissionOutcome(identifier=identifier, is_duplicate=False)

    def _insert(self, task: Task) -> str:
        """Persist ``task``; when the INSERT raises, return the row holding its key.

        That row is this task's own if the INSERT committed before the error,
        or a concurrent identical submit's if it won the unique index. With no
        such row the error propagates.
        """
        try:
            return self._repository.add(task)
        except DatabaseOperationError:
            twin_identifier = self._find_in_flight_twin(task)
            if twin_identifier is None:
                raise
            return twin_identifier

    def _schedule_or_fail(
        self,
        task: Task,
        admission: FreeTierAdmission,
        schedule: Callable[[str], None],
    ) -> None:
        """Queue the job. If that fails, fail the row so no resubmit dedupes onto it."""
        assert task.audio_duration is not None
        try:
            schedule(task.uuid)
        except Exception as error:
            admission.refund(task.audio_duration)
            self._repository.update(
                task.uuid,
                {"status": TaskStatus.failed, "error": f"Could not queue the job: {error}"},
            )
            raise

    def _find_in_flight_twin(self, task: Task) -> str | None:
        """Identifier of the caller's processing task with the same key, if any."""
        assert task.user_id is not None and task.submission_key is not None
        twin = self._repository.find_in_flight_by_submission_key(
            user_id=task.user_id, submission_key=task.submission_key
        )
        return twin.uuid if twin is not None else None

    @staticmethod
    def _return_twin(twin_identifier: str, audio_path: str) -> SubmissionOutcome:
        """Answer with the in-flight twin and drop the duplicate upload."""
        logger.info(
            "Resubmit matches in-flight task %s; returning it instead of queueing a duplicate",
            twin_identifier,
        )
        os.remove(audio_path)
        return SubmissionOutcome(identifier=twin_identifier, is_duplicate=True)
