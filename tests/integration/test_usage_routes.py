"""Integration tests for GET /api/usage (quick-260505-l2w).

Coverage:
  1. Unauthenticated GET returns 401 (matches dual-auth-failure shape).
  2. Authenticated trial user with no buckets: 200 + zero counts + free limits.
  3. Authenticated user with hour bucket pre-seeded: hour_count > 0.
  4. Authenticated pro user: pro limits surfaced.
  5. CSRF NOT required on GET (no X-CSRF-Token header still returns 200).
  6. Response shape locked: exactly 9 declared fields (T-15-11 mirror).

Phase 19 Plan 10 fixture migration (mirrors test_account_routes.py):
  - slim FastAPI app per test (auth_router + usage_router)
  - app.dependency_overrides[get_db] is the SOLE DB-binding seam
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api import dependencies
from app.api.auth_routes import auth_router
from app.api.exception_handlers import (
    invalid_credentials_handler,
    validation_error_handler,
)
from app.api.usage_routes import usage_router
from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import Base


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------


@pytest.fixture
def tmp_db_url(tmp_path) -> str:
    """File-backed SQLite URL with all tables pre-created."""
    db_file = tmp_path / "usage_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    return url


@pytest.fixture
def session_factory(tmp_db_url: str):
    engine = create_engine(tmp_db_url, connect_args={"check_same_thread": False})
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def usage_app(
    tmp_db_url: str, session_factory
) -> Generator[FastAPI, None, None]:
    """Slim FastAPI app: auth_router + usage_router driven via dependency_overrides."""
    limiter.reset()

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(InvalidCredentialsError, invalid_credentials_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.include_router(auth_router)
    app.include_router(usage_router)

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


@pytest.fixture
def client(usage_app: FastAPI) -> TestClient:
    return TestClient(usage_app)


def _register(client: TestClient, email: str, password: str = "supersecret123") -> int:
    response = client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    csrf = client.cookies.get("csrf_token")
    assert csrf is not None
    client.headers["X-CSRF-Token"] = csrf
    return int(response.json()["user_id"])


def _set_plan_tier(session_factory, *, user_id: int, plan_tier: str) -> None:
    with session_factory() as session:
        session.execute(
            text("UPDATE users SET plan_tier = :pt WHERE id = :uid"),
            {"pt": plan_tier, "uid": user_id},
        )
        session.commit()


def _set_trial_started_at(session_factory, *, user_id: int, value: str) -> None:
    """Write a tz-naive timestamp string the way SQLite persists DATETIME columns."""
    with session_factory() as session:
        session.execute(
            text("UPDATE users SET trial_started_at = :ts WHERE id = :uid"),
            {"ts": value, "uid": user_id},
        )
        session.commit()


def _seed_api_key(
    session_factory, *, user_id: int, name: str, prefix: str, revoked: bool = False
) -> int:
    """Insert an api_keys row; return its id."""
    with session_factory() as session:
        result = session.execute(
            text(
                "INSERT INTO api_keys "
                "(user_id, name, prefix, hash, scopes, created_at, revoked_at) "
                "VALUES (:uid, :name, :prefix, :hash, 'transcribe', :ts, :rev)"
            ),
            {
                "uid": user_id,
                "name": name,
                "prefix": prefix,
                "hash": f"hash-{prefix}",
                "ts": datetime.now(timezone.utc),
                "rev": datetime.now(timezone.utc) if revoked else None,
            },
        )
        session.commit()
        return int(result.lastrowid)


def _seed_usage_event(
    session_factory,
    *,
    user_id: int,
    idempotency_key: str,
    file_seconds: float,
    api_key_id: int | None,
) -> None:
    """Insert a usage_events row with optional api_key attribution."""
    with session_factory() as session:
        session.execute(
            text(
                "INSERT INTO usage_events "
                "(user_id, api_key_id, gpu_seconds, file_seconds, model, "
                "idempotency_key, created_at) "
                "VALUES (:uid, :akid, 1.0, :fs, 'tiny', :idem, :ts)"
            ),
            {
                "uid": user_id,
                "akid": api_key_id,
                "fs": file_seconds,
                "idem": idempotency_key,
                "ts": datetime.now(timezone.utc),
            },
        )
        session.commit()


def _seed_bucket(
    session_factory,
    *,
    bucket_key: str,
    tokens: int,
    last_refill: datetime,
) -> None:
    with session_factory() as session:
        session.execute(
            text(
                "INSERT INTO rate_limit_buckets (bucket_key, tokens, last_refill) "
                "VALUES (:k, :t, :ts)"
            ),
            {"k": bucket_key, "t": tokens, "ts": last_refill},
        )
        session.commit()


# ---------------------------------------------------------------
# Tests
# ---------------------------------------------------------------


@pytest.mark.integration
def test_get_usage_unauthenticated_returns_401(usage_app: FastAPI) -> None:
    """GET /api/usage without auth -> 401."""
    anon = TestClient(usage_app)
    response = anon.get("/api/usage")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.integration
def test_get_usage_no_buckets_returns_zero_counts(
    client: TestClient,
) -> None:
    """Trial user, freshly registered: hour_count=0, daily_minutes_used=0.0."""
    _register(client, "trial-user@example.com")
    response = client.get("/api/usage")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan_tier"] == "trial"
    assert body["hour_count"] == 0
    assert body["daily_minutes_used"] == 0.0
    assert body["hour_limit"] == 5
    assert body["daily_minutes_limit"] == 30.0


@pytest.mark.integration
def test_get_usage_with_hour_bucket_returns_real_count(
    client: TestClient,
    session_factory,
) -> None:
    """Hour bucket with tokens=2, last_refill=now -> hour_count == 3 (no refill drift)."""
    user_id = _register(client, "hour-bucket@example.com")
    _seed_bucket(
        session_factory,
        bucket_key=f"user:{user_id}:tx:hour",
        tokens=2,
        last_refill=datetime.now(timezone.utc),
    )
    response = client.get("/api/usage")
    assert response.status_code == 200, response.text
    body = response.json()
    # capacity=5, tokens=2, no elapsed -> hour_count = 5 - 2 = 3.
    # NOTE: small clock-drift between last_refill and now_utc inside service may refill +1 token.
    # Allow [3, 4] range (typical drift well under 1s).
    assert body["hour_count"] in (3, 4), f"unexpected hour_count: {body['hour_count']}"


@pytest.mark.integration
def test_get_usage_pro_user_returns_pro_limits(
    client: TestClient,
    session_factory,
) -> None:
    """plan_tier='pro' -> hour_limit=100, daily_minutes_limit=1440.0 (PRO_POLICY 24h)."""
    user_id = _register(client, "pro@example.com")
    _set_plan_tier(session_factory, user_id=user_id, plan_tier="pro")
    response = client.get("/api/usage")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan_tier"] == "pro"
    assert body["hour_limit"] == 100
    assert body["daily_minutes_limit"] == 1440.0


@pytest.mark.integration
def test_get_usage_trial_dates_are_timezone_aware(
    client: TestClient,
    session_factory,
) -> None:
    """Regression: non-null trial_started_at must serialise with a tz designator.

    SQLite drops tzinfo, so a persisted DATETIME reads back naive and
    isoformat()s to a string with NO timezone. The frontend Zod contract is
    ``.datetime({ offset: true })`` which rejects such strings, surfacing as
    'Could not load usage.' The user_mapper now normalises to UTC-aware.
    """
    user_id = _register(client, "trial-dates@example.com")
    _set_trial_started_at(
        session_factory, user_id=user_id, value="2026-05-18 16:42:21.806094"
    )
    response = client.get("/api/usage")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["trial_started_at"] is not None
    assert body["trial_expires_at"] is not None
    # Must carry a timezone designator (Z or +HH:MM) — else Zod rejects.
    assert body["trial_started_at"].endswith(("Z", "+00:00"))
    assert body["trial_expires_at"].endswith(("Z", "+00:00"))


@pytest.mark.integration
def test_get_usage_csrf_not_required_on_get(
    client: TestClient,
) -> None:
    """GET without X-CSRF-Token must NOT 403 (csrf_protected early-returns on GET)."""
    _register(client, "no-csrf@example.com")
    # Strip the auto-attached header
    client.headers.pop("X-CSRF-Token", None)
    response = client.get("/api/usage")
    assert response.status_code == 200, response.text
    assert response.status_code != 403


@pytest.mark.integration
def test_get_usage_by_key_aggregates_and_buckets_unattributed(
    client: TestClient,
    session_factory,
) -> None:
    """Events group by api_key_id; NULL-key rows collapse to one bucket."""
    user_id = _register(client, "by-key@example.com")
    key_id = _seed_api_key(
        session_factory, user_id=user_id, name="livestream-pc", prefix="AhUddB8W"
    )
    # Two attributed events (90s + 30s = 2.0 min) + one unattributed (60s = 1.0 min).
    _seed_usage_event(
        session_factory, user_id=user_id, idempotency_key="e1",
        file_seconds=90.0, api_key_id=key_id,
    )
    _seed_usage_event(
        session_factory, user_id=user_id, idempotency_key="e2",
        file_seconds=30.0, api_key_id=key_id,
    )
    _seed_usage_event(
        session_factory, user_id=user_id, idempotency_key="e3",
        file_seconds=60.0, api_key_id=None,
    )

    response = client.get("/api/usage/by-key")
    assert response.status_code == 200, response.text
    keys = response.json()["keys"]

    # Busiest key first (2.0 min > 1.0 min).
    assert len(keys) == 2
    attributed, unattributed = keys[0], keys[1]

    assert attributed["api_key_id"] == key_id
    assert attributed["name"] == "livestream-pc"
    assert attributed["prefix"] == "AhUddB8W"
    assert attributed["revoked"] is False
    assert attributed["transcription_count"] == 2
    assert attributed["minutes_used"] == 2.0
    assert attributed["last_used_at"].endswith(("Z", "+00:00"))

    assert unattributed["api_key_id"] is None
    assert unattributed["name"] is None
    assert unattributed["transcription_count"] == 1
    assert unattributed["minutes_used"] == 1.0


@pytest.mark.integration
def test_get_usage_by_key_empty_when_no_events(client: TestClient) -> None:
    """Fresh user with no usage_events -> empty keys list."""
    _register(client, "no-events@example.com")
    response = client.get("/api/usage/by-key")
    assert response.status_code == 200, response.text
    assert response.json()["keys"] == []


@pytest.mark.integration
def test_get_usage_by_key_unauthenticated_returns_401(usage_app: FastAPI) -> None:
    """GET /api/usage/by-key without auth -> 401."""
    anon = TestClient(usage_app)
    response = anon.get("/api/usage/by-key")
    assert response.status_code == 401


@pytest.mark.integration
def test_get_usage_response_shape_locked(client: TestClient) -> None:
    """Response keys are EXACTLY the 9 declared UsageSummaryResponse fields."""
    _register(client, "shape@example.com")
    response = client.get("/api/usage")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {
        "plan_tier",
        "trial_started_at",
        "trial_expires_at",
        "hour_count",
        "hour_limit",
        "daily_minutes_used",
        "daily_minutes_limit",
        "window_resets_at",
        "day_resets_at",
    }
