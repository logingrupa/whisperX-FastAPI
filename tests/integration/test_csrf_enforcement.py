"""VERIFY-06 CSRF double-submit. 4 cases: missing/mismatched/matching X-CSRF-Token + bearer-auth bypass.

Cookie-auth state-mutating POST without X-CSRF-Token header -> 403 "CSRF token missing".
Cookie-auth state-mutating POST with mismatched X-CSRF-Token -> 403 "CSRF token mismatch".
Cookie-auth state-mutating POST with matching X-CSRF-Token -> 204.
Bearer-auth state-mutating POST with NO X-CSRF-Token header -> 204 (CsrfMiddleware skips,
MID-04 invariant — auth_method='bearer' bypasses CSRF check).

Builds a slim FastAPI app per test (NOT app/main.py): mounts auth_router + key_router
with both DualAuthMiddleware (resolves session/bearer first) and CsrfMiddleware
(enforces double-submit second). ASGI registration is REVERSED so dispatch order is
DualAuth -> Csrf -> route.

Code-quality invariants (verifier-checked):
    DRY  — _csrf_target_endpoint() is the single source for the path under test.
    SRP  — each test asserts ONE thing (status code + optional body detail).
    Tiger-style — assert response body string equality on 403 cases (not just status).
    No nested-if — flat early-return guards only.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import dependencies
from app.api.auth_routes import auth_router
from app.api.exception_handlers import (
    invalid_credentials_handler,
    validation_error_handler,
)
from app.api.key_routes import key_router
from app.core.container import Container
from app.core.csrf_middleware import CsrfMiddleware
from app.core.dual_auth import DualAuthMiddleware
from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import Base

from tests.integration._phase16_helpers import _issue_csrf_pair


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str:
    """Return a file-backed SQLite URL with auth+key tables pre-created."""
    db_file = tmp_path / "csrf_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    return url


@pytest.fixture
def session_factory(tmp_db_url: str):
    """Sessionmaker bound to the temp DB."""
    engine = create_engine(tmp_db_url, connect_args={"check_same_thread": False})
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def auth_full_app(
    tmp_db_url: str, session_factory
) -> Generator[tuple[FastAPI, Container], None, None]:
    """FastAPI app with auth_router + key_router + DualAuthMiddleware + CsrfMiddleware.

    Middleware ASGI registration order (CRITICAL):
        add_middleware(CsrfMiddleware)     → registered first → runs SECOND on dispatch
        add_middleware(DualAuthMiddleware) → registered last  → runs FIRST on dispatch
    Net dispatch order: request -> DualAuth (sets auth_method) -> Csrf (enforces) -> route.
    """
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
    app.add_middleware(CsrfMiddleware, container=container)
    app.add_middleware(DualAuthMiddleware, container=container)

    yield app, container

    container.unwire()
    container.db_session_factory.reset_override()
    limiter.reset()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _csrf_target_endpoint() -> str:
    """Single source for the state-mutating cookie-auth path under test.

    /auth/logout-all is idempotent, returns 204 on success, requires cookie auth,
    and lives on a router we already mount in auth_full_app — perfect CSRF surface.
    """
    return "/auth/logout-all"


def _issue_api_key(client: TestClient) -> str:
    """Cookie-auth POST /api/keys -> plaintext API key (shown once, KEY-04).

    Caller must have already seated session + csrf_token cookies via
    _issue_csrf_pair. We re-read csrf_token from the jar so the helper has zero
    parameter coupling to the registration step.
    """
    csrf_token = client.cookies.get("csrf_token")
    assert csrf_token is not None, "csrf_token cookie missing — call _issue_csrf_pair first"
    response = client.post(
        "/api/keys",
        json={"name": "csrf-bypass-test"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 201, response.text
    return response.json()["key"]


# ---------------------------------------------------------------------------
# VERIFY-06 — 4 cases
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_csrf_missing_header_returns_403(
    auth_full_app: tuple[FastAPI, Container],
) -> None:
    """Cookie-auth POST without X-CSRF-Token -> 403 'CSRF token missing'."""
    app, _ = auth_full_app
    client = TestClient(app)
    _issue_csrf_pair(client, "csrf-missing@phase16.example.com")
    # Cookies attached automatically; X-CSRF-Token deliberately absent.
    response = client.post(_csrf_target_endpoint())
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "CSRF token missing", response.text


@pytest.mark.integration
def test_csrf_mismatched_header_returns_403(
    auth_full_app: tuple[FastAPI, Container],
) -> None:
    """X-CSRF-Token != csrf_token cookie -> 403 'CSRF token mismatch'."""
    app, _ = auth_full_app
    client = TestClient(app)
    _issue_csrf_pair(client, "csrf-mismatch@phase16.example.com")
    response = client.post(
        _csrf_target_endpoint(),
        headers={"X-CSRF-Token": "deadbeef-not-the-real-cookie-value-12345"},
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "CSRF token mismatch", response.text


@pytest.mark.integration
def test_csrf_matching_header_succeeds(
    auth_full_app: tuple[FastAPI, Container],
) -> None:
    """Matching X-CSRF-Token -> request passes through (204)."""
    app, _ = auth_full_app
    client = TestClient(app)
    _, csrf_cookie_value = _issue_csrf_pair(
        client, "csrf-match@phase16.example.com"
    )
    response = client.post(
        _csrf_target_endpoint(),
        headers={"X-CSRF-Token": csrf_cookie_value},
    )
    assert response.status_code == 204, response.text


@pytest.mark.integration
def test_bearer_auth_bypasses_csrf(
    auth_full_app: tuple[FastAPI, Container],
) -> None:
    """Bearer-auth state-mutating POST WITHOUT X-CSRF-Token still succeeds (MID-04).

    DualAuthMiddleware sets request.state.auth_method='bearer' on the
    Authorization: Bearer leg; CsrfMiddleware then short-circuits its check
    (cookie + header double-submit only fires when auth_method=='cookie').
    """
    app, _ = auth_full_app
    client = TestClient(app)
    _issue_csrf_pair(client, "csrf-bearer-bypass@phase16.example.com")
    plaintext_key = _issue_api_key(client)  # cookie-auth path issues key

    # Drop ALL cookies so ONLY the bearer path is exercised — bearer wins on
    # mixed presentation (Phase 13-02), but unambiguous test signal demands
    # zero cookie noise.
    client.cookies.clear()
    response = client.post(
        _csrf_target_endpoint(),
        headers={"Authorization": f"Bearer {plaintext_key}"},
    )
    assert response.status_code == 204, response.text
