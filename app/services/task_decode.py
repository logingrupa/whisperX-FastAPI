"""Decode a task's saved upload and hold the task to the decoded length.

The submit path gates and bills on the duration ffprobe reads from the
container, so it can reply without decoding. A truncated or forged header
misstates it. Once the background job has decoded the audio, the decoded
length is written to the task (usage_events bill it). A task that went
through FreeTierGate is re-checked against its tier's file-length cap and its
daily audio minutes are settled to the decoded length, before any model work.
"""

from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from app.audio import decode_saved_upload, get_audio_duration
from app.core.logging import logger
from app.domain.entities.task import Task
from app.domain.entities.user import User
from app.infrastructure.database.repositories.sqlalchemy_api_key_repository import (
    SQLAlchemyApiKeyRepository,
)
from app.infrastructure.database.repositories.sqlalchemy_rate_limit_repository import (
    SQLAlchemyRateLimitRepository,
)
from app.infrastructure.database.repositories.sqlalchemy_task_repository import (
    SQLAlchemyTaskRepository,
)
from app.infrastructure.database.repositories.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
from app.services.auth.rate_limit_service import RateLimitService
from app.services.concurrency_slot import task_bypassed_gate
from app.services.free_tier_gate import FreeTierGate

DURATION_TOLERANCE_SECONDS = 1.0


def decode_task_audio(
    session: Session, identifier: str, audio_path: str
) -> np.ndarray[Any, np.dtype[np.float32]]:
    """Decode the task's upload; record the decoded length if it differs.

    Raises:
        AudioProcessingError: ffmpeg could not decode the upload.
        FreeTierViolationError: a gated task's decoded audio exceeds its
            tier's file-length cap.
        RateLimitExceededError: the day's audio minutes cannot cover the
            longer decoded length.
    """
    audio = decode_saved_upload(audio_path)
    decoded_seconds = get_audio_duration(audio)
    repository = SQLAlchemyTaskRepository(session)
    task = repository.get_by_id(identifier)
    if task is None:
        raise ValueError(f"Task {identifier} not found after decoding its upload")
    probed_seconds = task.audio_duration or 0.0
    if abs(decoded_seconds - probed_seconds) <= DURATION_TOLERANCE_SECONDS:
        return audio
    logger.warning(
        "Task %s: decoded %.1fs but the container reported %.1fs; recording the decoded length",
        identifier,
        decoded_seconds,
        probed_seconds,
    )
    repository.update(identifier, {"audio_duration": decoded_seconds})
    gated_owner = _gated_owner(session, task)
    if gated_owner is None:
        return audio
    gate = FreeTierGate(
        rate_limit_service=RateLimitService(SQLAlchemyRateLimitRepository(session))
    )
    gate.check_file_duration(gated_owner, decoded_seconds)
    gate.reconcile_daily_minutes(gated_owner, probed_seconds, decoded_seconds)
    return audio


def _gated_owner(session: Session, task: Task) -> User | None:
    """The task's owner when its submit went through FreeTierGate, else None.

    Every transcription submit path (multipart, URL, TUS) runs the gate;
    only an unlimited API key skips it.
    """
    if task.user_id is None:
        return None
    if task_bypassed_gate(SQLAlchemyApiKeyRepository(session), task.api_key_id):
        return None
    return SQLAlchemyUserRepository(session).get_by_id(task.user_id)
