"""FreeTierGate.release_admission returns every bucket a check() consumed.

Real RateLimitService on a SQLite file, so the refund lands in the same
buckets the check charged.
"""

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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
