"""VERIFY-07 WS ticket lifecycle safety — 3 cases: reuse, expired (mocked clock),
cross-user drift. All close 1008.

Coverage:

1.  test_reused_ticket_close_1008          — same ticket consumed twice → 1008
                                              on second connect (atomic single-use,
                                              T-13-25)
2.  test_expired_ticket_close_1008         — ``datetime.now`` monkeypatched +120s
                                              past 60s TTL → 1008 (T-13-26 +
                                              Pitfall 4: patch the SERVICE
                                              module's ``datetime``, not the
                                              global symbol)
3.  test_cross_user_ticket_close_1008      — ticket issued for User A's task,
                                              ``tasks.user_id`` rewritten to a
                                              non-existent id post-issue → 1008
                                              from the WS handler's
                                              ``consumed_user_id != task.user_id``
                                              defence-in-depth check (MID-07,
                                              Phase 13-07 STATE.md lock)

Fixture choice: ``ws_app`` mounts ``auth_router`` + ``ws_ticket_router`` +
``websocket_router`` + ``DualAuthMiddleware``; CsrfMiddleware is omitted because
the WS handshake doesn't trigger HTTP CSRF and ticket flow IS the WS auth
(mirrors test_ws_ticket_flow.py).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

from app.api import dependencies
from app.api.auth_routes import auth_router
from app.api.exception_handlers import (
    invalid_credentials_handler,
    validation_error_handler,
)
from app.api.websocket_api import websocket_router
from app.api.ws_ticket_routes import ws_ticket_router
from app.core.container import Container
from app.core.dual_auth import DualAuthMiddleware
from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import Base

from tests.integration._phase16_helpers import (
    WS_POLICY_VIOLATION,
    _insert_task,
    _register,
)


# ---------------------------------------------------------------
# Fixtures — copy verbatim shape from test_ws_ticket_flow.py:60-113.
# ---------------------------------------------------------------


@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str:
    """File-backed SQLite URL with all tables pre-created."""
    db_file = tmp_path / "ws_ticket_safety_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    return url


@pytest.fixture
def session_factory(tmp_db_url: str):
    """Sessionmaker for direct DB introspection / fixture seeding."""
    engine = create_engine(tmp_db_url, connect_args={"check_same_thread": False})
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def ws_app(
    tmp_db_url: str, session_factory
) -> Generator[tuple[FastAPI, Container], None, None]:
    """Slim FastAPI app: auth + ws_ticket + websocket routers + DualAuthMiddleware.

    A fresh ``Container`` is wired against a per-test SQLite DB and installed
    into ``app.api.dependencies._container`` so the route helpers (and the
    WS endpoint's reach-in to ``dependencies._container``) both observe the
    same instance.

    NOTE: CsrfMiddleware is NOT mounted — WS handshake doesn't trigger HTTP
    CSRF and the ticket flow IS the WS auth. ``POST /api/ws/ticket`` succeeds
    without ``X-CSRF-Token`` because no CSRF guard exists in this stack.
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
    app.include_router(ws_ticket_router)
    app.include_router(websocket_router)
    app.add_middleware(DualAuthMiddleware, container=container)

    yield app, container

    container.unwire()
    container.db_session_factory.reset_override()
    limiter.reset()


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------


def _close_code_from_disconnect(exc: WebSocketDisconnect) -> int:
    """Extract the close code in a Starlette-version-tolerant way."""
    return int(exc.code)


def _issue_ticket(client: TestClient, task_uuid: str) -> str:
    """Issue a fresh WS ticket for ``task_uuid``; return the token string.

    Mirrors test_ws_ticket_flow.py:182-188 — POST /api/ws/ticket with cookie
    auth (set by prior _register call on the same client jar). No CSRF header
    needed because ws_app omits CsrfMiddleware.
    """
    response = client.post("/api/ws/ticket", json={"task_id": task_uuid})
    assert response.status_code == 201, response.text
    return response.json()["ticket"]
