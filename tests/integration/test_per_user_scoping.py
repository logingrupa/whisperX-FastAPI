"""Integration tests for Phase 13-07 per-user scoping (SCOPE-02..04).

Coverage (≥10 cases):

  1.  test_get_all_tasks_returns_only_caller_tasks
  2.  test_get_task_by_id_cross_user_returns_404
  3.  test_get_task_by_id_own_returns_200
  4.  test_delete_task_cross_user_returns_404_and_preserves_row
  5.  test_delete_task_own_returns_200
  6.  test_get_task_progress_cross_user_returns_404
  7.  test_ws_ticket_for_other_users_task_returns_404
  8.  test_ws_ticket_for_owned_task_succeeds
  9.  test_repo_unscoped_default_returns_all
  10. test_repo_scoped_returns_only_user
  11. test_get_all_tasks_anonymous_returns_401
  12. test_cross_user_delete_returns_same_404_body_as_unknown_id

Slim FastAPI app per test (mirrors 13-03/13-04/13-06):
  - auth_router (for cookie-acquisition via /auth/register)
  - task_router + ws_ticket_router
  - DualAuthMiddleware for cookie session resolution
  - Per-test Container overridden against a fresh SQLite DB
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
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
from app.api.task_api import task_router
from app.api.ws_ticket_routes import ws_ticket_router
from app.core.container import Container
from app.core.dual_auth import DualAuthMiddleware
from app.core.exceptions import (
    InvalidCredentialsError,
    TaskNotFoundError,
    ValidationError,
)
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import Base
from app.infrastructure.database.models import Task as ORMTask
from app.infrastructure.database.repositories.sqlalchemy_task_repository import (
    SQLAlchemyTaskRepository,
)


# ---------------------------------------------------------------
# Exception handler — TaskNotFoundError → 404
# ---------------------------------------------------------------


async def _task_not_found_handler(_request, exc: TaskNotFoundError):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=404, content={"detail": "Task not found"})


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------


@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str:
    db_file = tmp_path / "scoping_test.db"
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
def app_and_container(
    tmp_db_url: str, session_factory
) -> Generator[tuple[FastAPI, Container], None, None]:
    """Slim FastAPI app: auth + task + ws_ticket routers + DualAuthMiddleware."""
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
    app.include_router(ws_ticket_router)
    app.add_middleware(DualAuthMiddleware, container=container)

    # Phase 19 Plan 07 additive override (Rule 3): wire app.dependency_overrides
    # for get_db so authenticated_user + the v2 service chain resolves against
    # the tmp SQLite. Plan 10 owns the full fixture migration.
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
def client(app_and_container: tuple[FastAPI, Container]) -> TestClient:
    app, _ = app_and_container
    return TestClient(app)


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------


def _register(client: TestClient, email: str, password: str = "supersecret123") -> int:
    """Register via /auth/register; cookie set on the jar; returns user_id.

    Phase 19 Plan 07 additive: task_router + ws_ticket_router both apply
    router-level Depends(csrf_protected); plumb the csrf_token cookie
    value as a default X-CSRF-Token header so subsequent
    DELETE/POST calls pass the double-submit check.
    """
    response = client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert response.status_code == 201, response.text
    csrf = client.cookies.get("csrf_token")
    assert csrf is not None, "csrf_token cookie missing after /auth/register"
    client.headers["X-CSRF-Token"] = csrf
    return int(response.json()["user_id"])


def _insert_task(
    session_factory, *, user_id: int, uuid: str | None = None, status: str = "pending"
) -> str:
    """Insert a task row owned by user_id; return its UUID."""
    if uuid is None:
        uuid = (
            f"uuid-u{user_id}-{datetime.now(timezone.utc).timestamp()}"
            f"-{id(session_factory)}"
        )
    with session_factory() as session:
        session.add(
            ORMTask(
                uuid=uuid,
                status=status,
                file_name="audio.mp3",
                task_type="speech-to-text",
                user_id=user_id,
            )
        )
        session.commit()
    return uuid


# ---------------------------------------------------------------
# 1. /task/all — list endpoint scope isolation
# ---------------------------------------------------------------


@pytest.mark.integration
def test_get_all_tasks_returns_only_caller_tasks(
    client: TestClient, session_factory
) -> None:
    """User A inserts 3 tasks, User B inserts 2; each sees only their own."""
    user_a = _register(client, "alice@example.com")
    _insert_task(session_factory, user_id=user_a, uuid="alice-1")
    _insert_task(session_factory, user_id=user_a, uuid="alice-2")
    _insert_task(session_factory, user_id=user_a, uuid="alice-3")

    # Switch to User B by clearing cookies + registering fresh
    client.cookies.clear()
    user_b = _register(client, "bob@example.com")
    _insert_task(session_factory, user_id=user_b, uuid="bob-1")
    _insert_task(session_factory, user_id=user_b, uuid="bob-2")

    # B's view: only 2 tasks
    resp_b = client.get("/task/all")
    assert resp_b.status_code == 200
    b_uuids = {t["identifier"] for t in resp_b.json()["tasks"]}
    assert b_uuids == {"bob-1", "bob-2"}

    # Switch back to A
    client.cookies.clear()
    client.post(
        "/auth/login", json={"email": "alice@example.com", "password": "supersecret123"}
    )
    resp_a = client.get("/task/all")
    assert resp_a.status_code == 200
    a_uuids = {t["identifier"] for t in resp_a.json()["tasks"]}
    assert a_uuids == {"alice-1", "alice-2", "alice-3"}


# ---------------------------------------------------------------
# 2. GET /task/{id} cross-user → 404
# ---------------------------------------------------------------


@pytest.mark.integration
def test_get_task_by_id_cross_user_returns_404(
    client: TestClient, session_factory
) -> None:
    """User B requesting User A's task returns opaque 404."""
    user_a = _register(client, "alice2@example.com")
    _insert_task(session_factory, user_id=user_a, uuid="alice-secret")

    client.cookies.clear()
    _register(client, "bob2@example.com")

    resp = client.get("/task/alice-secret")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Task not found"


@pytest.mark.integration
def test_get_task_by_id_own_returns_200(
    client: TestClient, session_factory
) -> None:
    """Caller can fetch their own task by id."""
    user_a = _register(client, "carol@example.com")
    _insert_task(session_factory, user_id=user_a, uuid="carol-task")

    resp = client.get("/task/carol-task")
    assert resp.status_code == 200


# ---------------------------------------------------------------
# 3. DELETE /task/{id} cross-user → 404 + row preserved
# ---------------------------------------------------------------


@pytest.mark.integration
def test_delete_task_cross_user_returns_404_and_preserves_row(
    client: TestClient, session_factory
) -> None:
    """Cross-user DELETE returns 404; A's task remains intact."""
    user_a = _register(client, "alice3@example.com")
    _insert_task(session_factory, user_id=user_a, uuid="alice-keep")

    client.cookies.clear()
    _register(client, "mallory@example.com")

    resp = client.delete("/task/alice-keep/delete")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Task not found"

    # Direct DB check: row still exists with original owner
    with session_factory() as session:
        row = session.query(ORMTask).filter(ORMTask.uuid == "alice-keep").first()
        assert row is not None
        assert row.user_id == user_a


@pytest.mark.integration
def test_delete_task_own_returns_200(
    client: TestClient, session_factory
) -> None:
    """Caller can delete their own task."""
    user_a = _register(client, "dave@example.com")
    _insert_task(session_factory, user_id=user_a, uuid="dave-task")

    resp = client.delete("/task/dave-task/delete")
    assert resp.status_code == 200

    with session_factory() as session:
        row = session.query(ORMTask).filter(ORMTask.uuid == "dave-task").first()
        assert row is None


# ---------------------------------------------------------------
# 4. GET /tasks/{id}/progress cross-user → 404
# ---------------------------------------------------------------


@pytest.mark.integration
def test_get_task_progress_cross_user_returns_404(
    client: TestClient, session_factory
) -> None:
    """Cross-user progress lookup returns opaque 404."""
    user_a = _register(client, "eve@example.com")
    _insert_task(session_factory, user_id=user_a, uuid="eve-task")

    client.cookies.clear()
    _register(client, "frank@example.com")

    resp = client.get("/tasks/eve-task/progress")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Task not found"


# ---------------------------------------------------------------
# 5. WS ticket — owned task succeeds; cross-user 404
# ---------------------------------------------------------------


@pytest.mark.integration
def test_ws_ticket_for_owned_task_succeeds(
    client: TestClient, session_factory
) -> None:
    """Owner can issue a WS ticket via the scoped repo path."""
    user_a = _register(client, "grace@example.com")
    _insert_task(session_factory, user_id=user_a, uuid="grace-task")

    resp = client.post("/api/ws/ticket", json={"task_id": "grace-task"})
    assert resp.status_code == 201
    assert len(resp.json()["ticket"]) == 32


@pytest.mark.integration
def test_ws_ticket_for_other_users_task_returns_404(
    client: TestClient, session_factory
) -> None:
    """Cross-user WS ticket attempt returns opaque 404 (anti-enum)."""
    user_a = _register(client, "henry@example.com")
    _insert_task(session_factory, user_id=user_a, uuid="henry-task")

    client.cookies.clear()
    _register(client, "ivy@example.com")

    resp = client.post("/api/ws/ticket", json={"task_id": "henry-task"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Task not found"


# ---------------------------------------------------------------
# 6. Repository-level scope unit checks (in-process — Phase 12 backwards
# compat for CLI / admin paths)
# ---------------------------------------------------------------


@pytest.mark.integration
def test_repo_unscoped_default_returns_all(session_factory) -> None:
    """Unscoped repo (CLI / admin) sees every row regardless of owner."""
    with session_factory() as session:
        # Need a user row to satisfy FK
        from app.infrastructure.database.models import User as ORMUser

        for uid in (101, 102):
            session.add(
                ORMUser(id=uid, email=f"u{uid}@x.com", password_hash="x")
            )
        session.commit()

    _insert_task(session_factory, user_id=101, uuid="multi-1")
    _insert_task(session_factory, user_id=102, uuid="multi-2")

    with session_factory() as session:
        repo = SQLAlchemyTaskRepository(session)
        assert repo._user_scope is None
        all_uuids = {t.uuid for t in repo.get_all()}
    assert {"multi-1", "multi-2"}.issubset(all_uuids)


@pytest.mark.integration
def test_repo_scoped_returns_only_user(session_factory) -> None:
    """Repo with set_user_scope(N) returns only rows where user_id == N."""
    with session_factory() as session:
        from app.infrastructure.database.models import User as ORMUser

        for uid in (201, 202):
            session.add(
                ORMUser(id=uid, email=f"u{uid}@x.com", password_hash="x")
            )
        session.commit()

    _insert_task(session_factory, user_id=201, uuid="own-1")
    _insert_task(session_factory, user_id=201, uuid="own-2")
    _insert_task(session_factory, user_id=202, uuid="other-1")

    with session_factory() as session:
        repo = SQLAlchemyTaskRepository(session)
        repo.set_user_scope(201)
        scoped_uuids = {t.uuid for t in repo.get_all()}
    assert scoped_uuids == {"own-1", "own-2"}


# ---------------------------------------------------------------
# 7. Negative paths — auth required & opaque body parity
# ---------------------------------------------------------------


@pytest.mark.integration
def test_get_all_tasks_anonymous_returns_401(client: TestClient) -> None:
    """No cookie → DualAuthMiddleware rejects with 401."""
    client.cookies.clear()
    resp = client.get("/task/all")
    assert resp.status_code == 401


@pytest.mark.integration
def test_post_speech_to_text_persists_with_user_id(
    app_and_container: tuple[FastAPI, Container],
    client: TestClient,
    session_factory,
) -> None:
    """Direct exercise: scoped repo.add() persists task with caller's user_id.

    Bypasses the full /speech-to-text route (which depends on heavy
    audio-decode + ML), but exercises the SAME wiring the route uses:
    container.task_repository() + set_user_scope(user.id) + repo.add().
    Proves the scope mechanism injects user_id at write-time.
    """
    _, container = app_and_container
    user_id = _register(client, "monica@example.com")

    # Acquire a scoped repo exactly the way get_scoped_task_repository does
    repo = container.task_repository()
    repo.set_user_scope(user_id)

    from app.domain.entities.task import Task as DomainTask

    task = DomainTask(
        uuid="monica-task-1",
        status="processing",
        task_type="speech-to-text",
        # NB: user_id intentionally None — scope must inject it
        user_id=None,
    )
    persisted_uuid = repo.add(task)
    repo.set_user_scope(None)

    assert persisted_uuid == "monica-task-1"
    with session_factory() as session:
        row = session.query(ORMTask).filter(ORMTask.uuid == "monica-task-1").first()
        assert row is not None
        assert row.user_id == user_id


@pytest.mark.integration
def test_cross_user_delete_returns_same_404_body_as_unknown_id(
    client: TestClient, session_factory
) -> None:
    """Cross-user DELETE and unknown-uuid DELETE share identical 404 shape.

    Anti-enumeration: caller cannot distinguish "task does not exist" from
    "task exists but belongs to someone else".
    """
    user_a = _register(client, "kate@example.com")
    _insert_task(session_factory, user_id=user_a, uuid="kate-private")

    client.cookies.clear()
    _register(client, "leo@example.com")

    cross = client.delete("/task/kate-private/delete")
    unknown = client.delete("/task/uuid-does-not-exist/delete")

    assert cross.status_code == 404
    assert unknown.status_code == 404
    assert cross.json() == unknown.json()  # identical opaque shape
