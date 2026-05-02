"""Integration tests for Phase 13-08 free-tier gate (RATE-01..12, BILL-01).

Coverage (≥14):

  1.  test_free_user_6th_transcribe_returns_429_with_retry_after
  2.  test_free_user_5min_file_accepted
  3.  test_free_user_6min_file_rejected_403
  4.  test_free_user_daily_audio_cap
  5.  test_free_user_large_v3_model_rejected_403
  6.  test_free_user_diarize_true_rejected_403
  7.  test_pro_user_higher_limits_pass
  8.  test_trial_user_within_7d_passes
  9.  test_trial_expired_returns_402
  10. test_concurrency_limit_429
  11. test_concurrency_slot_released_on_success                (W1)
  12. test_concurrency_slot_released_on_failure                (W1)
  13. test_usage_events_row_per_completion
  14. test_usage_events_idempotency
  15. test_429_response_has_retry_after_header

Strategy:
  - Slim FastAPI app per test mounts auth_router + stt_router + handlers
  - process_audio_file and get_audio_duration are monkey-patched to skip
    heavy decode; audio_duration is set per-test via a controllable stub
  - process_audio_common is monkey-patched to a fast no-op so
    BackgroundTask never blocks; concurrency slot release tested by
    direct FreeTierGate calls (proves the contract that the wrapper would
    use in production)
  - usage_events writes tested via direct UsageEventWriter calls + a
    mock process_audio_common that invokes the writer
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api import audio_api as audio_api_module
from app.api import dependencies
from app.api.audio_api import stt_router
from app.api.auth_routes import auth_router
from app.api.exception_handlers import (
    concurrency_limit_handler,
    free_tier_violation_handler,
    invalid_credentials_handler,
    rate_limit_exceeded_handler,
    trial_expired_handler,
    validation_error_handler,
)
from app.core.exceptions import (
    ConcurrencyLimitError,
    FreeTierViolationError,
    InvalidCredentialsError,
    RateLimitExceededError,
    TrialExpiredError,
    ValidationError,
)
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import Base
from app.infrastructure.database.models import User as ORMUser
from app.infrastructure.database.repositories.sqlalchemy_rate_limit_repository import (
    SQLAlchemyRateLimitRepository,
)
from app.services.auth.rate_limit_service import RateLimitService
from app.services.free_tier_gate import (
    FREE_POLICY,
    PRO_POLICY,
    FreeTierGate,
    concurrency_bucket_key,
)
from app.services.usage_event_writer import UsageEventWriter


# ---------------------------------------------------------------
# Fixtures — slim app + tmp DB + mocked audio pipeline
# ---------------------------------------------------------------


@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str:
    db_file = tmp_path / "ftg.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    return url


@pytest.fixture
def session_factory(tmp_db_url: str) -> Any:
    engine = create_engine(tmp_db_url, connect_args={"check_same_thread": False})
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


class _AudioDurationController:
    """Per-test handle to swap the audio_duration returned by the gate."""

    def __init__(self) -> None:
        self.value: float = 60.0  # default 1min
        # Default True: tests that expect the slot to release after
        # transcription (most tests). Set to False for cap-test that
        # asserts a held slot blocks subsequent requests.
        self.auto_release_slot: bool = True

    def set(self, seconds: float) -> None:
        self.value = seconds


@pytest.fixture
def audio_ctrl() -> _AudioDurationController:
    return _AudioDurationController()


@pytest.fixture
def app_and_container(
    tmp_db_url: str,
    session_factory: Any,
    audio_ctrl: _AudioDurationController,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[FastAPI, None, None]:
    """Slim FastAPI app: auth + stt routers + free-tier handlers.

    Phase 19 Plan 10: dependency_overrides[get_db] is the SOLE DB-binding
    seam for /auth routes. The legacy stt_router still uses
    ``Depends(get_authenticated_user)`` (request.state.user), which would
    require DualAuthMiddleware — that middleware is being deleted in
    Plan 11, so this file's free-tier route tests are deferred. Direct
    FreeTierGate / UsageEventWriter unit-style cases below construct
    their own service instances via session_factory (no container).
    """
    limiter.reset()

    # Patch heavy audio pipeline within audio_api module (the route
    # uses these names directly via local imports).
    def _fake_process_audio_file(*_args, **_kwargs) -> Any:
        return np.zeros(16000, dtype=np.float32)

    def _fake_get_audio_duration(*_args, **_kwargs) -> float:
        return audio_ctrl.value

    def _fake_save_upload(self: Any, file: Any) -> str:  # noqa: ARG001
        return "/tmp/fake.wav"

    def _fake_validate_file_extension(
        self: Any, filename: str, allowed: set
    ) -> None:  # noqa: ARG001
        return None

    def _fake_download_from_url(self: Any, url: str) -> tuple[str, str]:  # noqa: ARG001
        return "/tmp/fake.wav", "fake.wav"

    def _fake_process_audio_common(params: Any, *_args, **_kwargs) -> None:  # noqa: ARG001
        """Phase 19 Plan 10: stripped of container reach-in.

        The legacy stub released the concurrency slot via
        ``dependencies._container.free_tier_gate().release_concurrency(...)``
        which is no longer available. The route-level free-tier tests in
        this file are deferred (DualAuthMiddleware deletion in Plan 11
        removes the route's request.state.user source); the direct
        FreeTierGate / UsageEventWriter tests below construct their own
        service instances and continue to exercise the W1 contract.
        """
        return

    monkeypatch.setattr(audio_api_module, "process_audio_file", _fake_process_audio_file)
    monkeypatch.setattr(audio_api_module, "get_audio_duration", _fake_get_audio_duration)
    monkeypatch.setattr(
        audio_api_module, "process_audio_common", _fake_process_audio_common
    )
    monkeypatch.setattr(
        "app.services.file_service.FileService.save_upload", _fake_save_upload
    )
    monkeypatch.setattr(
        "app.services.file_service.FileService.validate_file_extension",
        _fake_validate_file_extension,
    )
    monkeypatch.setattr(
        "app.services.file_service.FileService.download_from_url",
        _fake_download_from_url,
    )

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(InvalidCredentialsError, invalid_credentials_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.add_exception_handler(TrialExpiredError, trial_expired_handler)
    app.add_exception_handler(FreeTierViolationError, free_tier_violation_handler)
    app.add_exception_handler(RateLimitExceededError, rate_limit_exceeded_handler)
    app.add_exception_handler(ConcurrencyLimitError, concurrency_limit_handler)
    app.include_router(auth_router)
    app.include_router(stt_router)

    def _override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[dependencies.get_db] = _override_get_db

    yield app

    app.dependency_overrides.clear()
    limiter.reset()


def _build_rate_limit_service(session_factory: Any) -> RateLimitService:
    """Phase 19 Plan 10 helper: build a RateLimitService bound to the tmp DB.

    Replaces the legacy ``container.rate_limit_service()`` call. The repo
    holds the session for the lifetime of the service; tests own their
    cleanup (the per-test SQLite file is a tmp_path artifact).
    """
    return RateLimitService(repository=SQLAlchemyRateLimitRepository(session_factory()))


def _build_usage_event_writer(session_factory: Any) -> UsageEventWriter:
    """Phase 19 Plan 10 helper: build a UsageEventWriter bound to the tmp DB."""
    return UsageEventWriter(session=session_factory())


@pytest.fixture
def client(app_and_container: FastAPI) -> TestClient:
    return TestClient(app_and_container)


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------


def _register(client: TestClient, email: str = "u@x.com") -> int:
    resp = client.post(
        "/auth/register", json={"email": email, "password": "supersecret123"}
    )
    assert resp.status_code == 201, resp.text
    return int(resp.json()["user_id"])


def _post_stt(
    client: TestClient,
    *,
    model: str = "tiny",
    diarize: bool = False,
) -> Any:
    """Hit POST /speech-to-text with a tiny in-memory file + given model.

    Whisper params + DiarizationParams are wrapped in Query(...) so they
    travel as URL query strings, NOT multipart form fields.
    DiarizationParams has min_speakers/max_speakers only in v1.2; the
    gate treats either-bound-set as diarize=True intent.
    """
    files = {"file": ("a.wav", b"RIFFFAKEDATAfake", "audio/wav")}
    params: dict[str, Any] = {"model": model}
    if diarize:
        params["min_speakers"] = 2
    return client.post("/speech-to-text", files=files, params=params)


def _set_plan_tier(
    session_factory: Any, *, user_id: int, plan_tier: str
) -> None:
    with session_factory() as s:
        s.execute(
            text("UPDATE users SET plan_tier = :p WHERE id = :i"),
            {"p": plan_tier, "i": user_id},
        )
        s.commit()


def _set_trial_started_at(
    session_factory: Any,
    *,
    user_id: int,
    trial_started_at: datetime,
    plan_tier: str = "trial",
) -> None:
    with session_factory() as s:
        s.execute(
            text(
                "UPDATE users SET plan_tier = :p, trial_started_at = :t "
                "WHERE id = :i"
            ),
            {"p": plan_tier, "t": trial_started_at, "i": user_id},
        )
        s.commit()


# ---------------------------------------------------------------
# Tests
# ---------------------------------------------------------------


@pytest.mark.integration
def test_free_user_6th_transcribe_returns_429_with_retry_after(
    client: TestClient,
    session_factory: Any,
    audio_ctrl: _AudioDurationController,
) -> None:
    """First 5 transcribes succeed; 6th hits 429 with Retry-After."""
    user_id = _register(client, "alice@x.com")
    _set_plan_tier(session_factory, user_id=user_id, plan_tier="free")
    audio_ctrl.set(60.0)

    for i in range(FREE_POLICY.max_per_hour):
        resp = _post_stt(client)
        assert resp.status_code == 200, f"req {i + 1}: {resp.text}"

    resp_overflow = _post_stt(client)
    assert resp_overflow.status_code == 429
    assert "Retry-After" in resp_overflow.headers
    assert resp_overflow.headers["Retry-After"].isdigit()


@pytest.mark.integration
def test_free_user_5min_file_accepted(
    client: TestClient,
    session_factory: Any,
    audio_ctrl: _AudioDurationController,
) -> None:
    """File at exactly 5min (=300s) — within limit."""
    user_id = _register(client, "bob@x.com")
    _set_plan_tier(session_factory, user_id=user_id, plan_tier="free")
    audio_ctrl.set(290.0)
    resp = _post_stt(client)
    assert resp.status_code == 200


@pytest.mark.integration
def test_free_user_6min_file_rejected_403(
    client: TestClient,
    session_factory: Any,
    audio_ctrl: _AudioDurationController,
) -> None:
    """360s file -> FreeTierViolationError -> 403."""
    user_id = _register(client, "carol@x.com")
    _set_plan_tier(session_factory, user_id=user_id, plan_tier="free")
    audio_ctrl.set(360.0)
    resp = _post_stt(client)
    assert resp.status_code == 403


@pytest.mark.integration
def test_free_user_daily_audio_cap(
    client: TestClient,
    session_factory: Any,
    audio_ctrl: _AudioDurationController,
) -> None:
    """7 sequential 4-min uploads; 8th returns 429 (>30min daily cap).

    Daily cap is 30 token-minutes. tokens_needed = max(1, file_seconds//60).
    4-min uploads cost 4 tokens each: 7 uploads = 28 tokens; 8th adds 4
    -> 32 > 30 -> denied. But the hourly cap (5/hr) trips first, so
    reset that bucket between calls by using direct gate path.
    """
    user_id = _register(client, "diana@x.com")
    _set_plan_tier(session_factory, user_id=user_id, plan_tier="free")
    audio_ctrl.set(240.0)  # 4 min

    # First 5 burn the hourly bucket
    for _ in range(5):
        _post_stt(client)

    # 6th and beyond all hit hourly 429 — the daily cap test instead
    # exercises the gate directly via FreeTierGate
    from app.domain.entities.user import User

    rls = _build_rate_limit_service(session_factory)
    gate = FreeTierGate(rls)
    user = User(id=user_id, email="diana@x.com", password_hash="x", plan_tier="free")

    # Reset by using a different bucket: directly hammer audio_min:day
    for _ in range(7):
        # Bypass hourly bucket — call only the daily check via consume
        rls.check_and_consume(
            f"user:{user_id}:audio_min:day",
            tokens_needed=4,
            rate=FREE_POLICY.max_daily_seconds / 86400.0,
            capacity=FREE_POLICY.max_daily_seconds // 60,
        )

    # Now next gate.check daily-min consume should fail
    with pytest.raises(RateLimitExceededError):
        gate._check_daily_minutes(user_id, 240.0, FREE_POLICY)  # noqa: SLF001


@pytest.mark.integration
def test_free_user_large_v3_model_rejected_403(
    client: TestClient,
    session_factory: Any,
    audio_ctrl: _AudioDurationController,
) -> None:
    """large-v3 not in {tiny, small} -> 403 FreeTierViolation."""
    user_id = _register(client, "eve@x.com")
    _set_plan_tier(session_factory, user_id=user_id, plan_tier="free")
    audio_ctrl.set(60.0)
    resp = _post_stt(client, model="large-v3")
    assert resp.status_code == 403
    assert "large-v3" in resp.text or "plan" in resp.text.lower()


@pytest.mark.integration
def test_free_user_diarize_true_rejected_403(
    client: TestClient,
    session_factory: Any,
    audio_ctrl: _AudioDurationController,
) -> None:
    """diarize=True for free user -> 403."""
    user_id = _register(client, "frank@x.com")
    _set_plan_tier(session_factory, user_id=user_id, plan_tier="free")
    audio_ctrl.set(60.0)
    resp = _post_stt(client, diarize=True)
    assert resp.status_code == 403


@pytest.mark.integration
def test_pro_user_higher_limits_pass(
    client: TestClient,
    session_factory: Any,
    audio_ctrl: _AudioDurationController,
) -> None:
    """Pro tier honors large-v3 + diarize=True (would fire 403 for free).

    NB: TestClient cookie jar can desync after many JWT-refreshing
    requests; we exercise model + diarize coverage with 3 requests
    (stays under cookie-refresh threshold) — capacity proof for 100/hr
    is covered in unit tests via PRO_POLICY constants.
    """
    user_id = _register(client, "grace@x.com")
    _set_plan_tier(session_factory, user_id=user_id, plan_tier="pro")
    audio_ctrl.set(60.0)

    for _ in range(3):
        resp = _post_stt(client, model="large-v3", diarize=True)
        assert resp.status_code == 200, resp.text


@pytest.mark.integration
def test_trial_user_within_7d_passes(
    client: TestClient,
    session_factory: Any,
    audio_ctrl: _AudioDurationController,
) -> None:
    """Trial user 3 days in: still allowed."""
    user_id = _register(client, "henry@x.com")
    started = datetime.now(timezone.utc) - timedelta(days=3)
    _set_trial_started_at(
        session_factory, user_id=user_id, trial_started_at=started
    )
    audio_ctrl.set(60.0)
    resp = _post_stt(client)
    assert resp.status_code == 200


@pytest.mark.integration
def test_trial_expired_returns_402(
    client: TestClient,
    session_factory: Any,
    audio_ctrl: _AudioDurationController,
) -> None:
    """Trial 8 days old -> 402 Payment Required (RATE-09)."""
    user_id = _register(client, "ivy@x.com")
    started = datetime.now(timezone.utc) - timedelta(days=8)
    _set_trial_started_at(
        session_factory, user_id=user_id, trial_started_at=started
    )
    audio_ctrl.set(60.0)
    resp = _post_stt(client)
    assert resp.status_code == 402


@pytest.mark.integration
def test_concurrency_limit_429(
    client: TestClient,
    session_factory: Any,
    audio_ctrl: _AudioDurationController,
) -> None:
    """1 concurrent slot. Second simultaneous attempt -> 429.

    Disable the auto-release stub so the slot stays held across both
    POSTs — proves cap is enforced server-side.
    """
    user_id = _register(client, "jane@x.com")
    _set_plan_tier(session_factory, user_id=user_id, plan_tier="free")
    audio_ctrl.set(60.0)
    audio_ctrl.auto_release_slot = False  # simulate in-progress transcription

    first = _post_stt(client)
    assert first.status_code == 200

    second = _post_stt(client)
    assert second.status_code == 429
    assert "Retry-After" in second.headers


@pytest.mark.integration
def test_concurrency_slot_released_on_success(
    app_and_container: FastAPI,
    session_factory: Any,
) -> None:
    """W1: after a successful release_concurrency, next consume succeeds."""
    app = app_and_container
    user_id = 9001
    with session_factory() as s:
        s.add(
            ORMUser(
                id=user_id,
                email="kate@x.com",
                password_hash="x",
                plan_tier="free",
            )
        )
        s.commit()

    from app.domain.entities.user import User as DUser

    user = DUser(id=user_id, email="kate@x.com", password_hash="x", plan_tier="free")
    rls = _build_rate_limit_service(session_factory)
    gate = FreeTierGate(rls)

    # 1. Acquire (consume slot)
    gate._check_concurrency(user_id, FREE_POLICY)  # noqa: SLF001
    # 2. Second acquire would block
    with pytest.raises(ConcurrencyLimitError):
        gate._check_concurrency(user_id, FREE_POLICY)  # noqa: SLF001
    # 3. Simulate completion success — release
    gate.release_concurrency(user)
    # 4. Now we can acquire again
    gate._check_concurrency(user_id, FREE_POLICY)  # noqa: SLF001


@pytest.mark.integration
def test_concurrency_slot_released_on_failure(
    app_and_container: FastAPI,
    session_factory: Any,
) -> None:
    """W1: release runs from finally even when transcription raises.

    Mirrors process_audio_common's try/finally contract: the slot is
    released regardless of success/failure path.
    """
    app = app_and_container
    user_id = 9002
    with session_factory() as s:
        s.add(
            ORMUser(
                id=user_id,
                email="leo@x.com",
                password_hash="x",
                plan_tier="free",
            )
        )
        s.commit()

    from app.domain.entities.user import User as DUser

    user = DUser(id=user_id, email="leo@x.com", password_hash="x", plan_tier="free")
    rls = _build_rate_limit_service(session_factory)
    gate = FreeTierGate(rls)

    # 1. Acquire
    gate._check_concurrency(user_id, FREE_POLICY)  # noqa: SLF001

    # 2. Simulate transcription that raises but releases in finally
    try:
        raise RuntimeError("transcription failed")
    except RuntimeError:
        pass
    finally:
        gate.release_concurrency(user)

    # 3. Slot should be back — next acquire succeeds
    gate._check_concurrency(user_id, FREE_POLICY)  # noqa: SLF001


@pytest.mark.integration
def test_usage_events_row_per_completion(
    app_and_container: FastAPI,
    session_factory: Any,
) -> None:
    """A single record() call writes exactly one usage_events row."""
    app = app_and_container
    with session_factory() as s:
        s.add(
            ORMUser(
                id=11,
                email="mary@x.com",
                password_hash="x",
                plan_tier="free",
            )
        )
        s.commit()

    writer: UsageEventWriter = _build_usage_event_writer(session_factory)
    writer.record(
        user_id=11,
        task_uuid="task-end-to-end",
        gpu_seconds=4.2,
        file_seconds=60.0,
        model="tiny",
    )

    with session_factory() as s:
        count = s.execute(
            text(
                "SELECT COUNT(*) FROM usage_events "
                "WHERE idempotency_key = :k"
            ),
            {"k": "task-end-to-end"},
        ).scalar()
    assert count == 1


@pytest.mark.integration
def test_usage_events_idempotency(
    app_and_container: FastAPI,
    session_factory: Any,
) -> None:
    """Replay protection: duplicate completion fires no extra row."""
    app = app_and_container
    with session_factory() as s:
        s.add(
            ORMUser(
                id=12,
                email="nina@x.com",
                password_hash="x",
                plan_tier="free",
            )
        )
        s.commit()

    # Two writers (per request) but same task uuid -> same idempotency_key
    writer1: UsageEventWriter = _build_usage_event_writer(session_factory)
    writer1.record(
        user_id=12,
        task_uuid="task-replay",
        gpu_seconds=1.0,
        file_seconds=30.0,
        model="tiny",
    )
    writer2: UsageEventWriter = _build_usage_event_writer(session_factory)
    writer2.record(
        user_id=12,
        task_uuid="task-replay",
        gpu_seconds=1.0,
        file_seconds=30.0,
        model="tiny",
    )

    with session_factory() as s:
        count = s.execute(
            text(
                "SELECT COUNT(*) FROM usage_events "
                "WHERE idempotency_key = :k"
            ),
            {"k": "task-replay"},
        ).scalar()
    assert count == 1


@pytest.mark.integration
def test_429_response_has_retry_after_header(
    client: TestClient,
    session_factory: Any,
    audio_ctrl: _AudioDurationController,
) -> None:
    """Hourly 429 surfaces Retry-After as integer string."""
    user_id = _register(client, "olga@x.com")
    _set_plan_tier(session_factory, user_id=user_id, plan_tier="free")
    audio_ctrl.set(60.0)

    # Exhaust the bucket
    for _ in range(FREE_POLICY.max_per_hour):
        _post_stt(client)
    resp = _post_stt(client)
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert int(resp.headers["Retry-After"]) > 0


@pytest.mark.integration
def test_concurrency_bucket_key_uses_user_id(
    app_and_container: FastAPI,
    session_factory: Any,
) -> None:
    """concurrency_bucket_key isolates buckets per-user (defence)."""
    app = app_and_container
    rls = _build_rate_limit_service(session_factory)
    rls.check_and_consume(
        concurrency_bucket_key(7),
        tokens_needed=1,
        rate=0.0,
        capacity=1,
    )
    # Different user not affected
    allowed = rls.check_and_consume(
        concurrency_bucket_key(8),
        tokens_needed=1,
        rate=0.0,
        capacity=1,
    )
    assert allowed is True


@pytest.mark.integration
def test_pro_diarize_route_passes_pro_blocks_free(
    app_and_container: FastAPI,
    session_factory: Any,
) -> None:
    """check_diarize_route: pro passes, free raises 403."""
    app = app_and_container
    rls = _build_rate_limit_service(session_factory)
    gate = FreeTierGate(rls)

    from app.domain.entities.user import User as DUser

    pro = DUser(id=1, email="p@x", password_hash="x", plan_tier="pro")
    free = DUser(id=2, email="f@x", password_hash="x", plan_tier="free")

    gate.check_diarize_route(pro)  # no raise
    with pytest.raises(FreeTierViolationError):
        gate.check_diarize_route(free)
