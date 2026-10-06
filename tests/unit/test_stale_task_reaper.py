"""Tests for the startup sweep of orphaned tasks."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.database.models import Base, RateLimitBucket, Task
from app.services.stale_task_reaper import reap_orphaned_tasks, reset_concurrency_slots


@pytest.fixture()
def session() -> Session:
    """In-memory database with the real Task schema."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db_session:
        yield db_session


def _add_task(session: Session, uuid: str, status: str) -> None:
    session.add(
        Task(
            uuid=uuid,
            status=status,
            result=None,
            task_type="full_process",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    session.commit()


def test_sweeps_processing_tasks(session: Session) -> None:
    _add_task(session, "orphan-1", "processing")
    _add_task(session, "orphan-2", "processing")

    assert reap_orphaned_tasks(session) == 2

    statuses = {
        row[0] for row in session.execute(text("SELECT status FROM tasks")).all()
    }
    assert statuses == {"failed"}


def test_leaves_completed_and_failed_untouched(session: Session) -> None:
    _add_task(session, "done", "completed")
    _add_task(session, "broken", "failed")

    assert reap_orphaned_tasks(session) == 0

    rows = dict(
        session.execute(text("SELECT uuid, status FROM tasks")).all()  # type: ignore[arg-type]
    )
    assert rows == {"done": "completed", "broken": "failed"}


def test_records_reason_and_end_time(session: Session) -> None:
    _add_task(session, "orphan", "processing")

    reap_orphaned_tasks(session)

    error, end_time = session.execute(
        text("SELECT error, end_time FROM tasks WHERE uuid = 'orphan'")
    ).one()
    assert "Orphaned" in error, "operator needs to know why it failed"
    assert end_time is not None, "end_time must be set so the row is not open-ended"


def test_is_idempotent(session: Session) -> None:
    _add_task(session, "orphan", "processing")

    assert reap_orphaned_tasks(session) == 1
    assert reap_orphaned_tasks(session) == 0, "second sweep must find nothing"


def _add_bucket(session: Session, bucket_key: str, tokens: int) -> None:
    session.add(
        RateLimitBucket(
            bucket_key=bucket_key, tokens=tokens, last_refill=datetime.now(timezone.utc)
        )
    )
    session.commit()


def test_startup_returns_every_concurrency_slot(session: Session) -> None:
    _add_bucket(session, "user:3:concurrent", 0)
    _add_bucket(session, "user:7:concurrent", 0)

    assert reset_concurrency_slots(session) == 2

    remaining = session.execute(text("SELECT bucket_key FROM rate_limit_buckets")).all()
    assert remaining == []


def test_startup_leaves_hourly_and_daily_buckets(session: Session) -> None:
    _add_bucket(session, "user:3:concurrent", 0)
    _add_bucket(session, "user:3:tx:hour", 2)
    _add_bucket(session, "user:3:audio_min:day", 11)

    reset_concurrency_slots(session)

    remaining = {
        row[0] for row in session.execute(text("SELECT bucket_key FROM rate_limit_buckets")).all()
    }
    assert remaining == {"user:3:tx:hour", "user:3:audio_min:day"}
