"""Per-completed-transcription usage_events writer (RATE-11, BILL-04).

SRP: writes one usage_events row per completed task. Idempotent via
``idempotency_key`` UNIQUE constraint (idempotency_key=task.uuid) — replay
safety for v1.3 Stripe metered billing (T-13-40).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class UsageEventWriter:
    """Idempotent insert into usage_events (idempotency_key=task.uuid)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        user_id: int,
        task_uuid: str,
        gpu_seconds: float,
        file_seconds: float,
        model: str,
    ) -> None:
        """Insert one usage_events row. Idempotent — duplicate task_uuid is no-op.

        The UNIQUE constraint on usage_events.idempotency_key means a
        replayed completion (re-enqueued task, double-fire) raises
        IntegrityError which we catch and rollback silently (T-13-40).
        """
        try:
            self.session.execute(
                text(
                    "INSERT INTO usage_events "
                    "(user_id, task_id, gpu_seconds, file_seconds, model, "
                    "idempotency_key, created_at) "
                    "VALUES (:user_id, :task_id, :gpu_seconds, :file_seconds, "
                    ":model, :idempotency_key, :created_at)"
                ),
                {
                    "user_id": user_id,
                    "task_id": None,
                    "gpu_seconds": gpu_seconds,
                    "file_seconds": file_seconds,
                    "model": model,
                    "idempotency_key": task_uuid,
                    "created_at": datetime.now(timezone.utc),
                },
            )
            self.session.commit()
            logger.info(
                "usage_events recorded user_id=%s task_uuid=%s",
                user_id,
                task_uuid,
            )
        except IntegrityError:
            self.session.rollback()
            logger.debug(
                "usage_events duplicate skipped task_uuid=%s", task_uuid
            )
