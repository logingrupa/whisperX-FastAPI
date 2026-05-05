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
    """plan_tier='pro' -> hour_limit=100, daily_minutes_limit=600.0."""
    user_id = _register(client, "pro@example.com")
    _set_plan_tier(session_factory, user_id=user_id, plan_tier="pro")
    response = client.get("/api/usage")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan_tier"] == "pro"
    assert body["hour_limit"] == 100
    assert body["daily_minutes_limit"] == 600.0


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
