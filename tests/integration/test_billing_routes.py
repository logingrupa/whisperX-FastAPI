"""Integration tests for Phase 13 ``/billing/*`` stub routes.

Coverage (≥5 cases per plan 13-05):

1. test_checkout_stub_returns_501 — auth + valid body → 501 + StubResponse
2. test_checkout_requires_auth — no auth → 401
3. test_webhook_valid_signature_schema_returns_501 — well-formed header → 501
4. test_webhook_missing_signature_returns_400 — no header → 400
5. test_webhook_malformed_signature_returns_400 — garbage header → 400
6. test_stripe_imported_no_runtime_calls — module-load import succeeds (BILL-07)

Slim FastAPI app per test mirrors 13-03/13-04 patterns.
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
from app.api.billing_routes import billing_router
from app.api.billing_webhook_routes import billing_webhook_router
from app.api.exception_handlers import (
    invalid_credentials_handler,
    validation_error_handler,
)
from app.core.container import Container
from app.core.dual_auth import DualAuthMiddleware
from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import Base


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------


@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str:
    """File-backed SQLite URL with all tables pre-created."""
    db_file = tmp_path / "billing_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    return url


@pytest.fixture
def session_factory(tmp_db_url: str):
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=create_engine(tmp_db_url, connect_args={"check_same_thread": False}),
    )


@pytest.fixture
def billing_app(
    tmp_db_url: str, session_factory
) -> Generator[tuple[FastAPI, Container], None, None]:
    """Slim FastAPI app: auth_router + billing_router + DualAuthMiddleware."""
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
    app.include_router(billing_router)
    app.include_router(billing_webhook_router)
    app.add_middleware(DualAuthMiddleware, container=container)

    # Phase 19 Plan 07 additive override (Rule 3): wire app.dependency_overrides
    # for get_db so authenticated_user + csrf_protected resolve against the tmp
    # SQLite. Plan 10 owns the full container-override -> dependency_overrides
    # cutover.
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
def client(billing_app: tuple[FastAPI, Container]) -> TestClient:
    app, _ = billing_app
    return TestClient(app)


def _register(client: TestClient, email: str, password: str = "supersecret123") -> None:
    """Register a user; plumb X-CSRF-Token onto the client for state-mutating calls.

    Phase 19 Plan 07 additive: billing_router applies router-level
    Depends(csrf_protected), so cookie-auth POSTs (e.g. /billing/checkout)
    require X-CSRF-Token. Stamp the csrf_token cookie value as a default
    header on the client after register so subsequent POSTs pass the
    double-submit check; this preserves the legacy test bodies untouched.
    """
    response = client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    csrf = client.cookies.get("csrf_token")
    assert csrf is not None, "csrf_token cookie missing after /auth/register"
    client.headers["X-CSRF-Token"] = csrf


# ---------------------------------------------------------------
# Tests
# ---------------------------------------------------------------


@pytest.mark.integration
def test_checkout_stub_returns_501(client: TestClient) -> None:
    """POST /billing/checkout with auth → 501 + StubResponse body."""
    _register(client, "alice@example.com")
    response = client.post("/billing/checkout", json={"plan": "pro"})
    assert response.status_code == 501
    body = response.json()
    assert body["detail"] == "Not Implemented"
    assert body["status"] == "stub"
    assert "v1.3" in body["hint"]


@pytest.mark.integration
def test_checkout_requires_auth(billing_app: tuple[FastAPI, Container]) -> None:
    """POST /billing/checkout without cookie/bearer → 401."""
    app, _ = billing_app
    client_no_auth = TestClient(app)
    response = client_no_auth.post("/billing/checkout", json={"plan": "pro"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.integration
def test_webhook_valid_signature_schema_returns_501(
    billing_app: tuple[FastAPI, Container],
) -> None:
    """Valid Stripe-Signature schema → 501 + StubResponse (no auth needed)."""
    app, _ = billing_app
    client_no_auth = TestClient(app)
    response = client_no_auth.post(
        "/billing/webhook",
        json={"type": "checkout.session.completed"},
        headers={"Stripe-Signature": "t=1700000000,v1=abc123def456"},
    )
    assert response.status_code == 501, response.text
    body = response.json()
    assert body["detail"] == "Not Implemented"
    assert body["status"] == "stub"
    assert "v1.3" in body["hint"]


@pytest.mark.integration
def test_webhook_missing_signature_returns_400(
    billing_app: tuple[FastAPI, Container],
) -> None:
    """No Stripe-Signature header → 400."""
    app, _ = billing_app
    client_no_auth = TestClient(app)
    response = client_no_auth.post("/billing/webhook", json={})
    assert response.status_code == 400
    assert "Stripe-Signature" in response.json()["detail"]


@pytest.mark.integration
def test_webhook_malformed_signature_returns_400(
    billing_app: tuple[FastAPI, Container],
) -> None:
    """Garbage Stripe-Signature header → 400."""
    app, _ = billing_app
    client_no_auth = TestClient(app)
    response = client_no_auth.post(
        "/billing/webhook",
        json={},
        headers={"Stripe-Signature": "garbage"},
    )
    assert response.status_code == 400
    assert "Stripe-Signature" in response.json()["detail"]


@pytest.mark.integration
def test_stripe_imported_no_runtime_calls() -> None:
    """BILL-07: stripe imports at module-load; module exposes no runtime calls.

    Phase 19-07 split: ``_STRIPE_SIG_PATTERN`` lives on the
    ``app.api.billing_webhook_routes`` module (the webhook moved to its own
    auth-free / CSRF-free router so ``billing_router`` can apply
    router-level CSRF cleanly).
    """
    import app.api.billing_routes as br
    import app.api.billing_webhook_routes as bwr
    import stripe  # type: ignore[import-untyped]
    assert stripe is not None
    # Module-load import is enough — verifier-checked grep enforces zero
    # runtime stripe.* calls in app/. Here we just exercise the import.
    assert hasattr(br, "billing_router")
    assert hasattr(bwr, "_STRIPE_SIG_PATTERN")
    assert hasattr(bwr, "billing_webhook_router")
