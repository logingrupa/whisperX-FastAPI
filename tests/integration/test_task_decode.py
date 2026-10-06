"""decode_task_audio: the background job holds a task to its decoded length.

Real SQLite file (Base.metadata.create_all); only the ffmpeg decode is stubbed.
"""

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import audio as audio_module
from app.core.exceptions import FreeTierViolationError, RateLimitExceededError
from app.domain.entities.task import Task
from app.infrastructure.database.models import ApiKey as ORMApiKey
from app.infrastructure.database.models import Base
from app.infrastructure.database.models import User as ORMUser
from app.infrastructure.database.repositories.sqlalchemy_rate_limit_repository import (
    SQLAlchemyRateLimitRepository,
)
from app.infrastructure.database.repositories.sqlalchemy_task_repository import (
    SQLAlchemyTaskRepository,
)
from app.services.auth.rate_limit_service import RateLimitService
from app.services.free_tier_gate import daily_minutes_bucket_key
from app.services.task_decode import decode_task_audio

TRIAL_USER_ID = 401
UNLIMITED_KEY_ID = 41
TRIAL_FILE_CAP_SECONDS = 300
TRIAL_DAILY_MINUTES = 30


@pytest.fixture
def session_factory(tmp_path: Path) -> Any:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'decode.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with factory() as session:
        session.add(ORMUser(id=TRIAL_USER_ID, email="trial@x.com", password_hash="x", plan_tier="trial"))
        session.commit()  # the key's FK needs the user row first
        session.add(
            ORMApiKey(
                id=UNLIMITED_KEY_ID,
                user_id=TRIAL_USER_ID,
                name="owner-pipeline",
                prefix="unlimit1",
                hash="h",
                unlimited=True,
            )
        )
        session.commit()
    return factory


def _decode_returning_seconds(monkeypatch: pytest.MonkeyPatch, seconds: float) -> None:
    waveform = np.zeros(int(audio_module.SAMPLE_RATE * seconds), dtype=np.float32)
    monkeypatch.setattr(audio_module, "process_audio_file", lambda _path: waveform)


def _add_task(
    session_factory: Any, *, probed_seconds: float, api_key_id: int | None = None
) -> None:
    with session_factory() as session:
        SQLAlchemyTaskRepository(session).add(
            Task(
                uuid="task-1",
                status="processing",
                task_type="transcription",
                user_id=TRIAL_USER_ID,
                api_key_id=api_key_id,
                audio_duration=probed_seconds,
            )
        )


def _daily_tokens_left(session_factory: Any) -> int:
    with session_factory() as session:
        bucket = SQLAlchemyRateLimitRepository(session).get_by_key(
            daily_minutes_bucket_key(TRIAL_USER_ID)
        )
    assert bucket is not None
    return bucket.tokens


def _charge_at_submit(session_factory: Any, seconds: float) -> None:
    """Consume the daily minutes the submit gate charged for ``seconds``."""
    with session_factory() as session:
        service = RateLimitService(SQLAlchemyRateLimitRepository(session))
        assert service.check_and_consume(
            daily_minutes_bucket_key(TRIAL_USER_ID),
            tokens_needed=max(1, int(seconds / 60)),
            rate=TRIAL_DAILY_MINUTES / 86400.0,
            capacity=TRIAL_DAILY_MINUTES,
        )


def _stored_seconds(session_factory: Any) -> float | None:
    with session_factory() as session:
        task = SQLAlchemyTaskRepository(session).get_by_id("task-1")
        assert task is not None
        return task.audio_duration


@pytest.mark.integration
class TestDecodeTaskAudio:
    def test_matching_length_leaves_the_task_alone(
        self, session_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _add_task(session_factory, probed_seconds=120.0)
        _decode_returning_seconds(monkeypatch, 120.4)

        with session_factory() as session:
            audio = decode_task_audio(session, "task-1", "upload.ogg")

        assert len(audio) == int(audio_module.SAMPLE_RATE * 120.4)
        assert _stored_seconds(session_factory) == pytest.approx(120.0)

    def test_truncated_file_bills_the_shorter_decoded_length(
        self, session_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _add_task(session_factory, probed_seconds=290.0)
        _decode_returning_seconds(monkeypatch, 150.0)

        with session_factory() as session:
            decode_task_audio(session, "task-1", "partial-download.mp3")

        assert _stored_seconds(session_factory) == pytest.approx(150.0)

    def test_forged_short_header_cannot_bypass_the_trial_file_cap(
        self, session_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _add_task(session_factory, probed_seconds=26.0)
        _decode_returning_seconds(monkeypatch, TRIAL_FILE_CAP_SECONDS + 300)

        with session_factory() as session:
            with pytest.raises(FreeTierViolationError, match="exceeds tier limit"):
                decode_task_audio(session, "task-1", "forged.mp3")

        assert _stored_seconds(session_factory) == pytest.approx(TRIAL_FILE_CAP_SECONDS + 300)

    def test_unlimited_key_task_is_never_capped(
        self, session_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _add_task(session_factory, probed_seconds=26.0, api_key_id=UNLIMITED_KEY_ID)
        _decode_returning_seconds(monkeypatch, TRIAL_FILE_CAP_SECONDS + 300)

        with session_factory() as session:
            decode_task_audio(session, "task-1", "long-sermon.ogg")

        assert _stored_seconds(session_factory) == pytest.approx(TRIAL_FILE_CAP_SECONDS + 300)

    def test_longer_decoded_audio_charges_the_extra_daily_minutes(
        self, session_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _add_task(session_factory, probed_seconds=26.0)
        _charge_at_submit(session_factory, 26.0)
        _decode_returning_seconds(monkeypatch, 280.0)

        with session_factory() as session:
            decode_task_audio(session, "task-1", "forged.webm")

        assert _daily_tokens_left(session_factory) == TRIAL_DAILY_MINUTES - 4

    def test_shorter_decoded_audio_refunds_daily_minutes(
        self, session_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _add_task(session_factory, probed_seconds=290.0)
        _charge_at_submit(session_factory, 290.0)
        _decode_returning_seconds(monkeypatch, 130.0)

        with session_factory() as session:
            decode_task_audio(session, "task-1", "partial-download.mp3")

        assert _daily_tokens_left(session_factory) == TRIAL_DAILY_MINUTES - 2

    def test_day_budget_short_of_the_decoded_length_fails_the_job(
        self, session_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _add_task(session_factory, probed_seconds=60.0)
        _charge_at_submit(session_factory, 60.0)
        _charge_at_submit(session_factory, 27 * 60)
        _decode_returning_seconds(monkeypatch, 290.0)

        with session_factory() as session:
            with pytest.raises(RateLimitExceededError):
                decode_task_audio(session, "task-1", "forged.webm")
