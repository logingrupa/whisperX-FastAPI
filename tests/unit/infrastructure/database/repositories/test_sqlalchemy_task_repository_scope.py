"""Unit tests for SQLAlchemyTaskRepository per-user scoping (Plan 13-07).

Uses an in-memory SQLite engine (no factory_boy dependency) — verifies:

  * unscoped reads return all rows (admin/CLI compat — backward compat)
  * scoped reads filter rows to the scoped user
  * scope auto-injects user_id on add() when entity has no owner
  * fail-loud refuses to persist orphan task
  * cross-user get_by_id / update / delete all behave as if not found
"""

from __future__ import annotations

from typing import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.entities.task import Task as DomainTask
from app.infrastructure.database.models import Base
from app.infrastructure.database.models import Task as ORMTask
from app.infrastructure.database.models import User as ORMUser
from app.infrastructure.database.repositories.sqlalchemy_task_repository import (
    SQLAlchemyTaskRepository,
)


def _seed_users(session: Session, ids: list[int]) -> None:
    """Insert minimal user rows so tasks.user_id FK is satisfied."""
    for uid in ids:
        session.add(
            ORMUser(
                id=uid,
                email=f"u{uid}@example.com",
                password_hash="x",
            )
        )
    session.commit()


def _new_task(
    *,
    uuid: str,
    user_id: int | None = None,
    status: str = "pending",
    task_type: str = "transcription",
) -> DomainTask:
    return DomainTask(
        uuid=uuid,
        status=status,
        task_type=task_type,
        user_id=user_id,
    )


@pytest.fixture
def session() -> Generator[Session, None, None]:
    """In-memory SQLite session with all tables pre-created."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    sess = SessionLocal()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


@pytest.fixture
def repo(session: Session) -> SQLAlchemyTaskRepository:
    # Seed users 1, 2, 3, 7, 99 covering every user_id used across the suite
    # (FK enforcement is enabled globally — Phase 10-04 PRAGMA listener).
    _seed_users(session, [1, 2, 3, 7, 99])
    return SQLAlchemyTaskRepository(session)


@pytest.mark.unit
def test_default_scope_is_none(repo: SQLAlchemyTaskRepository) -> None:
    """No scope set on construction — backward-compatible default."""
    assert repo._user_scope is None


@pytest.mark.unit
def test_set_user_scope_idempotent(repo: SQLAlchemyTaskRepository) -> None:
    """set_user_scope mutates _user_scope; setting None clears."""
    repo.set_user_scope(7)
    assert repo._user_scope == 7
    repo.set_user_scope(None)
    assert repo._user_scope is None


@pytest.mark.unit
def test_unscoped_get_all_returns_every_row(repo: SQLAlchemyTaskRepository) -> None:
    """Backward-compatible CLI / admin path — no scope means all rows visible."""
    repo.add(_new_task(uuid="t-a", user_id=1))
    repo.add(_new_task(uuid="t-b", user_id=2))
    repo.add(_new_task(uuid="t-c", user_id=3))
    assert {t.uuid for t in repo.get_all()} == {"t-a", "t-b", "t-c"}


@pytest.mark.unit
def test_scoped_get_all_returns_only_users_rows(repo: SQLAlchemyTaskRepository) -> None:
    """Scoped get_all filters to rows owned by the scoped user."""
    repo.add(_new_task(uuid="alice-1", user_id=1))
    repo.add(_new_task(uuid="alice-2", user_id=1))
    repo.add(_new_task(uuid="bob-1", user_id=2))

    repo.set_user_scope(1)
    alice = repo.get_all()
    assert {t.uuid for t in alice} == {"alice-1", "alice-2"}

    repo.set_user_scope(2)
    bob = repo.get_all()
    assert {t.uuid for t in bob} == {"bob-1"}


@pytest.mark.unit
def test_scoped_get_by_id_cross_user_returns_none(repo: SQLAlchemyTaskRepository) -> None:
    """Foreign UUID under scope returns None (route raises 404 opaquely)."""
    repo.add(_new_task(uuid="alice-task", user_id=1))
    repo.set_user_scope(2)  # Bob looking
    assert repo.get_by_id("alice-task") is None


@pytest.mark.unit
def test_scoped_get_by_id_own_returns_task(repo: SQLAlchemyTaskRepository) -> None:
    repo.add(_new_task(uuid="alice-task", user_id=1))
    repo.set_user_scope(1)
    task = repo.get_by_id("alice-task")
    assert task is not None
    assert task.user_id == 1


@pytest.mark.unit
def test_scoped_delete_cross_user_returns_false(
    repo: SQLAlchemyTaskRepository, session: Session
) -> None:
    """Cross-user delete is a no-op; row remains intact."""
    repo.add(_new_task(uuid="alice-task", user_id=1))
    repo.set_user_scope(2)
    assert repo.delete("alice-task") is False
    # Bypass scope to confirm row still exists
    assert session.query(ORMTask).filter(ORMTask.uuid == "alice-task").first() is not None


@pytest.mark.unit
def test_scoped_delete_own_succeeds(repo: SQLAlchemyTaskRepository) -> None:
    repo.add(_new_task(uuid="alice-task", user_id=1))
    repo.set_user_scope(1)
    assert repo.delete("alice-task") is True
    assert repo.get_by_id("alice-task") is None


@pytest.mark.unit
def test_scoped_update_cross_user_raises_not_found(repo: SQLAlchemyTaskRepository) -> None:
    """Cross-user update raises ValueError (same surface as genuine miss)."""
    repo.add(_new_task(uuid="alice-task", user_id=1))
    repo.set_user_scope(2)
    with pytest.raises(ValueError, match="Task not found"):
        repo.update("alice-task", {"status": "completed"})


@pytest.mark.unit
def test_add_injects_user_id_from_scope(repo: SQLAlchemyTaskRepository) -> None:
    """Entity without explicit user_id gets it from the scope."""
    repo.set_user_scope(7)
    repo.add(_new_task(uuid="auto-owned", user_id=None))
    repo.set_user_scope(None)
    fetched = repo.get_by_id("auto-owned")
    assert fetched is not None
    assert fetched.user_id == 7


@pytest.mark.unit
def test_add_raises_when_no_owner_and_no_scope(repo: SQLAlchemyTaskRepository) -> None:
    """Fail-loud: orphan task with no scope is refused (T-13-34)."""
    with pytest.raises(ValueError, match="Cannot persist task without user_id"):
        repo.add(_new_task(uuid="orphan", user_id=None))


@pytest.mark.unit
def test_add_raises_when_user_id_zero_and_no_scope(repo: SQLAlchemyTaskRepository) -> None:
    """Sentinel user_id=0 also refused (T-13-34 belt + braces)."""
    with pytest.raises(ValueError, match="Cannot persist task without user_id"):
        repo.add(_new_task(uuid="zero-owner", user_id=0))


@pytest.mark.unit
def test_explicit_user_id_overrides_scope_injection(
    repo: SQLAlchemyTaskRepository,
) -> None:
    """Explicit task.user_id is preserved even when a different scope is set.

    Scope only injects when entity has no owner — this preserves Phase 12
    admin-CLI behavior where user_id is explicit on the entity.
    """
    repo.set_user_scope(2)
    repo.add(_new_task(uuid="explicit", user_id=99))
    repo.set_user_scope(None)
    fetched = repo.get_by_id("explicit")
    assert fetched is not None
    assert fetched.user_id == 99


@pytest.mark.unit
def test_clearing_scope_restores_unscoped_view(repo: SQLAlchemyTaskRepository) -> None:
    """After set_user_scope(None) all rows visible again."""
    repo.add(_new_task(uuid="alice", user_id=1))
    repo.add(_new_task(uuid="bob", user_id=2))

    repo.set_user_scope(1)
    assert {t.uuid for t in repo.get_all()} == {"alice"}
    repo.set_user_scope(None)
    assert {t.uuid for t in repo.get_all()} == {"alice", "bob"}
