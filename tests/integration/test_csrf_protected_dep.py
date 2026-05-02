"""Phase 19 Plan 05 — csrf_protected Depends factory.

5 cases verifying the new per-router CSRF dep mirrors CsrfMiddleware semantics
1:1 (mitigations T-19-05-01..04 from the plan threat register):

    1. POST cookie-auth, NO X-CSRF-Token header        -> 403 "CSRF token missing"
    2. POST cookie-auth, X-CSRF-Token != csrf cookie   -> 403 "CSRF token mismatch"
    3. GET  cookie-auth (method gate short-circuits)   -> 200 (no CSRF check)
    4. POST bearer-auth, NO X-CSRF-Token header        -> 200 (bearer skips CSRF)
    5. POST cookie-auth, X-CSRF-Token == csrf cookie   -> 200

Tiger-style:
- per-test slim FastAPI app (auth_router for cookie/key acquisition + a
  /test-csrf POST + /test-csrf-get GET probe both gated by csrf_protected).
- assertions at boundaries (cookies present pre-call, status post-call).
- flat early-return helpers; no nested-if.

Coexistence: DualAuthMiddleware + CsrfMiddleware are still mounted while the
new dep runs. The middleware's PUBLIC_ALLOWLIST is monkeypatched to include
the test endpoints so DualAuth lets unauthenticated calls fall through to
the new dep, AND CsrfMiddleware is mounted so /api/keys (used to seat a
bearer key) still passes its own CSRF check via the cookie-issued token.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from dependency_injector import providers
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api import dependencies as deps_module
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

from tests.integration._phase16_helpers import _register


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str:
    """File-backed SQLite URL with all tables pre-created."""
    db_file = tmp_path / "csrf_dep_test.db"
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


def _build_csrf_probe_router() -> APIRouter:
    """Slim router: POST + GET probes both gated by csrf_protected.

    POST /test-csrf      — exercises every csrf_protected branch.
    GET  /test-csrf-get  — exercises the method-gate short-circuit branch.
    """
    router = APIRouter()

    @router.post(
        "/test-csrf", dependencies=[Depends(deps_module.csrf_protected)]
    )
    def _post_probe() -> dict:
        return {"ok": True}

    @router.get(
        "/test-csrf-get", dependencies=[Depends(deps_module.csrf_protected)]
    )
    def _get_probe() -> dict:
        return {"ok": True}

    return router


@pytest.fixture
def app_and_factory(
    tmp_db_url: str,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[FastAPI, sessionmaker], None, None]:
    """FastAPI app: auth_router + key_router + /test-csrf + /test-csrf-get.

    DualAuthMiddleware + CsrfMiddleware coexist with the new dep (Plan 05
    explicitly states CsrfMiddleware is NOT deleted yet). PUBLIC_ALLOWLIST
    is extended with the test endpoints so DualAuth lets unauthenticated
    calls reach the dep instead of 401-ing at the middleware layer.
    """
    from app.core import dual_auth as dual_auth_mod

    container = Container()
    container.db_session_factory.override(providers.Factory(session_factory))
    deps_module.set_container(container)

    limiter.reset()

    extended_allowlist = dual_auth_mod.PUBLIC_ALLOWLIST + (
        "/test-csrf", "/test-csrf-get",
    )
    monkeypatch.setattr(dual_auth_mod, "PUBLIC_ALLOWLIST", extended_allowlist)

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(InvalidCredentialsError, invalid_credentials_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.include_router(auth_router)
    app.include_router(key_router)
    app.include_router(_build_csrf_probe_router())
    # ASGI reversal: register Csrf FIRST so it dispatches AFTER DualAuth.
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


# ---------------------------------------------------------------------------
# Helpers — flat early-returns only.
# ---------------------------------------------------------------------------


def _seat_cookie_with_csrf(client_to_seat: TestClient, email: str) -> str:
    """Register a user; return the csrf_token cookie value (DRT)."""
    _register(client_to_seat, email)
    csrf = client_to_seat.cookies.get("csrf_token")
    assert csrf is not None, "csrf_token cookie missing after register"
    assert client_to_seat.cookies.get("session") is not None, (
        "session cookie missing after register"
    )
    return csrf


def _issue_bearer(client_to_seat: TestClient, email: str) -> str:
    """Register + issue an API key via cookie-auth POST /api/keys.

    Returns the plaintext bearer key (whsk_*). Caller should drop the cookie
    jar before exercising the bearer-only path.
    """
    csrf = _seat_cookie_with_csrf(client_to_seat, email)
    response = client_to_seat.post(
        "/api/keys",
        json={"name": "csrf-bypass-test"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201, response.text
    plaintext = response.json()["key"]
    assert plaintext.startswith("whsk_"), plaintext
    return plaintext


# ---------------------------------------------------------------------------
# 5 cases.
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCsrfProtectedDep:
    # 1
    def test_post_without_header_returns_403_token_missing(
        self, client: TestClient
    ) -> None:
        _seat_cookie_with_csrf(client, "csrf-missing@example.com")
        response = client.post("/test-csrf")
        assert response.status_code == 403, response.text
        assert response.json()["detail"] == "CSRF token missing", response.text

    # 2
    def test_post_with_mismatched_header_returns_403_token_mismatch(
        self, client: TestClient
    ) -> None:
        _seat_cookie_with_csrf(client, "csrf-mismatch@example.com")
        response = client.post(
            "/test-csrf",
            headers={"X-CSRF-Token": "deadbeef-not-the-real-cookie-value-12345"},
        )
        assert response.status_code == 403, response.text
        assert response.json()["detail"] == "CSRF token mismatch", response.text

    # 3
    def test_get_method_short_circuits_csrf_check(
        self, client: TestClient
    ) -> None:
        """GET request with cookie auth bypasses CSRF entirely (method gate)."""
        _seat_cookie_with_csrf(client, "csrf-get@example.com")
        response = client.get("/test-csrf-get")
        assert response.status_code == 200, response.text
        assert response.json() == {"ok": True}

    # 4
    def test_bearer_auth_post_without_header_succeeds(
        self, app_and_factory: tuple[FastAPI, sessionmaker]
    ) -> None:
        """Bearer-auth state-mutating POST WITHOUT X-CSRF-Token still succeeds."""
        app, _ = app_and_factory
        seater = TestClient(app)
        plaintext = _issue_bearer(seater, "csrf-bearer-bypass@example.com")

        # Drop cookies so ONLY bearer is presented (unambiguous test signal).
        bearer_client = TestClient(app)
        response = bearer_client.post(
            "/test-csrf",
            headers={"Authorization": f"Bearer {plaintext}"},
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"ok": True}

    # 5
    def test_post_with_matching_header_succeeds(
        self, client: TestClient
    ) -> None:
        csrf = _seat_cookie_with_csrf(client, "csrf-match@example.com")
        response = client.post(
            "/test-csrf",
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"ok": True}
