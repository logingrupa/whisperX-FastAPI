"""Integration tests for Phase 13 ``/api/keys/*`` routes.

Coverage (≥10 cases per plan 13-04):

1.  test_create_key_returns_plaintext_once — POST returns whsk_* plaintext (36 chars)
2.  test_create_key_persists_prefix_and_hash_only — DB has hash, never plaintext
3.  test_create_key_starts_trial_on_first — first key sets users.trial_started_at
4.  test_create_key_idempotent_trial_on_second — second key does NOT reset
5.  test_create_key_multiple_active_allowed — POST 5 → GET 5 active (KEY-06)
6.  test_get_keys_lists_all_with_status — active + revoked items both returned
7.  test_get_keys_no_plaintext_in_list — no `key` field in list items
8.  test_delete_key_soft_deletes — revoked row persists with status=revoked
9.  test_delete_key_cross_user_returns_404 — other user → opaque 404
10. test_delete_unknown_key_returns_404 — missing id → opaque 404
11. test_create_key_requires_auth — POST without auth → 401
12. test_bearer_auth_can_create_key — bearer auth path issues key

Slim FastAPI app per test (mirror 13-03 pattern):
  - mounts auth_router for cookie-acquisition + key_router for /api/keys/*
  - mounts DualAuthMiddleware for both bearer + cookie resolution
  - per-test Container override against tmp SQLite DB
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api import dependencies
from app.api.auth_routes import auth_router
from app.api.exception_handlers import (
    invalid_credentials_handler,
    validation_error_handler,
)
from app.api.key_routes import key_router
from app.core.container import Container
from app.core.dual_auth import DualAuthMiddleware
from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import ApiKey as ORMApiKey
from app.infrastructure.database.models import Base
from app.infrastructure.database.models import User as ORMUser


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------


@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str:
    """File-backed SQLite URL with auth tables pre-created."""
    db_file = tmp_path / "keys_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    return url


@pytest.fixture
def session_factory(tmp_db_url: str):
    """Sessionmaker for direct DB introspection in tests."""
    engine = create_engine(tmp_db_url, connect_args={"check_same_thread": False})
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def keys_app(
    tmp_db_url: str, session_factory
) -> Generator[tuple[FastAPI, Container], None, None]:
    """Slim FastAPI app: auth_router + key_router + DualAuthMiddleware."""
    container = Container()
    container.db_session_factory.override(providers.Factory(session_factory))
    dependencies.set_container(container)

    limiter.reset()

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(InvalidCredentialsError, invalid_credentials_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.include_router(auth_router)
    app.include_router(key_router)
    # DualAuthMiddleware: cookie + bearer auth resolution
    app.add_middleware(DualAuthMiddleware, container=container)

    # Phase 19 Plan 07 additive override (Rule 3): wire app.dependency_overrides
    # for get_db so authenticated_user + csrf_protected resolve against the
    # tmp SQLite. Plan 10 owns the full fixture migration.
    def _override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[dependencies.get_db] = _override_get_db

    yield app, container

    app.dependency_overrides.clear()
    container.unwire()
    container.db_session_factory.reset_override()
    limiter.reset()


@pytest.fixture
def client(keys_app: tuple[FastAPI, Container]) -> TestClient:
    app, _ = keys_app
    return TestClient(app)


def _register(client: TestClient, email: str, password: str = "supersecret123") -> dict:
    """Register a user via /auth/register; returns the response body.

    Phase 19 Plan 07 additive: key_router applies router-level
    Depends(csrf_protected), so cookie-auth POST/DELETEs require
    X-CSRF-Token. Plumb the csrf_token cookie value as a default header on
    the client jar so subsequent state-mutating calls pass the
    double-submit check; legacy test bodies stay untouched.
    """
    response = client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    csrf = client.cookies.get("csrf_token")
    assert csrf is not None, "csrf_token cookie missing after /auth/register"
    client.headers["X-CSRF-Token"] = csrf
    return response.json()


# ---------------------------------------------------------------
# Tests
# ---------------------------------------------------------------


@pytest.mark.integration
def test_create_key_returns_plaintext_once(client: TestClient) -> None:
    """POST /api/keys with cookie auth returns plaintext whsk_* (36 chars)."""
    _register(client, "alice@example.com")
    response = client.post("/api/keys", json={"name": "cli"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["key"].startswith("whsk_")
    assert len(body["key"]) == 36
    assert body["name"] == "cli"
    assert body["status"] == "active"
    assert isinstance(body["id"], int)
    assert isinstance(body["prefix"], str)
    assert len(body["prefix"]) == 8


@pytest.mark.integration
def test_create_key_persists_prefix_and_hash_only(
    client: TestClient, session_factory
) -> None:
    """DB stores prefix + sha256 hash; plaintext is NOT stored anywhere."""
    _register(client, "bob@example.com")
    response = client.post("/api/keys", json={"name": "api-key"})
    assert response.status_code == 201
    plaintext = response.json()["key"]
    # Direct DB check: row exists, no column equals the plaintext
    with session_factory() as session:
        row = session.execute(select(ORMApiKey)).scalar_one()
        assert row.prefix in plaintext  # prefix is a substring of plaintext
        assert row.hash != plaintext  # hash != plaintext
        assert len(row.hash) == 64  # sha256 hex
        assert row.name == "api-key"
        # No column carries the plaintext
        for value in (row.prefix, row.hash, row.name, row.scopes):
            assert value != plaintext


@pytest.mark.integration
def test_create_key_starts_trial_on_first(
    client: TestClient, session_factory
) -> None:
    """First key creation sets users.trial_started_at (RATE-08)."""
    body = _register(client, "carol@example.com")
    user_id = body["user_id"]
    # Pre-condition: trial_started_at is NULL
    with session_factory() as session:
        user = session.execute(
            select(ORMUser).where(ORMUser.id == user_id)
        ).scalar_one()
        assert user.trial_started_at is None
    # Create first key
    response = client.post("/api/keys", json={"name": "first"})
    assert response.status_code == 201
    # Post-condition: trial_started_at populated
    with session_factory() as session:
        user = session.execute(
            select(ORMUser).where(ORMUser.id == user_id)
        ).scalar_one()
        assert user.trial_started_at is not None


@pytest.mark.integration
def test_create_key_idempotent_trial_on_second(
    client: TestClient, session_factory
) -> None:
    """Second key creation does NOT reset trial_started_at (RATE-08 idempotent)."""
    body = _register(client, "dan@example.com")
    user_id = body["user_id"]
    # First key — starts trial
    client.post("/api/keys", json={"name": "first"})
    with session_factory() as session:
        user = session.execute(
            select(ORMUser).where(ORMUser.id == user_id)
        ).scalar_one()
        first_trial_at = user.trial_started_at
        assert first_trial_at is not None
    # Second key — must NOT reset
    response = client.post("/api/keys", json={"name": "second"})
    assert response.status_code == 201
    with session_factory() as session:
        user = session.execute(
            select(ORMUser).where(ORMUser.id == user_id)
        ).scalar_one()
        assert user.trial_started_at == first_trial_at


@pytest.mark.integration
def test_create_key_multiple_active_allowed(client: TestClient) -> None:
    """POST 5 keys; GET returns 5 active items (KEY-06: no cap)."""
    _register(client, "eve@example.com")
    for index in range(5):
        response = client.post("/api/keys", json={"name": f"key-{index}"})
        assert response.status_code == 201
    list_response = client.get("/api/keys")
    assert list_response.status_code == 200
    items = list_response.json()
    assert len(items) == 5
    for item in items:
        assert item["status"] == "active"


@pytest.mark.integration
def test_get_keys_lists_all_with_status(client: TestClient) -> None:
    """POST 2, revoke 1; GET returns 2 items with statuses [active, revoked]."""
    _register(client, "frank@example.com")
    first = client.post("/api/keys", json={"name": "stay"}).json()
    second = client.post("/api/keys", json={"name": "die"}).json()
    revoke = client.delete(f"/api/keys/{second['id']}")
    assert revoke.status_code == 204
    items = client.get("/api/keys").json()
    assert len(items) == 2
    statuses_by_id = {item["id"]: item["status"] for item in items}
    assert statuses_by_id[first["id"]] == "active"
    assert statuses_by_id[second["id"]] == "revoked"


@pytest.mark.integration
def test_get_keys_no_plaintext_in_list(client: TestClient) -> None:
    """GET /api/keys items lack `key` field entirely (Pydantic serialization)."""
    _register(client, "gina@example.com")
    client.post("/api/keys", json={"name": "shown-once"})
    items = client.get("/api/keys").json()
    assert len(items) == 1
    assert "key" not in items[0]


@pytest.mark.integration
def test_delete_key_soft_deletes(client: TestClient) -> None:
    """DELETE soft-deletes; GET still returns the row with status=revoked."""
    _register(client, "harry@example.com")
    created = client.post("/api/keys", json={"name": "deletable"}).json()
    response = client.delete(f"/api/keys/{created['id']}")
    assert response.status_code == 204
    items = client.get("/api/keys").json()
    assert len(items) == 1  # row persists for audit
    assert items[0]["id"] == created["id"]
    assert items[0]["status"] == "revoked"


@pytest.mark.integration
def test_delete_key_cross_user_returns_404(
    keys_app: tuple[FastAPI, Container],
) -> None:
    """User B attempting to DELETE User A's key gets opaque 404 (T-13-15)."""
    app, _container = keys_app
    # User A registers + creates key — keep cookie jar separate
    client_a = TestClient(app)
    _register(client_a, "alice@a.com")
    a_key = client_a.post("/api/keys", json={"name": "a-key"}).json()
    assert a_key["status"] == "active"
    # User B registers separately (fresh client = fresh cookie jar)
    client_b = TestClient(app)
    _register(client_b, "bob@b.com")
    # User B tries to DELETE User A's key
    response = client_b.delete(f"/api/keys/{a_key['id']}")
    assert response.status_code == 404
    body = response.json()
    assert body["detail"] == "Key not found"
    # Confirm User A's key is still ACTIVE (not revoked by the cross-user attempt)
    a_items = client_a.get("/api/keys").json()
    assert len(a_items) == 1
    assert a_items[0]["status"] == "active"


@pytest.mark.integration
def test_delete_unknown_key_returns_404(client: TestClient) -> None:
    """DELETE on a non-existent id returns the same opaque 404 as cross-user."""
    _register(client, "ivy@example.com")
    response = client.delete("/api/keys/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Key not found"


@pytest.mark.integration
def test_create_key_requires_auth(keys_app: tuple[FastAPI, Container]) -> None:
    """POST /api/keys without cookie/bearer returns 401."""
    app, _ = keys_app
    client_no_auth = TestClient(app)
    response = client_no_auth.post("/api/keys", json={"name": "anon"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.integration
def test_bearer_auth_can_create_key(
    keys_app: tuple[FastAPI, Container],
) -> None:
    """Authorization: Bearer whsk_<plaintext> creates a new key for that user."""
    app, _ = keys_app
    # Register + obtain plaintext key via cookie-auth path
    cookie_client = TestClient(app)
    _register(cookie_client, "kev@example.com")
    first = cookie_client.post("/api/keys", json={"name": "bearer-source"}).json()
    plaintext = first["key"]
    # Now use bearer auth (no cookies) to create a 2nd key
    bearer_client = TestClient(app)
    response = bearer_client.post(
        "/api/keys",
        json={"name": "second-via-bearer"},
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert response.status_code == 201, response.text
    second = response.json()
    assert second["name"] == "second-via-bearer"
    # Verify both keys belong to the same user (list under cookie auth)
    items = cookie_client.get("/api/keys").json()
    assert len(items) == 2
