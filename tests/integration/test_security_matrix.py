"""VERIFY-01 cross-user matrix.

Parametrized 8 endpoints x {self, foreign}. Two TestClient instances, same
app + DB. Foreign-leg expected status from ENDPOINT_CATALOG; self-leg
confirms positive control. Anti-enumeration parity asserted: foreign-id
404 body bytewise-identical to unknown-id 404 body for /task/{id}.

Pitfall coverage:
    1. limiter.reset() in BOTH setup AND teardown (rate-limit poisoning)
    2. Two TestClient(app) instances per test (cookie jar isolation)
    3. CsrfMiddleware registered FIRST so DualAuth runs FIRST on dispatch

Code-quality invariants:
    DRT  - ENDPOINT_CATALOG single source; _request, _format_url, _seed_resources reused
    SRP  - one assertion per test
    Tiger-style - every assertion carries failure-message with response.text
    No nested-if - flat conditionals + dict lookups only
    Self-explanatory naming - client_a, client_b, foreign_response, unknown_response
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import dependencies
from app.api.account_routes import account_router
from app.api.auth_routes import auth_router
from app.api.exception_handlers import (
    invalid_credentials_handler,
    validation_error_handler,
)
from app.api.key_routes import key_router
from app.api.task_api import task_router
from app.api.ws_ticket_routes import ws_ticket_router
from app.core.container import Container
from app.core.csrf_middleware import CsrfMiddleware
from app.core.dual_auth import DualAuthMiddleware
from app.core.exceptions import (
    InvalidCredentialsError,
    TaskNotFoundError,
    ValidationError,
)
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import Base

from tests.integration._phase16_helpers import (
    ENDPOINT_CATALOG,
    _insert_task,
    _register,
    _seed_two_users,
)


# ---------------------------------------------------------------------------
# Exception handler — TaskNotFoundError -> 404
# (Pattern: test_per_user_scoping.py:67-70)
# ---------------------------------------------------------------------------


async def _task_not_found_handler(_request, _exc: TaskNotFoundError):
    return JSONResponse(status_code=404, content={"detail": "Task not found"})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str:
    """File-backed SQLite URL with all tables pre-created."""
    db_file = tmp_path / "security_matrix_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    return url


@pytest.fixture
def session_factory(tmp_db_url: str):
    """Sessionmaker bound to the per-test DB engine."""
    engine = create_engine(tmp_db_url, connect_args={"check_same_thread": False})
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def full_app(
    tmp_db_url: str, session_factory
) -> Generator[tuple[FastAPI, Container], None, None]:
    """Slim FastAPI app with all 5 routers + CSRF + DualAuth middleware.

    ASGI middleware ORDER LOCKED (Pitfall 3): registration is REVERSED on
    dispatch. Registering CsrfMiddleware FIRST means it runs SECOND on
    dispatch -> DualAuth runs FIRST -> request.state.auth_method is set
    BEFORE CsrfMiddleware reads it.
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
    app.add_exception_handler(TaskNotFoundError, _task_not_found_handler)

    app.include_router(auth_router)
    app.include_router(task_router)
    app.include_router(key_router)
    app.include_router(account_router)
    app.include_router(ws_ticket_router)

    # Pitfall 3: CSRF FIRST registration -> DualAuth FIRST on dispatch.
    app.add_middleware(CsrfMiddleware, container=container)
    app.add_middleware(DualAuthMiddleware, container=container)

    yield app, container

    container.unwire()
    container.db_session_factory.reset_override()
    limiter.reset()


# ---------------------------------------------------------------------------
# Resource-seeding helpers — DRT for both foreign + self legs.
# ---------------------------------------------------------------------------


def _create_key(client: TestClient) -> int:
    """POST /api/keys for the authenticated client; return key_id.

    State-mutating route -> sends X-CSRF-Token from the cookie jar.
    """
    csrf_token = client.cookies.get("csrf_token") or ""
    response = client.post(
        "/api/keys",
        json={"name": "test-key"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def _seed_resources(
    app: FastAPI, session_factory
) -> tuple[TestClient, TestClient, dict[str, str]]:
    """Build two clients (separate jars) + insert User A's task + key.

    Returns:
        (client_a, client_b, resources)
        resources: {"task_uuid": <A's uuid>, "key_id": <A's key id as str>}
    """
    client_a = TestClient(app)
    client_b = TestClient(app)
    user_a_id, _ = _seed_two_users(client_a, client_b)
    task_uuid = _insert_task(session_factory, user_id=user_a_id)
    key_id = _create_key(client_a)
    return client_a, client_b, {"task_uuid": task_uuid, "key_id": str(key_id)}
