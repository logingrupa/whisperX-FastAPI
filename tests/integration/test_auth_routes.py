"""Integration tests for Phase 13 ``/auth/*`` routes.

Coverage (≥10 cases):

1.  register happy path — 201 + cookies set
2.  register duplicate email — 422 generic "Registration failed" (anti-enum)
3.  register disposable email — 422 generic "Registration failed" (anti-enum)
4.  register weak password — pydantic 422
5.  register rate-limited 3/hr — 4th request 429 with Retry-After
6.  login happy path — 200 + cookies set
7.  login wrong email — 401 InvalidCredentials shape
8.  login wrong password — 401 IDENTICAL shape (anti-enumeration)
9.  login rate-limited 10/hr — 11th request 429
10. logout clears cookies — 204 + Set-Cookie max-age=0
11. logout idempotent — 204 with no prior session
12. password reset hint exposed in OpenAPI description (AUTH-07)

Phase 15-02 additions (AUTH-06 — /auth/logout-all):

13. logout-all bumps users.token_version atomically (+1)
14. logout-all clears session + csrf_token cookies (Set-Cookie max-age=0)
15. logout-all invalidates the caller's existing JWT (token_version invariant)
16. logout-all without auth returns 401 "Authentication required"

Phase 19 Plan 10 fixture migration:
  - slim FastAPI app per test (auth_router only)
  - app.dependency_overrides[get_db] is the SOLE DB-binding seam — drives
    Depends(authenticated_user) + Depends(csrf_protected) on /auth/logout-all
    transitively against the tmp SQLite.
  - Single fixture ``auth_app`` covers BOTH anonymous public-allowlist routes
    (register/login/logout) AND the auth-gated /auth/logout-all path; the
    Phase-15-02 ``auth_full_app`` middleware-mounting variant collapses into
    the same shape because the new Depends graph runs the auth gate per-route
    (not via middleware).
  - DualAuthMiddleware mounting + the legacy DI container are GONE — Plans
    11-13 delete those modules; the fixture surface migrates ahead of the
    deletions so the atomic-commit invariant holds (collection succeeds at
    every commit).
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

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
from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import Base


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------


@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str:
    """Return a file-backed SQLite URL with auth tables pre-created."""
    db_file = tmp_path / "auth_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    return url


@pytest.fixture
def auth_app(tmp_db_url: str) -> Generator[FastAPI, None, None]:
    """Slim FastAPI test app: auth_router driven via dependency_overrides[get_db].

    Phase 19 Plan 10: ``app.dependency_overrides[get_db]`` is the SOLE
    DB-binding seam. The production Depends graph
    (``Depends(authenticated_user)`` for /auth/logout-all,
    ``Depends(get_auth_service_v2)`` for /auth/register + /auth/login)
    resolves transitively through the overridden ``get_db`` against the
    tmp SQLite. No middleware mounting — the new Depends chain owns auth
    end-to-end.
    """
    test_engine = create_engine(
        tmp_db_url, connect_args={"check_same_thread": False}
    )
    TestSession = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )

    # Reset slowapi bucket between tests so 3/hr + 10/hr counters are fresh.
    limiter.reset()

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(InvalidCredentialsError, invalid_credentials_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.include_router(auth_router)

    def _override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[dependencies.get_db] = _override_get_db

    yield app

    app.dependency_overrides.clear()
    test_engine.dispose()
    limiter.reset()


@pytest.fixture
def client(auth_app: FastAPI) -> TestClient:
    """TestClient wrapping the slim auth app."""
    return TestClient(auth_app)


@pytest.fixture
def auth_full_session_factory(tmp_db_url: str):
    """Sessionmaker for direct DB introspection in auth-required tests."""
    engine = create_engine(tmp_db_url, connect_args={"check_same_thread": False})
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def auth_full_app(
    tmp_db_url: str, auth_full_session_factory
) -> Generator[FastAPI, None, None]:
    """Slim FastAPI app: auth_router driven via dependency_overrides[get_db].

    Phase 19 Plan 10: collapses the legacy ``auth_full_app`` (which mounted
    DualAuthMiddleware) into the same shape as ``auth_app`` because the new
    Depends(authenticated_user) on /auth/logout-all gates auth per-route via
    the dep graph — no middleware needed. ``auth_full_session_factory`` is
    kept as a separate fixture so tests can introspect DB state directly
    (e.g. token_version row reads) without going through the dep override.
    """
    limiter.reset()

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(InvalidCredentialsError, invalid_credentials_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.include_router(auth_router)

    def _override_get_db():
        session = auth_full_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[dependencies.get_db] = _override_get_db

    yield app

    app.dependency_overrides.clear()
    limiter.reset()


@pytest.fixture
def auth_full_client(
    auth_full_app: FastAPI,
) -> TestClient:
    """TestClient wrapping the auth_full_app."""
    return TestClient(auth_full_app)


def _register(
    client: TestClient, email: str, password: str = "supersecret123"
) -> int:
    """Register a user via /auth/register; return the user_id (cookies seated).

    Phase 19 Plan 07 additive: /auth/logout-all carries route-level
    Depends(csrf_protected); plumb the csrf_token cookie value as a default
    X-CSRF-Token header so subsequent state-mutating calls pass the
    double-submit check; legacy test bodies stay untouched.
    """
    response = client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert response.status_code == 201, response.text
    csrf = client.cookies.get("csrf_token")
    assert csrf is not None, "csrf_token cookie missing after /auth/register"
    client.headers["X-CSRF-Token"] = csrf
    return int(response.json()["user_id"])


# ---------------------------------------------------------------
# Tests
# ---------------------------------------------------------------


@pytest.mark.integration
def test_register_happy_path(client: TestClient) -> None:
    """POST /auth/register with valid body returns 201 + sets both cookies."""
    response = client.post(
        "/auth/register",
        json={"email": "alice@example.com", "password": "supersecret123"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body["user_id"], int)
    assert body["plan_tier"] == "trial"
    # Cookies set in client jar — sliding-refresh / login leg
    assert "session" in response.cookies
    assert "csrf_token" in response.cookies
    assert response.cookies["session"]
    assert response.cookies["csrf_token"]


@pytest.mark.integration
def test_register_duplicate_email_generic_error(client: TestClient) -> None:
    """Second register with same email returns 422 generic — no enumeration."""
    payload = {"email": "bob@example.com", "password": "supersecret123"}
    first = client.post("/auth/register", json=payload)
    assert first.status_code == 201
    second = client.post("/auth/register", json=payload)
    assert second.status_code == 422
    body = second.json()
    # Anti-enumeration (T-13-09): generic message + code, NEVER the
    # internal "User with email already exists".
    assert body["error"]["message"] == "Registration failed"
    assert body["error"]["code"] == "REGISTRATION_FAILED"
    assert "already exists" not in body["error"]["message"].lower()


@pytest.mark.integration
def test_register_disposable_email_rejected(client: TestClient) -> None:
    """Disposable domain rejected with IDENTICAL body to duplicate-email."""
    response = client.post(
        "/auth/register",
        json={
            "email": "throwaway@10minutemail.com",
            "password": "supersecret123",
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["message"] == "Registration failed"
    assert body["error"]["code"] == "REGISTRATION_FAILED"


@pytest.mark.integration
def test_register_weak_password_rejected(client: TestClient) -> None:
    """Pydantic min_length=8 rejects short passwords with 422."""
    response = client.post(
        "/auth/register",
        json={"email": "carol@example.com", "password": "short"},
    )
    assert response.status_code == 422


@pytest.mark.integration
def test_register_rate_limit_3_per_hour(client: TestClient) -> None:
    """4th register from same IP within an hour returns 429 + Retry-After."""
    # 3 different emails — limiter keys on /24 not on email
    for index in range(3):
        response = client.post(
            "/auth/register",
            json={
                "email": f"user{index}@example.com",
                "password": "supersecret123",
            },
        )
        assert response.status_code == 201, response.text
    # 4th should be rate-limited
    fourth = client.post(
        "/auth/register",
        json={"email": "user4@example.com", "password": "supersecret123"},
    )
    assert fourth.status_code == 429
    assert "Retry-After" in fourth.headers
    assert int(fourth.headers["Retry-After"]) > 0


@pytest.mark.integration
def test_login_happy_path(client: TestClient) -> None:
    """Register then login returns 200 + sets both cookies."""
    payload = {"email": "dave@example.com", "password": "supersecret123"}
    register = client.post("/auth/register", json=payload)
    assert register.status_code == 201
    # Clear cookies so the login leg's Set-Cookie is observable
    client.cookies.clear()
    login = client.post("/auth/login", json=payload)
    assert login.status_code == 200, login.text
    body = login.json()
    assert isinstance(body["user_id"], int)
    assert body["plan_tier"] == "trial"
    assert "session" in login.cookies
    assert "csrf_token" in login.cookies


@pytest.mark.integration
def test_login_wrong_email_returns_401_generic(client: TestClient) -> None:
    """Login with unknown email returns 401 with InvalidCredentials shape."""
    response = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "supersecret123"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.integration
def test_login_wrong_password_returns_401_same_shape(client: TestClient) -> None:
    """Login with wrong password returns IDENTICAL shape to wrong-email leg.

    T-13-10: Anti-enumeration — same code + same user_message; only
    correlation_id differs (per-request UUID).
    """
    payload = {"email": "ed@example.com", "password": "supersecret123"}
    register = client.post("/auth/register", json=payload)
    assert register.status_code == 201
    client.cookies.clear()
    bad_pw = client.post(
        "/auth/login",
        json={"email": "ed@example.com", "password": "WRONG_PASSWORD!!!"},
    )
    assert bad_pw.status_code == 401
    body = bad_pw.json()
    assert body["error"]["code"] == "INVALID_CREDENTIALS"
    # Compare to wrong-email leg
    bad_email = client.post(
        "/auth/login",
        json={"email": "ghost@example.com", "password": "WRONG_PASSWORD!!!"},
    )
    assert bad_email.status_code == 401
    other = bad_email.json()
    assert other["error"]["code"] == body["error"]["code"]
    assert other["error"]["message"] == body["error"]["message"]


@pytest.mark.integration
def test_login_rate_limit_10_per_hour(client: TestClient) -> None:
    """11th login attempt from same IP within an hour returns 429."""
    payload = {"email": "fred@example.com", "password": "supersecret123"}
    register = client.post("/auth/register", json=payload)
    assert register.status_code == 201
    client.cookies.clear()
    # 10 successful logins (each consumes a slot)
    for _ in range(10):
        response = client.post("/auth/login", json=payload)
        assert response.status_code == 200, response.text
        client.cookies.clear()
    # 11th login is rate-limited
    eleventh = client.post("/auth/login", json=payload)
    assert eleventh.status_code == 429
    assert "Retry-After" in eleventh.headers


@pytest.mark.integration
def test_logout_clears_cookies(client: TestClient) -> None:
    """Logout returns 204; both session + csrf_token cookies cleared."""
    payload = {"email": "gina@example.com", "password": "supersecret123"}
    register = client.post("/auth/register", json=payload)
    assert register.status_code == 201
    response = client.post("/auth/logout")
    assert response.status_code == 204
    set_cookie_headers = response.headers.get_list("set-cookie")
    joined = "\n".join(set_cookie_headers).lower()
    # Both cookies should be cleared via Max-Age=0 (FastAPI delete_cookie)
    assert "session=" in joined
    assert "csrf_token=" in joined
    assert "max-age=0" in joined


@pytest.mark.integration
def test_logout_idempotent(client: TestClient) -> None:
    """Logout without prior session is a 204 no-op (idempotent)."""
    response = client.post("/auth/logout")
    assert response.status_code == 204


@pytest.mark.integration
def test_password_reset_hint_in_openapi(client: TestClient) -> None:
    """OpenAPI description for /auth/register exposes mailto link (AUTH-07)."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    register_op = spec["paths"]["/auth/register"]["post"]
    assert "hey@logingrupa.lv" in register_op["description"]
    login_op = spec["paths"]["/auth/login"]["post"]
    assert "hey@logingrupa.lv" in login_op["description"]


# ---------------------------------------------------------------
# Phase 15-02 — POST /auth/logout-all (AUTH-06)
# ---------------------------------------------------------------


@pytest.mark.integration
def test_logout_all_bumps_token_version(
    auth_full_client: TestClient, auth_full_session_factory
) -> None:
    """POST /auth/logout-all bumps users.token_version by exactly +1."""
    user_id = _register(auth_full_client, "logoutall-bump@example.com")
    with auth_full_session_factory() as session:
        version_before = session.execute(
            text("SELECT token_version FROM users WHERE id = :uid"),
            {"uid": user_id},
        ).scalar_one()

    response = auth_full_client.post("/auth/logout-all")

    assert response.status_code == 204, response.text
    with auth_full_session_factory() as session:
        version_after = session.execute(
            text("SELECT token_version FROM users WHERE id = :uid"),
            {"uid": user_id},
        ).scalar_one()
    assert version_after == version_before + 1


@pytest.mark.integration
def test_logout_all_clears_cookies(auth_full_client: TestClient) -> None:
    """POST /auth/logout-all returns 204 + clears session + csrf_token cookies."""
    _register(auth_full_client, "logoutall-cookies@example.com")

    response = auth_full_client.post("/auth/logout-all")

    assert response.status_code == 204
    set_cookie_headers = response.headers.get_list("set-cookie")
    joined = "\n".join(set_cookie_headers).lower()
    assert "session=" in joined
    assert "csrf_token=" in joined
    assert joined.count("max-age=0") == 2


@pytest.mark.integration
def test_logout_all_invalidates_existing_jwt(
    auth_full_client: TestClient,
) -> None:
    """JWT issued before logout-all 401s on next call (token_version invariant).

    The first logout-all clears the client-side cookie, so the next call would
    not even carry a session. To exercise the token_version invariant
    explicitly, snapshot the cookie BEFORE logout-all and re-attach it on the
    follow-up request — server-side token_version is already N+1 so the stale
    JWT (ver=N) must 401.
    """
    _register(auth_full_client, "logoutall-invalidate@example.com")
    old_session_cookie = auth_full_client.cookies.get("session")
    assert old_session_cookie is not None

    first_response = auth_full_client.post("/auth/logout-all")
    assert first_response.status_code == 204

    # Re-attach the now-stale cookie (server expects ver=N+1, JWT carries N).
    auth_full_client.cookies.set("session", old_session_cookie)
    retry = auth_full_client.post("/auth/logout-all")
    assert retry.status_code == 401


@pytest.mark.integration
def test_logout_all_requires_auth(
    auth_full_app: FastAPI,
) -> None:
    """Anonymous POST /auth/logout-all returns 401 'Authentication required'."""
    app = auth_full_app
    anon = TestClient(app)

    response = anon.post("/auth/logout-all")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
