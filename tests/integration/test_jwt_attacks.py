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
from app.core.config import get_settings
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
) -> Generator[FastAPI, None, None]:
    """Slim FastAPI app: auth_router driven via dep overrides.

    Phase 19 Plan 10: dependency_overrides[get_db] is the SOLE DB-binding
    seam. The new Depends(authenticated_user) on /auth/logout-all rejects
    forged tokens via the token_service / SQLAlchemyUserRepository chain
    against the tmp DB — same 401 outcome as the legacy DualAuthMiddleware
    path, no middleware mounting required. The Phase-16-04 ASGI ordering
    invariant (CsrfMiddleware-first DualAuth-last) is OBSOLETE: order is
    determined by Depends resolution.

    Limiter reset in BOTH setup and teardown (Pitfall 1) so the register
    bucket (3/hr/IP/24) does not poison adjacent tests.
    """
    limiter.reset()

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(InvalidCredentialsError, invalid_credentials_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.include_router(auth_router)

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


# ---------------------------------------------------------------------------
# Helpers — flat early-returns only, no nested-if.
# ---------------------------------------------------------------------------


def _jwt_secret() -> str:
    """Unwrap the HS256 signing secret from the resolved Settings instance.

    Phase 19 Plan 10: tokens are now signed via the @lru_cache singleton
    in app.core.services.get_token_service which reads JWT_SECRET from
    Settings.auth — the same single source of truth used by every signing
    path in the codebase. Tests forge tokens with this secret to match.
    """
    raw = get_settings().auth.JWT_SECRET
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
    transport: str, auth_full_app: FastAPI
) -> None:
    """VERIFY-02 — alg=none token rejected on every transport.

    PyJWT decodes with ``algorithms=["HS256"]`` so an alg=none header
    surfaces ``InvalidAlgorithmError`` → ``JwtAlgorithmError`` → 401.
    """
    app = auth_full_app
    client = TestClient(app)
    user_id = _register_user(client, f"alg-none-{transport}@phase16.example.com")
    forged_token = _forge_jwt(alg=JWT_ALG_NONE, user_id=user_id)

    client.cookies.clear()
    response = _send_with(client, transport, forged_token)

    assert response.status_code == 401, response.text
    assert response.json()["detail"] == "Authentication required", (
        f"T-13-05 anti-leak body mismatch: {response.text}"
    )


@pytest.mark.parametrize("transport", _TRANSPORTS)
@pytest.mark.integration
def test_tampered_jwt_returns_401(
    transport: str, auth_full_app: FastAPI
) -> None:
    """VERIFY-03 — HS256 token with flipped last sig char rejected.

    HMAC verify fails → ``InvalidSignatureError`` → ``JwtTamperedError``
    → 401. Real signing key is required so the forgery exercises the
    signature-verification code path (not the algorithm allow-list).
    """
    app = auth_full_app
    client = TestClient(app)
    user_id = _register_user(client, f"tampered-{transport}@phase16.example.com")
    forged_token = _forge_jwt(alg=JWT_HS256, user_id=user_id, secret=_jwt_secret(), tamper=True)

    client.cookies.clear()
    response = _send_with(client, transport, forged_token)

    assert response.status_code == 401, response.text
    assert response.json()["detail"] == "Authentication required", (
        f"T-13-05 anti-leak body mismatch: {response.text}"
    )


@pytest.mark.parametrize("transport", _TRANSPORTS)
@pytest.mark.integration
def test_expired_jwt_returns_401(
    transport: str, auth_full_app: FastAPI
) -> None:
    """VERIFY-04 — HS256 token with exp in the past rejected.

    Real signing key + iat/exp shifted to the past so PyJWT raises
    ``ExpiredSignatureError`` → ``JwtExpiredError`` → 401.
    """
    app = auth_full_app
    client = TestClient(app)
    user_id = _register_user(client, f"expired-{transport}@phase16.example.com")
    forged_token = _forge_jwt(alg=JWT_HS256, user_id=user_id, secret=_jwt_secret(), expired=True)

    client.cookies.clear()
    response = _send_with(client, transport, forged_token)

    assert response.status_code == 401, response.text
    assert response.json()["detail"] == "Authentication required", (
        f"T-13-05 anti-leak body mismatch: {response.text}"
    )
