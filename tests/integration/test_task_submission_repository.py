"""Repository + schema tests for resubmit dedupe and the task-list query.

Real SQLite file (Base.metadata.create_all), so the partial unique index
``uq_tasks_in_flight_submission`` and the deferred ``result`` column are
exercised for real.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import DatabaseOperationError
from app.domain.entities.task import Task
from app.infrastructure.database.models import Base
from app.infrastructure.database.models import Task as ORMTask
from app.infrastructure.database.models import User as ORMUser
from app.infrastructure.database.repositories.sqlalchemy_task_repository import (
    SQLAlchemyTaskRepository,
)

OWNER_ID = 301
OTHER_USER_ID = 302
KEY = "c" * 64


@pytest.fixture
def session_factory(tmp_path: Path) -> Any:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'submissions.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with factory() as session:
        for user_id in (OWNER_ID, OTHER_USER_ID):
            session.add(ORMUser(id=user_id, email=f"u{user_id}@x.com", password_hash="x"))
        session.commit()
    return factory


def _task(uuid: str, *, user_id: int = OWNER_ID, status: str = "processing", **fields: Any) -> Task:
    return Task(
        uuid=uuid,
        status=status,
        task_type="transcription",
        user_id=user_id,
        submission_key=fields.pop("submission_key", KEY),
        **fields,
    )


@pytest.mark.integration
class TestFindInFlightBySubmissionKey:
    def test_finds_the_processing_twin(self, session_factory: Any) -> None:
        with session_factory() as session:
            repository = SQLAlchemyTaskRepository(session)
            repository.add(_task("in-flight"))

            twin = repository.find_in_flight_by_submission_key(
                user_id=OWNER_ID, submission_key=KEY
            )

        assert twin is not None
        assert twin.uuid == "in-flight"

    def test_finished_task_is_not_a_twin(self, session_factory: Any) -> None:
        with session_factory() as session:
            repository = SQLAlchemyTaskRepository(session)
            repository.add(_task("done", status="completed"))
            repository.add(_task("broken", status="failed"))

            twin = repository.find_in_flight_by_submission_key(
                user_id=OWNER_ID, submission_key=KEY
            )

        assert twin is None

    def test_other_users_task_is_not_a_twin(self, session_factory: Any) -> None:
        with session_factory() as session:
            repository = SQLAlchemyTaskRepository(session)
            repository.add(_task("someone-else", user_id=OTHER_USER_ID))

            twin = repository.find_in_flight_by_submission_key(
                user_id=OWNER_ID, submission_key=KEY
            )

        assert twin is None

    def test_rejects_a_non_digest_key(self, session_factory: Any) -> None:
        with session_factory() as session:
            with pytest.raises(ValueError, match="64-char"):
                SQLAlchemyTaskRepository(session).find_in_flight_by_submission_key(
                    user_id=OWNER_ID, submission_key="short"
                )


@pytest.mark.integration
class TestInFlightUniqueIndex:
    def test_second_processing_row_with_same_key_is_refused(self, session_factory: Any) -> None:
        with session_factory() as session:
            repository = SQLAlchemyTaskRepository(session)
            repository.add(_task("first"))

            with pytest.raises(DatabaseOperationError):
                repository.add(_task("second"))

    def test_same_key_allowed_once_the_first_task_finished(self, session_factory: Any) -> None:
        with session_factory() as session:
            repository = SQLAlchemyTaskRepository(session)
            repository.add(_task("first"))
            repository.update("first", {"status": "completed"})

            repository.add(_task("rerun"))

            assert repository.get_by_id("rerun") is not None

    def test_same_key_allowed_for_another_user(self, session_factory: Any) -> None:
        with session_factory() as session:
            repository = SQLAlchemyTaskRepository(session)
            repository.add(_task("mine"))

            repository.add(_task("theirs", user_id=OTHER_USER_ID))

            assert repository.get_by_id("theirs") is not None

    def test_legacy_rows_without_a_key_never_collide(self, session_factory: Any) -> None:
        with session_factory() as session:
            repository = SQLAlchemyTaskRepository(session)
            repository.add(_task("legacy-1", submission_key=None))

            repository.add(_task("legacy-2", submission_key=None))

            assert repository.count(q=None, status="processing") == 2


@pytest.mark.integration
class TestListPaginated:
    def test_list_rows_never_load_the_transcript(self, session_factory: Any) -> None:
        with session_factory() as session:
            repository = SQLAlchemyTaskRepository(session)
            repository.add(
                _task("with-result", status="completed", result={"segments": [{"text": "x"}]})
            )

            tasks = repository.list_paginated(q=None, status=None, offset=0, limit=10)

        assert [task.uuid for task in tasks] == ["with-result"]
        assert tasks[0].result is None

    def test_newest_first(self, session_factory: Any) -> None:
        base_time = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
        with session_factory() as session:
            repository = SQLAlchemyTaskRepository(session)
            for offset_minutes, uuid in ((0, "oldest"), (10, "newest"), (5, "middle")):
                repository.add(
                    _task(
                        uuid,
                        status="completed",
                        submission_key=None,
                        created_at=base_time + timedelta(minutes=offset_minutes),
                    )
                )

            tasks = repository.list_paginated(q=None, status=None, offset=0, limit=10)

        assert [task.uuid for task in tasks] == ["newest", "middle", "oldest"]

    def test_list_index_exists(self, session_factory: Any) -> None:
        engine = session_factory.kw["bind"]
        index_names = {index["name"] for index in inspect(engine).get_indexes(ORMTask.__tablename__)}

        assert {"idx_tasks_user_id_created_at", "uq_tasks_in_flight_submission"} <= index_names
