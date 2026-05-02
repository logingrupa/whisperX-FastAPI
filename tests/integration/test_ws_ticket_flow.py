"""Integration tests for the WS ticket flow (Plan 13-06; MID-06 + MID-07).

Coverage (≥10 cases):

1.  test_issue_ticket_for_owned_task            — 201 + 32-char + expires_at +60s
2.  test_issue_ticket_for_unknown_task          — 404 opaque
3.  test_issue_ticket_for_other_users_task      — 404 opaque (anti-enum, T-13-24)
4.  test_issue_ticket_requires_auth             — 401
5.  test_ws_connect_with_valid_ticket           — accept + ping/pong
6.  test_ws_reject_missing_ticket               — close 1008
7.  test_ws_reject_reused_ticket                — second connect close 1008
8.  test_ws_reject_expired_ticket               — TTL exceeded close 1008
9.  test_ws_reject_ticket_for_different_task    — wrong task_id close 1008
10. test_ws_reject_unknown_task_id              — non-existent task close 1008
11. test_ws_reject_unknown_ticket_token         — random token close 1008

Phase 19 Plan 10: slim app + dependency_overrides[get_db] only — auth on
POST /api/ws/ticket is owned by Depends(authenticated_user); the WS
endpoint itself uses an explicit `with SessionLocal() as db` block
(Plan 08), and we monkeypatch the module-level SessionLocal so the WS
scope reaches the tmp SQLite the same way the HTTP scope does.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded
from sqlalchemy import create_engine
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
from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import Base
from app.infrastructure.database.models import Task as ORMTask


WS_POLICY_VIOLATION = 1008


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------


@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str:
    """File-backed SQLite URL with all tables pre-created."""
    db_file = tmp_path / "ws_ticket_test.db"
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
) -> Generator[FastAPI, None, None]:
    """Slim FastAPI app: auth + ws_ticket + websocket routers.

    Phase 19 Plan 10: dependency_overrides[get_db] is the SOLE DB-binding
    seam for HTTP routes. The WS endpoint has no Depends, so we
    monkey-patch the module-level ``websocket_api.SessionLocal`` to point
    at the tmp DB session_factory (same shape as production SessionLocal).
    """
    limiter.reset()

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(InvalidCredentialsError, invalid_credentials_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.include_router(auth_router)
    app.include_router(ws_ticket_router)
    app.include_router(websocket_router)

    def _override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[dependencies.get_db] = _override_get_db

    # Phase 19 Plan 08: WS scope has no Depends, so monkey-patch the
    # module-level SessionLocal that websocket_api.py uses for its
    # explicit `with SessionLocal() as db:` block. The session_factory
    # is a sessionmaker — same shape as production SessionLocal.
    from app.api import websocket_api as _ws_api

    original_session_local = _ws_api.SessionLocal
    _ws_api.SessionLocal = session_factory

    yield app

    _ws_api.SessionLocal = original_session_local
    app.dependency_overrides.clear()
    limiter.reset()


@pytest.fixture
def client(ws_app: FastAPI) -> TestClient:
    return TestClient(ws_app)


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------


def _register(
    client: TestClient, email: str, password: str = "supersecret123"
) -> int:
    """Register a user via /auth/register; return the user_id.

    Cookies set on the TestClient jar by the response. Phase 19 Plan 07
    additive: ws_ticket_router applies router-level Depends(csrf_protected);
    plumb the csrf_token cookie value as a default X-CSRF-Token header so
    POST /api/ws/ticket passes the double-submit check.
    """
    response = client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert response.status_code == 201, response.text
    csrf = client.cookies.get("csrf_token")
    assert csrf is not None, "csrf_token cookie missing after /auth/register"
    client.headers["X-CSRF-Token"] = csrf
    return int(response.json()["user_id"])


def _insert_task(session_factory, *, user_id: int | None) -> str:
    """INSERT a tasks row owned by ``user_id``; return its UUID.

    ``user_id=None`` mints an ownerless task (used for cross-user tests
    that need a task no caller can claim).
    """
    with session_factory() as session:
        task_uuid = (
            f"uuid-{user_id or 'none'}-"
            f"{datetime.now(timezone.utc).timestamp()}"
        )
        task = ORMTask(
            uuid=task_uuid,
            status="pending",
            result=None,
            file_name="audio.mp3",
            task_type="speech-to-text",
            user_id=user_id,
        )
        session.add(task)
        session.commit()
        return task_uuid


def _close_code_from_disconnect(exc: WebSocketDisconnect) -> int:
    """Extract the close code in a Starlette-version-tolerant way."""
    return int(exc.code)


# ---------------------------------------------------------------
# HTTP tests — POST /api/ws/ticket
# ---------------------------------------------------------------


@pytest.mark.integration
def test_issue_ticket_for_owned_task(
    client: TestClient, session_factory
) -> None:
    """Owner POSTs and receives a 32-char ticket with ~60s TTL."""
    user_id = _register(client, "alice@example.com")
    task_uuid = _insert_task(session_factory, user_id=user_id)

    response = client.post("/api/ws/ticket", json={"task_id": task_uuid})
    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body["ticket"], str)
    assert len(body["ticket"]) == 32
    expires_at = datetime.fromisoformat(body["expires_at"])
    now = datetime.now(timezone.utc)
    # Allow a generous +/-5s window to accommodate slow CI clocks
    assert now + timedelta(seconds=55) <= expires_at <= now + timedelta(seconds=65)


@pytest.mark.integration
def test_issue_ticket_for_unknown_task(client: TestClient) -> None:
    """Unknown task_id returns the opaque 404 (no enumeration)."""
    _register(client, "bob@example.com")
    response = client.post(
        "/api/ws/ticket", json={"task_id": "uuid-does-not-exist-xxx"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


@pytest.mark.integration
def test_issue_ticket_for_other_users_task(
    client: TestClient, session_factory
) -> None:
    """User B cannot ticket User A's task — 404 with identical opaque body."""
    user_a = _register(client, "alice2@example.com")
    task_uuid = _insert_task(session_factory, user_id=user_a)

    # Switch to user B — clear A's cookie jar then register B
    client.cookies.clear()
    _register(client, "mallory@example.com")

    response = client.post("/api/ws/ticket", json={"task_id": task_uuid})
    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


@pytest.mark.integration
def test_issue_ticket_requires_auth(client: TestClient) -> None:
    """Anonymous POST returns 401 (DualAuthMiddleware rejects)."""
    client.cookies.clear()
    response = client.post("/api/ws/ticket", json={"task_id": "anything"})
    assert response.status_code == 401


# ---------------------------------------------------------------
# WS tests — /ws/tasks/{task_id}?ticket=...
# ---------------------------------------------------------------


@pytest.mark.integration
def test_ws_connect_with_valid_ticket(
    client: TestClient, session_factory
) -> None:
    """Valid ticket → connection accepts; ping/pong round-trip works."""
    user_id = _register(client, "carol@example.com")
    task_uuid = _insert_task(session_factory, user_id=user_id)
    ticket_resp = client.post("/api/ws/ticket", json={"task_id": task_uuid})
    ticket = ticket_resp.json()["ticket"]

    with client.websocket_connect(
        f"/ws/tasks/{task_uuid}?ticket={ticket}"
    ) as ws:
        ws.send_json({"type": "ping"})
        message = ws.receive_json()
        assert message == {"type": "pong"}


@pytest.mark.integration
def test_ws_reject_missing_ticket(
    client: TestClient, session_factory
) -> None:
    """No ?ticket query param → close 1008."""
    user_id = _register(client, "dave@example.com")
    task_uuid = _insert_task(session_factory, user_id=user_id)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/tasks/{task_uuid}"):
            pass
    assert _close_code_from_disconnect(exc_info.value) == WS_POLICY_VIOLATION


@pytest.mark.integration
def test_ws_reject_reused_ticket(
    client: TestClient, session_factory
) -> None:
    """Second connect with the same ticket → close 1008 (single-use)."""
    user_id = _register(client, "eve@example.com")
    task_uuid = _insert_task(session_factory, user_id=user_id)
    ticket = client.post(
        "/api/ws/ticket", json={"task_id": task_uuid}
    ).json()["ticket"]

    # First connection succeeds
    with client.websocket_connect(
        f"/ws/tasks/{task_uuid}?ticket={ticket}"
    ) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}

    # Reuse the same ticket → 1008
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            f"/ws/tasks/{task_uuid}?ticket={ticket}"
        ):
            pass
    assert _close_code_from_disconnect(exc_info.value) == WS_POLICY_VIOLATION


@pytest.mark.integration
def test_ws_reject_expired_ticket(
    client: TestClient,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TTL-exceeded ticket → close 1008.

    Issue a ticket, then fast-forward ``datetime.now`` inside the service
    module so ``consume`` observes ``expires_at < now``.
    """
    user_id = _register(client, "frank@example.com")
    task_uuid = _insert_task(session_factory, user_id=user_id)
    ticket = client.post(
        "/api/ws/ticket", json={"task_id": task_uuid}
    ).json()["ticket"]

    real_now = datetime.now(timezone.utc)
    fake_now = real_now + timedelta(seconds=120)

    class _FrozenDatetime(datetime):  # noqa: D401
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return fake_now

    monkeypatch.setattr(
        "app.services.ws_ticket_service.datetime", _FrozenDatetime
    )

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            f"/ws/tasks/{task_uuid}?ticket={ticket}"
        ):
            pass
    assert _close_code_from_disconnect(exc_info.value) == WS_POLICY_VIOLATION


@pytest.mark.integration
def test_ws_reject_ticket_for_different_task(
    client: TestClient, session_factory
) -> None:
    """Ticket issued for task A used on task B → close 1008 (T-13-27)."""
    user_id = _register(client, "grace@example.com")
    task_a = _insert_task(session_factory, user_id=user_id)
    task_b = _insert_task(session_factory, user_id=user_id)
    ticket = client.post(
        "/api/ws/ticket", json={"task_id": task_a}
    ).json()["ticket"]

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            f"/ws/tasks/{task_b}?ticket={ticket}"
        ):
            pass
    assert _close_code_from_disconnect(exc_info.value) == WS_POLICY_VIOLATION


@pytest.mark.integration
def test_ws_reject_unknown_task_id(client: TestClient) -> None:
    """WS connect to a task that does not exist → close 1008."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            "/ws/tasks/uuid-no-such-task?ticket=anything-32-chars-long-xxx"
        ):
            pass
    assert _close_code_from_disconnect(exc_info.value) == WS_POLICY_VIOLATION


@pytest.mark.integration
def test_ws_reject_unknown_ticket_token(
    client: TestClient, session_factory
) -> None:
    """Random token not issued by the service → close 1008."""
    user_id = _register(client, "henry@example.com")
    task_uuid = _insert_task(session_factory, user_id=user_id)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            f"/ws/tasks/{task_uuid}?ticket=this-token-was-never-issued-xx"
        ):
            pass
    assert _close_code_from_disconnect(exc_info.value) == WS_POLICY_VIOLATION
