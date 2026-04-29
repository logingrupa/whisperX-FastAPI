"""Integration tests for Phase 13 ``/api/account/*`` routes.

Coverage (≥6 cases per plan 13-05):

1. test_delete_user_data_removes_tasks — INSERT 3 tasks; DELETE; 0 remaining
2. test_delete_user_data_preserves_user_row — users row survives
3. test_delete_user_data_removes_uploaded_files — UPLOAD_DIR + tus dir cleaned
4. test_delete_user_data_skips_missing_files — best-effort; 204 OK
5. test_delete_user_data_cross_user_isolation — A's data survives B's DELETE
6. test_delete_user_data_requires_auth — no auth → 401

Slim FastAPI app per test mirrors 13-03/13-04 patterns:
  - mounts auth_router (cookie acquisition) + account_router
  - mounts DualAuthMiddleware for cookie/bearer resolution
  - per-test Container override against tmp SQLite
  - monkey-patches UPLOAD_DIR / TUS_UPLOAD_DIR on account_service module
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
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.api import dependencies
from app.api.account_routes import account_router
from app.api.auth_routes import auth_router
from app.api.exception_handlers import (
    invalid_credentials_handler,
    validation_error_handler,
)
from app.core.container import Container
from app.core.dual_auth import DualAuthMiddleware
from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import Base
from app.infrastructure.database.models import Task as ORMTask
from app.infrastructure.database.models import User as ORMUser
from app.services import account_service as account_service_module


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------


@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str:
    """File-backed SQLite URL with all tables pre-created."""
    db_file = tmp_path / "account_test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    return url


@pytest.fixture
def session_factory(tmp_db_url: str):
    """Sessionmaker for direct DB introspection in tests."""
    engine = create_engine(tmp_db_url, connect_args={"check_same_thread": False})
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def upload_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    """Redirect AccountService UPLOAD_DIR + TUS_UPLOAD_DIR to tmp."""
    upload_dir = tmp_path / "uploads"
    tus_dir = upload_dir / "tus"
    upload_dir.mkdir()
    tus_dir.mkdir()
    monkeypatch.setattr(account_service_module, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(account_service_module, "TUS_UPLOAD_DIR", tus_dir)
    return upload_dir, tus_dir


@pytest.fixture
def account_app(
    tmp_db_url: str, session_factory
) -> Generator[tuple[FastAPI, Container], None, None]:
    """Slim FastAPI app: auth_router + account_router + DualAuthMiddleware."""
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
    app.include_router(account_router)
    app.add_middleware(DualAuthMiddleware, container=container)

    yield app, container

    container.unwire()
    container.db_session_factory.reset_override()
    limiter.reset()


@pytest.fixture
def client(account_app: tuple[FastAPI, Container]) -> TestClient:
    app, _ = account_app
    return TestClient(app)


def _register(client: TestClient, email: str, password: str = "supersecret123") -> int:
    """Register a user via /auth/register; return the user_id."""
    response = client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return int(response.json()["user_id"])


def _insert_task(
    session_factory, *, user_id: int, file_name: str | None
) -> int:
    """INSERT a tasks row for ``user_id``; return the new task id."""
    with session_factory() as session:
        task = ORMTask(
            uuid=f"uuid-{user_id}-{file_name or 'no-file'}-{datetime.now(timezone.utc).timestamp()}",
            status="pending",
            result=None,
            file_name=file_name,
            task_type="speech-to-text",
            user_id=user_id,
        )
        session.add(task)
        session.commit()
        return int(task.id)


# ---------------------------------------------------------------
# Tests
# ---------------------------------------------------------------


@pytest.mark.integration
def test_delete_user_data_removes_tasks(
    client: TestClient, session_factory, upload_dirs: tuple[Path, Path]
) -> None:
    """DELETE /api/account/data removes ALL caller's tasks (3 → 0)."""
    user_id = _register(client, "alice@example.com")
    for index in range(3):
        _insert_task(session_factory, user_id=user_id, file_name=None)
    # Pre-condition
    with session_factory() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM tasks WHERE user_id = :uid"),
            {"uid": user_id},
        ).scalar_one()
        assert count == 3
    # Act
    response = client.delete("/api/account/data")
    assert response.status_code == 204
    # Post-condition
    with session_factory() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM tasks WHERE user_id = :uid"),
            {"uid": user_id},
        ).scalar_one()
        assert count == 0


@pytest.mark.integration
def test_delete_user_data_preserves_user_row(
    client: TestClient, session_factory, upload_dirs: tuple[Path, Path]
) -> None:
    """DELETE keeps the users row intact (Phase 15 SCOPE-06 will extend)."""
    user_id = _register(client, "bob@example.com")
    _insert_task(session_factory, user_id=user_id, file_name=None)
    response = client.delete("/api/account/data")
    assert response.status_code == 204
    with session_factory() as session:
        user = session.execute(
            select(ORMUser).where(ORMUser.id == user_id)
        ).scalar_one_or_none()
        assert user is not None
        assert user.email == "bob@example.com"


@pytest.mark.integration
def test_delete_user_data_removes_uploaded_files(
    client: TestClient,
    session_factory,
    upload_dirs: tuple[Path, Path],
) -> None:
    """Files at UPLOAD_DIR/<name> + UPLOAD_DIR/tus/<name> are cleaned up."""
    upload_dir, tus_dir = upload_dirs
    user_id = _register(client, "carol@example.com")
    file_a = "foo.mp3"
    file_b = "bar.mp3"
    (upload_dir / file_a).write_bytes(b"audio-a")
    (tus_dir / file_b).write_bytes(b"audio-b")
    _insert_task(session_factory, user_id=user_id, file_name=file_a)
    _insert_task(session_factory, user_id=user_id, file_name=file_b)
    assert (upload_dir / file_a).exists()
    assert (tus_dir / file_b).exists()
    response = client.delete("/api/account/data")
    assert response.status_code == 204
    assert not (upload_dir / file_a).exists()
    assert not (tus_dir / file_b).exists()


@pytest.mark.integration
def test_delete_user_data_skips_missing_files(
    client: TestClient, session_factory, upload_dirs: tuple[Path, Path]
) -> None:
    """Best-effort: missing files do NOT cause failure; endpoint returns 204."""
    user_id = _register(client, "dan@example.com")
    _insert_task(session_factory, user_id=user_id, file_name="never-existed.mp3")
    response = client.delete("/api/account/data")
    assert response.status_code == 204


@pytest.mark.integration
def test_delete_user_data_cross_user_isolation(
    account_app: tuple[FastAPI, Container],
    session_factory,
    upload_dirs: tuple[Path, Path],
) -> None:
    """User B's DELETE only affects User B; User A's tasks survive."""
    app, _ = account_app
    client_a = TestClient(app)
    client_b = TestClient(app)
    user_a_id = _register(client_a, "alice@a.com")
    user_b_id = _register(client_b, "bob@b.com")
    # User A creates 3 tasks
    for index in range(3):
        _insert_task(session_factory, user_id=user_a_id, file_name=None)
    # User B creates 2 tasks
    for index in range(2):
        _insert_task(session_factory, user_id=user_b_id, file_name=None)
    # User B issues DELETE
    response = client_b.delete("/api/account/data")
    assert response.status_code == 204
    # User A's 3 tasks survive; User B's 2 deleted
    with session_factory() as session:
        a_count = session.execute(
            text("SELECT COUNT(*) FROM tasks WHERE user_id = :uid"),
            {"uid": user_a_id},
        ).scalar_one()
        b_count = session.execute(
            text("SELECT COUNT(*) FROM tasks WHERE user_id = :uid"),
            {"uid": user_b_id},
        ).scalar_one()
        assert a_count == 3
        assert b_count == 0


@pytest.mark.integration
def test_delete_user_data_requires_auth(
    account_app: tuple[FastAPI, Container],
) -> None:
    """DELETE without cookie/bearer → 401."""
    app, _ = account_app
    client_no_auth = TestClient(app)
    response = client_no_auth.delete("/api/account/data")
    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


# ---------------------------------------------------------------
# GET /api/account/me — Plan 15-03 (UI-07 server-side hydration)
# ---------------------------------------------------------------


@pytest.mark.integration
def test_get_account_me_returns_summary(
    client: TestClient, upload_dirs: tuple[Path, Path]
) -> None:
    """Authenticated GET returns AccountSummaryResponse-shaped JSON for caller."""
    email = "alice-me@example.com"
    _register(client, email)

    response = client.get("/api/account/me")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == email
    assert body["plan_tier"] in {"trial", "free", "pro", "team"}
    assert isinstance(body["user_id"], int)
    assert body["user_id"] > 0
    assert isinstance(body["token_version"], int)
    # trial_started_at can be null (no API key created yet) but key MUST exist
    assert "trial_started_at" in body


@pytest.mark.integration
def test_get_account_me_requires_auth(
    account_app: tuple[FastAPI, Container],
) -> None:
    """Anonymous GET → 401 with the same generic detail used elsewhere (T-15-04)."""
    app, _ = account_app
    anon = TestClient(app)

    response = anon.get("/api/account/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.integration
def test_get_account_me_response_shape_locked(
    client: TestClient, upload_dirs: tuple[Path, Path]
) -> None:
    """Response keys are EXACTLY the 5 declared fields — no extras leaked (T-15-11)."""
    email = "alice-shape@example.com"
    _register(client, email)

    response = client.get("/api/account/me")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {
        "user_id",
        "email",
        "plan_tier",
        "trial_started_at",
        "token_version",
    }
