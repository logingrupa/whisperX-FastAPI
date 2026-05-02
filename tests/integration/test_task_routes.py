"""Integration tests for /task/all pagination + search (Plan 15-ux).

Coverage:
  1. Pagination respects user scope (User A page 1 does not leak User B)
  2. q matches file_name substring (case-insensitive)
  3. status filter narrows to one bucket
  4. Bounds: page<1 -> 422
  5. Bounds: page_size>200 -> 422
  6. Bounds: page_size<1 -> 422
  7. Empty result returns total=0
  8. Total reflects un-paginated count under filters
  9. Newest tasks come first (created_at DESC)

Phase 19 Plan 10: slim app + dependency_overrides[get_db] only — auth and
scope are owned by the new Depends graph (Depends(authenticated_user) +
get_scoped_task_management_service_v2). No DualAuthMiddleware, no Container.
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

from app.api import dependencies
from app.api.auth_routes import auth_router
from app.api.exception_handlers import (
    invalid_credentials_handler,
    validation_error_handler,
)
from app.api.task_api import task_router
from app.core.exceptions import (
    InvalidCredentialsError,
    TaskNotFoundError,
    ValidationError,
)
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import Base
from app.infrastructure.database.models import Task as ORMTask


async def _task_not_found_handler(_request, exc: TaskNotFoundError):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=404, content={"detail": "Task not found"})


# ---------------------------------------------------------------
# Fixtures (mirrored from test_per_user_scoping for parity)
# ---------------------------------------------------------------


@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str:
    db_file = tmp_path / "task_routes_test.db"
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
) -> Generator[FastAPI, None, None]:
    """Slim FastAPI app: auth + task routers driven via dep overrides.

    Phase 19 Plan 10: dependency_overrides[get_db] is the SOLE DB-binding
    seam. Auth + scope are owned by the new Depends graph. Fixture name
    kept as ``app_and_container`` for callsite stability across the
    refactor wave; the legacy container is gone.
    """
    limiter.reset()

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(InvalidCredentialsError, invalid_credentials_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.add_exception_handler(TaskNotFoundError, _task_not_found_handler)
    app.include_router(auth_router)
    app.include_router(task_router)

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


@pytest.fixture
def client(app_and_container: FastAPI) -> TestClient:
    return TestClient(app_and_container)


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------


def _register(client: TestClient, email: str, password: str = "supersecret123") -> int:
    response = client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert response.status_code == 201, response.text
    return int(response.json()["user_id"])


def _seed_task(
    session_factory,
    *,
    user_id: int,
    uuid: str,
    file_name: str,
    status: str = "completed",
    created_offset_seconds: int = 0,
) -> None:
    """Insert a task row owned by user_id with explicit timestamp ordering.

    ``created_offset_seconds`` lets tests force a deterministic
    ``created_at DESC`` ordering: lower offset = older row.
    """
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    created_at = base + timedelta(seconds=created_offset_seconds)
    with session_factory() as session:
        session.add(
            ORMTask(
                uuid=uuid,
                status=status,
                file_name=file_name,
                task_type="speech-to-text",
                user_id=user_id,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        session.commit()


# ---------------------------------------------------------------
# 1. Pagination respects user scope
# ---------------------------------------------------------------


@pytest.mark.integration
def test_pagination_respects_user_scope(
    client: TestClient, session_factory
) -> None:
    """User B's page 1 must NOT leak User A's tasks."""
    user_a = _register(client, "alice-page@example.com")
    for index in range(5):
        _seed_task(
            session_factory,
            user_id=user_a,
            uuid=f"alice-{index}",
            file_name=f"alice-{index}.mp3",
            created_offset_seconds=index,
        )

    client.cookies.clear()
    user_b = _register(client, "bob-page@example.com")
    for index in range(3):
        _seed_task(
            session_factory,
            user_id=user_b,
            uuid=f"bob-{index}",
            file_name=f"bob-{index}.mp3",
            created_offset_seconds=index,
        )

    resp = client.get("/task/all?page=1&page_size=10")
    assert resp.status_code == 200
    body = resp.json()
    uuids = {task["identifier"] for task in body["tasks"]}
    assert uuids == {"bob-0", "bob-1", "bob-2"}
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 10


# ---------------------------------------------------------------
# 2. q substring match — case-insensitive
# ---------------------------------------------------------------


@pytest.mark.integration
def test_q_matches_file_name_substring_case_insensitive(
    client: TestClient, session_factory
) -> None:
    user_id = _register(client, "carol-q@example.com")
    _seed_task(session_factory, user_id=user_id, uuid="t-1", file_name="Meeting.mp3")
    _seed_task(session_factory, user_id=user_id, uuid="t-2", file_name="podcast.wav")
    _seed_task(session_factory, user_id=user_id, uuid="t-3", file_name="MEETING-2.mp3")

    resp = client.get("/task/all?q=meeting")
    assert resp.status_code == 200
    body = resp.json()
    uuids = {task["identifier"] for task in body["tasks"]}
    assert uuids == {"t-1", "t-3"}
    assert body["total"] == 2


# ---------------------------------------------------------------
# 3. status filter
# ---------------------------------------------------------------


@pytest.mark.integration
def test_status_filter_narrows_to_one_bucket(
    client: TestClient, session_factory
) -> None:
    user_id = _register(client, "dave-status@example.com")
    _seed_task(
        session_factory,
        user_id=user_id,
        uuid="proc-1",
        file_name="a.mp3",
        status="processing",
    )
    _seed_task(
        session_factory,
        user_id=user_id,
        uuid="done-1",
        file_name="b.mp3",
        status="completed",
    )
    _seed_task(
        session_factory,
        user_id=user_id,
        uuid="fail-1",
        file_name="c.mp3",
        status="failed",
    )

    resp = client.get("/task/all?status=processing")
    assert resp.status_code == 200
    body = resp.json()
    uuids = {task["identifier"] for task in body["tasks"]}
    assert uuids == {"proc-1"}
    assert body["total"] == 1


# ---------------------------------------------------------------
# 4. Bounds — page<1 -> 422
# ---------------------------------------------------------------


@pytest.mark.integration
def test_page_below_one_returns_422(client: TestClient) -> None:
    _register(client, "eve-bounds@example.com")
    resp = client.get("/task/all?page=0")
    assert resp.status_code == 422


@pytest.mark.integration
def test_page_size_above_200_returns_422(client: TestClient) -> None:
    _register(client, "frank-bounds@example.com")
    resp = client.get("/task/all?page_size=201")
    assert resp.status_code == 422


@pytest.mark.integration
def test_page_size_below_one_returns_422(client: TestClient) -> None:
    _register(client, "grace-bounds@example.com")
    resp = client.get("/task/all?page_size=0")
    assert resp.status_code == 422


# ---------------------------------------------------------------
# 5. Empty result — total=0
# ---------------------------------------------------------------


@pytest.mark.integration
def test_empty_result_returns_total_zero(client: TestClient) -> None:
    _register(client, "henry-empty@example.com")
    resp = client.get("/task/all")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tasks"] == []
    assert body["total"] == 0
    assert body["page"] == 1
    assert body["page_size"] == 50


# ---------------------------------------------------------------
# 6. total reflects filtered count, not the page slice
# ---------------------------------------------------------------


@pytest.mark.integration
def test_total_reflects_filtered_count_not_slice(
    client: TestClient, session_factory
) -> None:
    user_id = _register(client, "ivy-total@example.com")
    for index in range(7):
        _seed_task(
            session_factory,
            user_id=user_id,
            uuid=f"ivy-{index}",
            file_name=f"file-{index}.mp3",
            created_offset_seconds=index,
        )

    resp = client.get("/task/all?page=1&page_size=3")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["tasks"]) == 3
    assert body["total"] == 7


# ---------------------------------------------------------------
# 7. Order is created_at DESC (newest first)
# ---------------------------------------------------------------


@pytest.mark.integration
def test_newest_tasks_returned_first(
    client: TestClient, session_factory
) -> None:
    user_id = _register(client, "jack-order@example.com")
    _seed_task(
        session_factory,
        user_id=user_id,
        uuid="oldest",
        file_name="old.mp3",
        created_offset_seconds=0,
    )
    _seed_task(
        session_factory,
        user_id=user_id,
        uuid="middle",
        file_name="mid.mp3",
        created_offset_seconds=60,
    )
    _seed_task(
        session_factory,
        user_id=user_id,
        uuid="newest",
        file_name="new.mp3",
        created_offset_seconds=120,
    )

    resp = client.get("/task/all?page=1&page_size=10")
    assert resp.status_code == 200
    identifiers = [task["identifier"] for task in resp.json()["tasks"]]
    assert identifiers == ["newest", "middle", "oldest"]


# ---------------------------------------------------------------
# 8. Page 2 returns next slice
# ---------------------------------------------------------------


@pytest.mark.integration
def test_page_two_returns_next_slice(
    client: TestClient, session_factory
) -> None:
    user_id = _register(client, "kate-pageturn@example.com")
    for index in range(5):
        _seed_task(
            session_factory,
            user_id=user_id,
            uuid=f"k-{index}",
            file_name=f"k-{index}.mp3",
            created_offset_seconds=index,
        )

    resp = client.get("/task/all?page=2&page_size=2")
    assert resp.status_code == 200
    body = resp.json()
    # Order: k-4 (newest), k-3, k-2, k-1, k-0 (oldest)
    # page=1 size=2 -> [k-4, k-3]; page=2 size=2 -> [k-2, k-1]
    identifiers = [task["identifier"] for task in body["tasks"]]
    assert identifiers == ["k-2", "k-1"]
    assert body["total"] == 5
    assert body["page"] == 2
