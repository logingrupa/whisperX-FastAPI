"""tests/integration/test_set_cookie_attrs.py — Phase 19 REFACTOR-07 backend lock (T-19-04).

Locks the Set-Cookie attribute byte-shape on POST /auth/login at Wave 2.

Without this gate, REFACTOR-07 would only fire at Plan 15 Playwright wire
diff — making cookie-attr drift between waves expensive to detect. Run on
every commit from Plan 04 onwards.

Locked attrs (dev defaults — settings.auth.{JWT_TTL_DAYS=7, COOKIE_SECURE=False,
COOKIE_DOMAIN=""}):
    Max-Age=604800   (7 * 86400)
    HttpOnly
    SameSite=lax
    Path=/
    Secure   ABSENT  (COOKIE_SECURE=false in dev/test env)
"""

from __future__ import annotations

import re
from collections.abc import Generator
from pathlib import Path

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import dependencies as deps_module
from app.api.auth_routes import auth_router
from app.api.exception_handlers import (
    invalid_credentials_handler,
    validation_error_handler,
)
from app.core.container import Container
from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import Base


@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str:
    db_file = tmp_path / "set_cookie_attrs.db"
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
def client(session_factory) -> Generator[TestClient, None, None]:
    """Slim FastAPI app with auth_router only — no auth middleware needed.

    /auth/register and /auth/login set cookies via _set_auth_cookies inside
    auth_routes.py; the wire shape is independent of any middleware stack.
    """
    container = Container()
    container.db_session_factory.override(providers.Factory(session_factory))
    deps_module.set_container(container)
    limiter.reset()

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(InvalidCredentialsError, invalid_credentials_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.include_router(auth_router)

    yield TestClient(app)

    container.unwire()
    container.db_session_factory.reset_override()
    limiter.reset()


@pytest.mark.integration
def test_login_set_cookie_attrs_locked(client: TestClient) -> None:
    """REFACTOR-07 backend gate: Set-Cookie attrs byte-identical to pre-refactor."""
    register = client.post(
        "/auth/register",
        json={"email": "cookie@example.com", "password": "TestPassword!23"},
    )
    assert register.status_code == 201, register.text

    response = client.post(
        "/auth/login",
        json={"email": "cookie@example.com", "password": "TestPassword!23"},
    )
    assert response.status_code == 200, response.text

    set_cookie_headers = response.headers.get_list("set-cookie")
    session_cookie = next(
        (h for h in set_cookie_headers if h.startswith("session=")), None
    )
    assert session_cookie is not None, (
        f"no session Set-Cookie header in {set_cookie_headers}"
    )

    # Locked attrs (dev defaults).
    assert "Max-Age=604800" in session_cookie, f"max_age drift: {session_cookie}"
    assert "HttpOnly" in session_cookie, f"httponly missing: {session_cookie}"
    assert re.search(r"SameSite=lax", session_cookie, re.IGNORECASE), (
        f"samesite drift: {session_cookie}"
    )
    assert "Path=/" in session_cookie, f"path drift: {session_cookie}"
    # Dev: Secure flag absent (COOKIE_SECURE=false in test env).
    assert "Secure" not in session_cookie, (
        f"unexpected Secure flag in dev: {session_cookie}"
    )
