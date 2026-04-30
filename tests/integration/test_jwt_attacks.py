"""VERIFY-02/03/04 JWT attack tests — 3 forgeries × 2 transports = 6 cases.

Each forged token must produce 401 from DualAuthMiddleware regardless of
transport (Authorization: Bearer header OR `session` cookie).

Coverage:
    VERIFY-02 — alg=none token (Bearer + cookie)            → 401
    VERIFY-03 — tampered HS256 signature (Bearer + cookie)  → 401
    VERIFY-04 — expired HS256 token (Bearer + cookie)       → 401

Single-decode-site invariant: every rejection collapses through
``app.core.jwt_codec.decode_session`` and surfaces as the generic
``"Authentication required"`` 401 (T-13-05 anti-leak).

The forge target is ``POST /auth/logout-all`` — auth-protected,
state-mutating, exists in v1.2 (Plan 15-02). 401 means rejection
BEFORE the handler runs (no token_version mutation possible).
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
from app.core.container import Container
from app.core.csrf_middleware import CsrfMiddleware
from app.core.dual_auth import DualAuthMiddleware
from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import Base

from tests.integration._phase16_helpers import (
    JWT_ALG_NONE,
    JWT_HS256,
    _forge_jwt,
    _register,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str:
    """File-backed SQLite URL with auth tables pre-created."""
    db_file = tmp_path / "jwt_attacks.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    return url


@pytest.fixture
def session_factory(tmp_db_url: str):
    """Sessionmaker bound to the per-test SQLite file."""
    engine = create_engine(tmp_db_url, connect_args={"check_same_thread": False})
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def auth_full_app(
    tmp_db_url: str, session_factory
) -> Generator[tuple[FastAPI, Container], None, None]:
    """FastAPI app with auth_router + CsrfMiddleware + DualAuthMiddleware.

    Middleware registration order is CRITICAL (Pitfall 3 — RESEARCH.md):
    Starlette dispatches in REVERSE registration order. We need
    DualAuthMiddleware to run FIRST (sets request.state.auth_method),
    then CsrfMiddleware (reads it), so Csrf is registered FIRST.

    Limiter reset in BOTH setup and teardown (Pitfall 1) so register
    bucket (3/hr/IP/24) does not poison adjacent tests.
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
    # ASGI reversal: register CsrfMiddleware FIRST so it runs SECOND on dispatch.
    app.add_middleware(CsrfMiddleware, container=container)
    app.add_middleware(DualAuthMiddleware, container=container)

    yield app, container

    container.unwire()
    container.db_session_factory.reset_override()
    limiter.reset()


# ---------------------------------------------------------------------------
# Helpers — flat early-returns only, no nested-if.
# ---------------------------------------------------------------------------


def _jwt_secret(container: Container) -> str:
    """Unwrap the HS256 signing secret from the resolved Settings instance.

    Plan 11-04 lesson: Settings.auth.JWT_SECRET is a Pydantic v2 SecretStr;
    tests need the plaintext to forge real signatures. The container
    exposes settings via the ``config`` provider (not ``settings``).
    """
    raw = container.config().auth.JWT_SECRET
    if hasattr(raw, "get_secret_value"):
        return raw.get_secret_value()
    return str(raw)


def _register_user(
    client: TestClient, email: str = "attacker@phase16.example.com"
) -> int:
    """Register a fresh user via /auth/register; return user_id.

    Wraps ``_register`` from _phase16_helpers so attack-test bodies stay
    a single line (DRT). Cookies land in the client jar — callers MUST
    ``client.cookies.clear()`` before attaching forged tokens (Pitfall 2).
    """
    return _register(client, email)


def _send_with(client: TestClient, transport: str, token: str):
    """Dispatch ``POST /auth/logout-all`` with ``token`` over ``transport``.

    Two flat early-return guards keep nested-if at zero. Forged tokens
    travel either as ``Authorization: Bearer ...`` OR via the ``session``
    cookie — both paths must collapse to 401 in DualAuthMiddleware.
    """
    if transport == "bearer":
        return client.post(
            "/auth/logout-all",
            headers={"Authorization": f"Bearer {token}"},
        )
    if transport == "cookie":
        client.cookies.set("session", token)
        return client.post("/auth/logout-all")
    raise ValueError(f"unknown transport: {transport}")


# ---------------------------------------------------------------------------
# Tests — 3 forgeries × 2 transports = 6 cases.
# Every test clears cookies before attaching the forged token (Pitfall 2)
# so the only credential reaching the middleware is the forgery under test.
# ---------------------------------------------------------------------------


_TRANSPORTS = [
    pytest.param("bearer", id="bearer"),
    pytest.param("cookie", id="cookie"),
]


@pytest.mark.parametrize("transport", _TRANSPORTS)
@pytest.mark.integration
def test_alg_none_jwt_returns_401(
    transport: str, auth_full_app: tuple[FastAPI, Container]
) -> None:
    """VERIFY-02 — alg=none token rejected on every transport.

    PyJWT decodes with ``algorithms=["HS256"]`` so an alg=none header
    surfaces ``InvalidAlgorithmError`` → ``JwtAlgorithmError`` → 401.
    """
    app, _ = auth_full_app
    client = TestClient(app)
    user_id = _register_user(client, f"alg-none-{transport}@phase16.example.com")
    forged_token = _forge_jwt(alg=JWT_ALG_NONE, user_id=user_id)

    client.cookies.clear()
    response = _send_with(client, transport, forged_token)

    assert response.status_code == 401, response.text


@pytest.mark.parametrize("transport", _TRANSPORTS)
@pytest.mark.integration
def test_tampered_jwt_returns_401(
    transport: str, auth_full_app: tuple[FastAPI, Container]
) -> None:
    """VERIFY-03 — HS256 token with flipped last sig char rejected.

    HMAC verify fails → ``InvalidSignatureError`` → ``JwtTamperedError``
    → 401. Real signing key is required so the forgery exercises the
    signature-verification code path (not the algorithm allow-list).
    """
    app, container = auth_full_app
    client = TestClient(app)
    user_id = _register_user(client, f"tampered-{transport}@phase16.example.com")
    forged_token = _forge_jwt(alg=JWT_HS256, user_id=user_id, secret=_jwt_secret(container), tamper=True)

    client.cookies.clear()
    response = _send_with(client, transport, forged_token)

    assert response.status_code == 401, response.text


@pytest.mark.parametrize("transport", _TRANSPORTS)
@pytest.mark.integration
def test_expired_jwt_returns_401(
    transport: str, auth_full_app: tuple[FastAPI, Container]
) -> None:
    """VERIFY-04 — HS256 token with exp in the past rejected.

    Real signing key + iat/exp shifted to the past so PyJWT raises
    ``ExpiredSignatureError`` → ``JwtExpiredError`` → 401.
    """
    app, container = auth_full_app
    client = TestClient(app)
    user_id = _register_user(client, f"expired-{transport}@phase16.example.com")
    forged_token = _forge_jwt(alg=JWT_HS256, user_id=user_id, secret=_jwt_secret(container), expired=True)

    client.cookies.clear()
    response = _send_with(client, transport, forged_token)

    assert response.status_code == 401, response.text
