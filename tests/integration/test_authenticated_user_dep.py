"""Phase 19 Plan 04 — authenticated_user / authenticated_user_optional Depends.

12 cases verifying the new per-route auth dep replaces DualAuthMiddleware
semantics 1:1:

    1. No auth                              -> 401 + WWW-Authenticate header
    2. Valid bearer                          -> 200 + user_id
    3. Valid cookie                          -> 200 + user_id
    4. Bearer + cookie both valid            -> bearer wins (different users)
    5. Bearer malformed (cookie also valid)  -> 401, does NOT fall through
    6. Cookie tampered                       -> 401
    7. Cookie expired                        -> 401
    8. Cookie token_version stale            -> 401
    9. Sliding refresh: response stamps
       a fresh Set-Cookie: session=...       -> session cookie + httponly + path=/
    10. /optional with no auth               -> 200 + "anonymous"
    11. /optional with valid cookie          -> 200 + user_id
    12. Stale cookie on protected path       -> 401, no cookie clearing

Tiger-style:
- per-test slim FastAPI app (auth_router for cookie acquisition + protected/
  optional helper routes); two TestClients only when cross-user isolation
  required.
- assertions at boundaries (cookie present pre-call, status post-call).
- flat early-return helpers; no nested-if.
"""

from __future__ import annotations

import re
from collections.abc import Generator
from pathlib import Path

import pytest
from dependency_injector import providers
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.api import dependencies as deps_module
from app.api.auth_routes import auth_router
from app.api.key_routes import key_router
from app.api.exception_handlers import (
    invalid_credentials_handler,
    validation_error_handler,
)
from app.core.config import get_settings
from app.core.container import Container
from app.core.csrf_middleware import CsrfMiddleware
from app.core.dual_auth import DualAuthMiddleware
from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.core.rate_limiter import limiter, rate_limit_handler
from app.domain.entities.user import User
from app.infrastructure.database.models import Base

from tests.integration._phase16_helpers import (
    JWT_HS256,
    _forge_jwt,
    _register,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str:
    """File-backed SQLite URL with all tables pre-created."""
    db_file = tmp_path / "auth_dep_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    return url


@pytest.fixture
def session_factory(tmp_db_url: str):
    """Per-test sessionmaker bound to the tmp SQLite file."""
    engine = create_engine(tmp_db_url, connect_args={"check_same_thread": False})
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _build_protected_router() -> APIRouter:
    """Slim router that exercises the new deps under test.

    /protected exercises authenticated_user (raises 401 on miss).
    /optional  exercises authenticated_user_optional (returns None on miss).
    """
    router = APIRouter()

    @router.get("/protected")
    def _protected(
        user: User = Depends(deps_module.authenticated_user),
    ) -> dict:
        return {"user_id": int(user.id) if user.id is not None else None}

    @router.get("/optional")
    def _optional(
        user: User | None = Depends(deps_module.authenticated_user_optional),
    ) -> dict:
        if user is None:
            return {"user_id": "anonymous"}
        return {"user_id": int(user.id) if user.id is not None else None}

    return router


@pytest.fixture
def app_and_factory(
    tmp_db_url: str,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[FastAPI, sessionmaker], None, None]:
    """FastAPI app: auth_router + key_router + protected/optional routes.

    DualAuthMiddleware + CsrfMiddleware are mounted because /auth/register
    and POST /api/keys (used to seat cookies/bearers) require them. The
    middleware lets unauthenticated requests through on PUBLIC_ALLOWLIST
    paths; we extend the allowlist with /protected and /optional so the
    new authenticated_user dep runs end-to-end without the legacy
    middleware short-circuiting tests 1, 5, 6, 7, 8, 9, 10, 12.

    Coexistence target (Plan 04): the new dep must work even WHILE
    DualAuthMiddleware is still installed (Plan 11 deletes it).
    """
    from app.core import dual_auth as dual_auth_mod

    container = Container()
    container.db_session_factory.override(providers.Factory(session_factory))
    deps_module.set_container(container)

    limiter.reset()

    # Add the test routes to the public allowlist so DualAuthMiddleware lets
    # unauthenticated calls fall through to the dep instead of 401-ing at
    # the middleware layer. Real prod routes that adopt the new dep will
    # also be removed from PUBLIC_ALLOWLIST checks in Plan 11; until then
    # this monkeypatch isolates the dep under test.
    extended_allowlist = dual_auth_mod.PUBLIC_ALLOWLIST + ("/protected", "/optional")
    monkeypatch.setattr(dual_auth_mod, "PUBLIC_ALLOWLIST", extended_allowlist)

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(InvalidCredentialsError, invalid_credentials_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.include_router(auth_router)
    app.include_router(key_router)
    app.include_router(_build_protected_router())
    # ASGI reversal: register Csrf FIRST so it dispatches AFTER DualAuth
    # (DualAuth populates request.state.auth_method which Csrf reads).
    # Required so /api/keys CSRF check passes when seating bearer keys via
    # cookie+csrf in helper functions.
    app.add_middleware(CsrfMiddleware, container=container)
    app.add_middleware(DualAuthMiddleware, container=container)

    def _override_get_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps_module.get_db] = _override_get_db

    yield app, session_factory

    app.dependency_overrides.clear()
    container.unwire()
    container.db_session_factory.reset_override()
    limiter.reset()


@pytest.fixture
def client(
    app_and_factory: tuple[FastAPI, sessionmaker],
) -> TestClient:
    app, _ = app_and_factory
    return TestClient(app)


@pytest.fixture
def jwt_secret() -> str:
    return get_settings().auth.JWT_SECRET.get_secret_value()


# ---------------------------------------------------------------------------
# Helpers — flat early-returns only.
# ---------------------------------------------------------------------------


def _seat_cookie_session(client_to_seat: TestClient, email: str) -> int:
    """Register a user (cookie auth) and return user_id; cookies sit on jar."""
    user_id = _register(client_to_seat, email)
    assert client_to_seat.cookies.get("session") is not None
    return user_id


def _issue_bearer(
    client_to_seat: TestClient, email: str
) -> tuple[int, str]:
    """Register, create an API key, return (user_id, bearer_plaintext).

    Flat: register → list+create key via /api/keys → return plaintext. We use
    the existing key_router which is auth-cookie protected.
    """
    user_id = _seat_cookie_session(client_to_seat, email)
    csrf = client_to_seat.cookies.get("csrf_token")
    assert csrf is not None
    response = client_to_seat.post(
        "/api/keys",
        json={"name": "test-bearer"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.text
    plaintext = response.json()["key"]
    assert plaintext.startswith("whsk_"), plaintext
    return user_id, plaintext


def _bump_token_version(session_factory: sessionmaker, user_id: int) -> None:
    """Bump users.token_version directly in the DB (simulates logout-all)."""
    with session_factory() as session:
        session.execute(
            text("UPDATE users SET token_version = token_version + 1 "
                 "WHERE id = :uid"),
            {"uid": user_id},
        )
        session.commit()


# ---------------------------------------------------------------------------
# 12 cases.
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAuthenticatedUserDep:
    # 1
    def test_no_auth_returns_401_with_www_authenticate_header(
        self, client: TestClient
    ) -> None:
        response = client.get("/protected")
        assert response.status_code == 401, response.text
        assert response.json() == {"detail": "Authentication required"}
        assert response.headers["WWW-Authenticate"] == 'Bearer realm="whisperx"'

    # 2
    def test_valid_bearer_returns_user_id(
        self, app_and_factory: tuple[FastAPI, sessionmaker]
    ) -> None:
        app, _ = app_and_factory
        seater = TestClient(app)
        user_id, plaintext = _issue_bearer(seater, "bearer-only@example.com")
        # Drop the cookie jar so this is bearer-only.
        bearer_client = TestClient(app)
        response = bearer_client.get(
            "/protected", headers={"Authorization": f"Bearer {plaintext}"}
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"user_id": user_id}

    # 3
    def test_valid_cookie_returns_user_id(
        self, client: TestClient
    ) -> None:
        user_id = _seat_cookie_session(client, "cookie-only@example.com")
        response = client.get("/protected")
        assert response.status_code == 200, response.text
        assert response.json() == {"user_id": user_id}

    # 4
    def test_bearer_wins_over_cookie_when_both_present(
        self, app_and_factory: tuple[FastAPI, sessionmaker]
    ) -> None:
        app, _ = app_and_factory
        # User A: cookie auth
        cookie_client = TestClient(app)
        user_a_id = _seat_cookie_session(cookie_client, "user-a@example.com")
        # User B: bearer
        bearer_seater = TestClient(app)
        user_b_id, plaintext_b = _issue_bearer(bearer_seater, "user-b@example.com")
        assert user_a_id != user_b_id

        # Use cookie_client (jar holds A's session) and add B's bearer header.
        response = cookie_client.get(
            "/protected", headers={"Authorization": f"Bearer {plaintext_b}"}
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"user_id": user_b_id}, (
            "bearer must win when both are presented"
        )

    # 5
    def test_malformed_bearer_does_not_fall_through_to_cookie(
        self, client: TestClient
    ) -> None:
        # Seat a valid cookie first.
        _seat_cookie_session(client, "fallthrough@example.com")
        # Send a garbage bearer with the cookie still present in the jar.
        response = client.get(
            "/protected", headers={"Authorization": "Bearer not-a-real-key"}
        )
        # Bearer wins resolution; failure must be terminal (401), NOT a
        # silent fallback to the cookie.
        assert response.status_code == 401, response.text

    # 6
    def test_tampered_cookie_returns_401(
        self, app_and_factory: tuple[FastAPI, sessionmaker]
    ) -> None:
        app, _ = app_and_factory
        seater = TestClient(app)
        _seat_cookie_session(seater, "tamper@example.com")
        token = seater.cookies.get("session")
        assert token is not None
        # Flip a single character in the JWT signature segment.
        head, body, sig = token.split(".")
        tampered_sig = sig[:-1] + ("A" if sig[-1] != "A" else "B")
        tampered = f"{head}.{body}.{tampered_sig}"

        fresh = TestClient(app)
        fresh.cookies.set("session", tampered)
        response = fresh.get("/protected")
        assert response.status_code == 401, response.text

    # 7
    def test_expired_cookie_returns_401(
        self, app_and_factory: tuple[FastAPI, sessionmaker], jwt_secret: str
    ) -> None:
        app, _ = app_and_factory
        seater = TestClient(app)
        user_id = _seat_cookie_session(seater, "expired@example.com")

        forged = _forge_jwt(
            alg=JWT_HS256,
            user_id=user_id,
            token_version=0,
            secret=jwt_secret,
            expired=True,
        )
        fresh = TestClient(app)
        fresh.cookies.set("session", forged)
        response = fresh.get("/protected")
        assert response.status_code == 401, response.text

    # 8
    def test_stale_token_version_cookie_returns_401(
        self,
        app_and_factory: tuple[FastAPI, sessionmaker],
        jwt_secret: str,
    ) -> None:
        app, factory = app_and_factory
        seater = TestClient(app)
        user_id = _seat_cookie_session(seater, "ver-bump@example.com")

        # Forge a JWT for ver=0; then bump server-side to ver=1.
        forged_v0 = _forge_jwt(
            alg=JWT_HS256,
            user_id=user_id,
            token_version=0,
            secret=jwt_secret,
        )
        _bump_token_version(factory, user_id)

        fresh = TestClient(app)
        fresh.cookies.set("session", forged_v0)
        response = fresh.get("/protected")
        assert response.status_code == 401, response.text

    # 9
    def test_sliding_refresh_stamps_fresh_session_cookie(
        self, client: TestClient
    ) -> None:
        _seat_cookie_session(client, "sliding@example.com")
        original_cookie = client.cookies.get("session")
        assert original_cookie is not None

        response = client.get("/protected")
        assert response.status_code == 200, response.text

        # Set-Cookie must be present in the response (sliding refresh).
        set_cookie_headers = response.headers.get_list("set-cookie")
        session_set_cookie = next(
            (h for h in set_cookie_headers if h.startswith("session=")), None
        )
        assert session_set_cookie is not None, (
            f"sliding-refresh missing; set-cookie headers={set_cookie_headers}"
        )
        # Locked cookie attrs (mirrors dual_auth.py:310-321 byte-for-byte).
        assert "HttpOnly" in session_set_cookie, session_set_cookie
        assert "Path=/" in session_set_cookie, session_set_cookie
        assert re.search(r"SameSite=lax", session_set_cookie, re.IGNORECASE), (
            session_set_cookie
        )

    # 10
    def test_optional_anonymous_returns_anonymous(
        self, client: TestClient
    ) -> None:
        response = client.get("/optional")
        assert response.status_code == 200, response.text
        assert response.json() == {"user_id": "anonymous"}

    # 11
    def test_optional_authed_returns_user_id(
        self, client: TestClient
    ) -> None:
        user_id = _seat_cookie_session(client, "optional-authed@example.com")
        response = client.get("/optional")
        assert response.status_code == 200, response.text
        assert response.json() == {"user_id": user_id}

    # 12
    def test_stale_cookie_on_protected_path_returns_401_without_clearing_cookies(
        self, app_and_factory: tuple[FastAPI, sessionmaker]
    ) -> None:
        """A bad cookie on a protected route must NOT silently clear cookies.

        Cookie clearing is a route-level concern (e.g. /auth/logout); the
        auth dep only authenticates or rejects. This test guards against a
        future regression where a 401 leg also strips Set-Cookie.
        """
        app, _ = app_and_factory
        # Plant an obviously bad cookie.
        fresh = TestClient(app)
        fresh.cookies.set("session", "not-a-real-jwt")
        response = fresh.get("/protected")
        assert response.status_code == 401, response.text

        # Response must NOT contain a Set-Cookie that deletes session.
        set_cookie_headers = response.headers.get_list("set-cookie")
        deleting = [
            h for h in set_cookie_headers
            if h.startswith("session=") and ("Max-Age=0" in h or 'session=""' in h)
        ]
        assert deleting == [], (
            f"401 leg must not clear cookies; got {deleting}"
        )
