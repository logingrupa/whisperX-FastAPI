"""Unit tests for UsageEventWriter (Phase 13-08, RATE-11/BILL-04).

Coverage (≥3):
  1. test_record_inserts_row             — single row written with all fields
  2. test_record_idempotency_skip        — duplicate task_uuid no-ops via UNIQUE catch
  3. test_record_uses_task_uuid_as_idempotency — column == task_uuid
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database.models import (
    Base,
    User as ORMUser,
)
from app.services.usage_event_writer import UsageEventWriter


@pytest.fixture
def session_factory(tmp_path: Path) -> Any:
    db = tmp_path / "ue.db"
    engine = create_engine(
        f"sqlite:///{db}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Seed user (FK target)
    with factory() as s:
        s.add(ORMUser(id=1, email="x@x.com", password_hash="x"))
        s.commit()
    return factory


@pytest.mark.unit
class TestUsageEventWriter:
    def test_record_inserts_row(self, session_factory: Any) -> None:
        with session_factory() as session:
            writer = UsageEventWriter(session)
            writer.record(
                user_id=1,
                task_uuid="task-abc",
                gpu_seconds=12.0,
                file_seconds=60.0,
                model="tiny",
            )
        with session_factory() as session:
            row = session.execute(
                text(
                    "SELECT user_id, gpu_seconds, file_seconds, model, "
                    "idempotency_key FROM usage_events "
                    "WHERE idempotency_key = :k"
                ),
                {"k": "task-abc"},
            ).first()
            assert row is not None
            assert row[0] == 1
            assert row[1] == 12.0
            assert row[2] == 60.0
            assert row[3] == "tiny"
            assert row[4] == "task-abc"

    def test_record_idempotency_skip(self, session_factory: Any) -> None:
        """Second record() with same task_uuid is silent no-op."""
        with session_factory() as session:
            writer = UsageEventWriter(session)
            writer.record(
                user_id=1,
                task_uuid="task-dup",
                gpu_seconds=1.0,
                file_seconds=10.0,
                model="tiny",
            )
        with session_factory() as session:
            writer = UsageEventWriter(session)
            writer.record(  # MUST NOT raise
                user_id=1,
                task_uuid="task-dup",
                gpu_seconds=1.0,
                file_seconds=10.0,
                model="tiny",
            )
        with session_factory() as session:
            count = session.execute(
                text(
                    "SELECT COUNT(*) FROM usage_events "
                    "WHERE idempotency_key = :k"
                ),
                {"k": "task-dup"},
            ).scalar()
            assert count == 1

    def test_record_uses_task_uuid_as_idempotency(
        self, session_factory: Any
    ) -> None:
        with session_factory() as session:
            writer = UsageEventWriter(session)
            writer.record(
                user_id=1,
                task_uuid="abcd-1234",
                gpu_seconds=2.0,
                file_seconds=30.0,
                model="small",
            )
        with session_factory() as session:
            row = session.execute(
                text(
                    "SELECT idempotency_key FROM usage_events "
                    "WHERE idempotency_key = :k"
                ),
                {"k": "abcd-1234"},
            ).first()
            assert row is not None
            assert row[0] == "abcd-1234"
