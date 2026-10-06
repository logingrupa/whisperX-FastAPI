"""FreeTierGate.release_admission returns every bucket a check() consumed.

Real RateLimitService on a SQLite file, so the refund lands in the same
buckets the check charged.
"""

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import ConcurrencyLimitError, RateLimitExceededError
from app.domain.entities.user import User
from app.infrastructure.database.models import Base
from app.infrastructure.database.repositories.sqlalchemy_rate_limit_repository import (
    SQLAlchemyRateLimitRepository,
)
from app.services.auth.rate_limit_service import RateLimitService
from app.services.free_tier_gate import (
    FreeTierGate,
    concurrency_bucket_key,
    daily_minutes_bucket_key,
    hourly_bucket_key,
)

FREE_USER = User(id=7, email="free@x.com", password_hash="x", plan_tier="free")


@pytest.fixture
def session_factory(tmp_path: Path) -> Any:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'gate.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _bucket_tokens(session_factory: Any) -> dict[str, int]:
    with session_factory() as session:
        repository = SQLAlchemyRateLimitRepository(session)
        return {
            name: repository.get_by_key(key).tokens  # type: ignore[union-attr]
            for name, key in (
                ("hourly", hourly_bucket_key(7)),
                ("daily_minutes", daily_minutes_bucket_key(7)),
                ("concurrency", concurrency_bucket_key(7)),
            )
        }


@pytest.mark.integration
def test_release_admission_undoes_a_check(session_factory: Any) -> None:
    with session_factory() as session:
        gate = FreeTierGate(RateLimitService(SQLAlchemyRateLimitRepository(session)))
        gate.check(user=FREE_USER, file_seconds=240.0, model="tiny", diarize=False)
    charged = _bucket_tokens(session_factory)

    with session_factory() as session:
        gate = FreeTierGate(RateLimitService(SQLAlchemyRateLimitRepository(session)))
        gate.release_admission(FREE_USER, 240.0)
    refunded = _bucket_tokens(session_factory)

    assert charged == {"hourly": 4, "daily_minutes": 26, "concurrency": 0}
    assert refunded == {"hourly": 5, "daily_minutes": 30, "concurrency": 1}


def _gate(session_factory: Any) -> tuple[Any, FreeTierGate]:
    session = session_factory()
    return session, FreeTierGate(RateLimitService(SQLAlchemyRateLimitRepository(session)))


@pytest.mark.integration
def test_concurrency_rejection_gives_back_hourly_and_daily(session_factory: Any) -> None:
    session, gate = _gate(session_factory)
    gate.check(user=FREE_USER, file_seconds=240.0, model="tiny", diarize=False)
    before = _bucket_tokens(session_factory)

    with pytest.raises(ConcurrencyLimitError):
        gate.check(user=FREE_USER, file_seconds=240.0, model="tiny", diarize=False)
    session.close()

    assert _bucket_tokens(session_factory) == before


@pytest.mark.integration
def test_daily_rejection_gives_back_the_hourly_token(session_factory: Any) -> None:
    session, gate = _gate(session_factory)
    RateLimitService(SQLAlchemyRateLimitRepository(session)).check_and_consume(
        daily_minutes_bucket_key(7), tokens_needed=29, rate=0, capacity=30
    )

    with pytest.raises(RateLimitExceededError):
        gate.check(user=FREE_USER, file_seconds=240.0, model="tiny", diarize=False)
    session.close()

    with session_factory() as check_session:
        hourly = SQLAlchemyRateLimitRepository(check_session).get_by_key(hourly_bucket_key(7))
    assert hourly is not None and hourly.tokens == 5
