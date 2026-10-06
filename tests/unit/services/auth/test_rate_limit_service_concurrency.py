"""RateLimitService under concurrent requests on a real SQLite file.

Each thread has its own session and connection, as parallel threadpool
requests do; BEGIN IMMEDIATE must serialize read -> consume -> write.
"""

import threading
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.infrastructure.database.models import Base
from app.infrastructure.database.repositories.sqlalchemy_rate_limit_repository import (
    SQLAlchemyRateLimitRepository,
)
from app.services.auth.rate_limit_service import RateLimitService

THREAD_COUNT = 8
CAPACITY = 3


@pytest.fixture
def session_factory(tmp_path: Path) -> Any:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'buckets.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _in_parallel(session_factory: Any, action: Any) -> list[Any]:
    start_together = threading.Barrier(THREAD_COUNT)
    results: list[Any] = []
    results_lock = threading.Lock()

    def worker() -> None:
        with session_factory() as session:
            service = RateLimitService(SQLAlchemyRateLimitRepository(session))
            start_together.wait()
            outcome = action(service)
        with results_lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(THREAD_COUNT)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert len(results) == THREAD_COUNT
    return results


@pytest.mark.unit
class TestConcurrentBuckets:
    @pytest.mark.parametrize("round_number", range(3))
    def test_concurrent_checks_never_over_admit(self, session_factory: Any, round_number: int) -> None:
        bucket_key = f"user:{round_number}:concurrent"

        admitted = _in_parallel(
            session_factory,
            lambda service: service.check_and_consume(
                bucket_key, tokens_needed=1, rate=0, capacity=CAPACITY
            ),
        )

        assert admitted.count(True) == CAPACITY

    def test_concurrent_releases_all_count(self, session_factory: Any) -> None:
        bucket_key = "user:9:concurrent"
        with session_factory() as session:
            service = RateLimitService(SQLAlchemyRateLimitRepository(session))
            for _ in range(THREAD_COUNT):
                assert service.check_and_consume(
                    bucket_key, tokens_needed=1, rate=0, capacity=THREAD_COUNT
                )

        _in_parallel(
            session_factory,
            lambda service: service.release(bucket_key, tokens=1, capacity=THREAD_COUNT),
        )

        with session_factory() as session:
            bucket = SQLAlchemyRateLimitRepository(session).get_by_key(bucket_key)
        assert bucket is not None
        assert bucket.tokens == THREAD_COUNT
