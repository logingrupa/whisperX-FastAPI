"""Concurrency slot release helper (Phase 20 leak fix).

Shared by every BackgroundTask worker that consumed a slot via
``FreeTierGate.check`` at request time. Centralised here so the
release contract has ONE implementation (DRY) — Phase 13-08 W1.

Tiger-style flat-guard: each precondition early-returns; no nested if.
SRP: slot release only — no usage_events, no task mutation.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.logging import logger
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
from app.services.free_tier_gate import FreeTierGate


def release_slot_if_authed(
    repo: SQLAlchemyTaskRepository,
    user_repo: SQLAlchemyUserRepository,
    identifier: str,
    free_tier_gate: FreeTierGate,
) -> None:
    """Release the concurrency slot iff the task has an authenticated owner."""
    completed_task = repo.get_by_id(identifier)
    if completed_task is None:
        return
    if completed_task.user_id is None:
        return
    user = user_repo.get_by_id(completed_task.user_id)
    if user is None:
        return
    free_tier_gate.release_concurrency(user)


def release_slot_for_task(session: Session, identifier: str) -> None:
    """Construct repos + gate from an open Session and release the slot.

    Convenience entrypoint for workers whose ``finally`` already has a
    SessionLocal-scoped Session. Swallows lookup failures so a release
    crash never blocks the worker's context-manager exit.
    """
    try:
        repo = SQLAlchemyTaskRepository(session)
        user_repo = SQLAlchemyUserRepository(session)
        rate_limit_service = RateLimitService(
            repository=SQLAlchemyRateLimitRepository(session)
        )
        free_tier_gate = FreeTierGate(rate_limit_service=rate_limit_service)
        release_slot_if_authed(repo, user_repo, identifier, free_tier_gate)
    except Exception as exc:
        logger.warning(
            "Failed to release concurrency slot task=%s: %s", identifier, exc
        )
