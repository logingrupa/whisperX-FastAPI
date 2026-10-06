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
from app.services.free_tier_gate import FreeTierGate


def task_bypassed_gate(
    api_key_repo: SQLAlchemyApiKeyRepository, api_key_id: int | None
) -> bool:
    """True iff the task was created by an unlimited key (gate was bypassed).

    Such a task consumed NO concurrency slot at request time, so releasing
    one here would over-refund the per-user bucket and corrupt accounting
    for the user's limited keys. Flat-guard: unknown / missing key => not
    bypassed (release as normal).
    """
    if api_key_id is None:
        return False
    api_key = api_key_repo.get_by_id(api_key_id)
    if api_key is None:
        return False
    return bool(api_key.unlimited)


def release_slot_if_authed(
    repo: SQLAlchemyTaskRepository,
    user_repo: SQLAlchemyUserRepository,
    identifier: str,
    free_tier_gate: FreeTierGate,
    api_key_repo: SQLAlchemyApiKeyRepository,
) -> None:
    """Release the concurrency slot iff the task has an authenticated owner.

    Skips the release when the task was created by an unlimited key — that
    request bypassed FreeTierGate.check and never consumed a slot (W1 mirror).
    """
    completed_task = repo.get_by_id(identifier)
    if completed_task is None:
        return
    if completed_task.user_id is None:
        return
    if task_bypassed_gate(api_key_repo, completed_task.api_key_id):
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
        api_key_repo = SQLAlchemyApiKeyRepository(session)
        rate_limit_service = RateLimitService(
            repository=SQLAlchemyRateLimitRepository(session)
        )
        free_tier_gate = FreeTierGate(rate_limit_service=rate_limit_service)
        release_slot_if_authed(
            repo, user_repo, identifier, free_tier_gate, api_key_repo
        )
    except Exception as exc:
        logger.warning(
            "Failed to release concurrency slot task=%s: %s", identifier, exc
        )
