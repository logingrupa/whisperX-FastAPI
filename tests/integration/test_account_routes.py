"""Integration tests for Phase 13 ``/api/account/*`` routes.

Coverage (≥6 cases per plan 13-05):

1. test_delete_user_data_removes_tasks — INSERT 3 tasks; DELETE; 0 remaining
2. test_delete_user_data_preserves_user_row — users row survives
3. test_delete_user_data_removes_uploaded_files — UPLOAD_DIR + tus dir cleaned
4. test_delete_user_data_skips_missing_files — best-effort; 204 OK
5. test_delete_user_data_cross_user_isolation — A's data survives B's DELETE
6. test_delete_user_data_requires_auth — no auth → 401

Phase 19 Plan 10 fixture migration:
  - slim FastAPI app per test (auth_router + account_router only)
  - app.dependency_overrides[get_db] is the SOLE DB-binding seam — drives
    the production Depends(authenticated_user) + Depends(csrf_protected) chain
    through the tmp SQLite without any middleware stack.
  - DualAuthMiddleware + the legacy DI container are GONE — Plans 11-13
    delete those modules; this plan switches the fixture surface ahead of
    those deletions so the atomic-commit invariant holds (collection
    succeeds at every commit).
  - monkey-patches UPLOAD_DIR / TUS_UPLOAD_DIR on account_service module
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path

import pytest
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
) -> Generator[FastAPI, None, None]:
    """Slim FastAPI app: auth_router + account_router driven via dependency_overrides.

    Phase 19 Plan 10 fixture migration: ``app.dependency_overrides[get_db]``
    is the SOLE DB-binding seam. The production
    ``Depends(authenticated_user)`` + ``Depends(csrf_protected)`` chain on
    account_router resolves transitively against the tmp SQLite via the
    overridden ``get_db`` (FastAPI dep cache shares the Session across
    sub-deps in one request). DualAuthMiddleware mounting is gone — the new
    Depends graph owns auth resolution end-to-end (Plan 11 deletes the
    middleware module).
    """
    limiter.reset()

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(InvalidCredentialsError, invalid_credentials_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.include_router(auth_router)
    app.include_router(account_router)

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
def client(account_app: FastAPI) -> TestClient:
    return TestClient(account_app)


def _register(client: TestClient, email: str, password: str = "supersecret123") -> int:
    """Register a user via /auth/register; return the user_id.

    Phase 19 Plan 06 additive: account_router now applies router-level
    csrf_protected (Depends), so cookie-auth state-mutating calls (DELETE)
    require X-CSRF-Token. Stamp the csrf_token cookie value as a default
    header on the client after register so subsequent DELETEs pass the
    double-submit check; this preserves the legacy test bodies untouched.
    """
    response = client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    csrf = client.cookies.get("csrf_token")
    assert csrf is not None, "csrf_token cookie missing after /auth/register"
    client.headers["X-CSRF-Token"] = csrf
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


def _seed_full_user_universe(session_factory, *, user_id: int) -> None:
    """Seed one row per dependent table for cascade tests (Plan 15-04).

    Tables: tasks, api_keys, subscriptions, usage_events,
    device_fingerprints, rate_limit_buckets. Column lists locked at
    Phase 10/11 schema (verified against app/infrastructure/database/models.py).
    """
    seed_ts = datetime(2026, 4, 29, tzinfo=timezone.utc)
    with session_factory() as session:
        # tasks (FK SET NULL — must be deleted before user)
        session.execute(
            text(
                "INSERT INTO tasks (uuid, status, file_name, task_type, "
                "created_at, updated_at, user_id) "
                "VALUES (:uuid, 'pending', :fn, 'speech-to-text', "
                ":ts, :ts, :uid)"
            ),
            {
                "uuid": f"uuid-seed-{user_id}",
                "fn": f"seed-{user_id}.wav",
                "ts": seed_ts,
                "uid": user_id,
            },
        )
        # api_keys (FK CASCADE)
        session.execute(
            text(
                "INSERT INTO api_keys (user_id, name, prefix, hash, scopes, "
                "created_at, last_used_at, revoked_at) "
                "VALUES (:uid, 'seeded', :pfx, :h, 'transcribe', "
                ":ts, NULL, NULL)"
            ),
            {
                "uid": user_id,
                "pfx": f"pfx{user_id:04d}"[:8],
                "h": "deadbeef" * 8,
                "ts": seed_ts,
            },
        )
        # subscriptions (FK CASCADE)
        session.execute(
            text(
                "INSERT INTO subscriptions (user_id, plan, status, "
                "created_at, updated_at) "
                "VALUES (:uid, 'pro', 'active', :ts, :ts)"
            ),
            {"uid": user_id, "ts": seed_ts},
        )
        # usage_events (FK CASCADE)
        session.execute(
            text(
                "INSERT INTO usage_events (user_id, idempotency_key, "
                "gpu_seconds, file_seconds, model, created_at) "
                "VALUES (:uid, :idk, 1, 1, 'tiny', :ts)"
            ),
            {"uid": user_id, "idk": f"seed-{user_id}", "ts": seed_ts},
        )
        # device_fingerprints (FK CASCADE)
        session.execute(
            text(
                "INSERT INTO device_fingerprints (user_id, cookie_hash, "
                "ua_hash, ip_subnet, device_id, created_at) "
                "VALUES (:uid, :ck, :ua, :ip, :did, :ts)"
            ),
            {
                "uid": user_id,
                "ck": "c" * 64,
                "ua": "a" * 64,
                "ip": "10.0.0.0/24",
                "did": f"dev-{user_id}",
                "ts": seed_ts,
            },
        )
        # rate_limit_buckets (no FK — bucket_key prefix-match required)
        session.execute(
            text(
                "INSERT INTO rate_limit_buckets (bucket_key, tokens, "
                "last_refill) VALUES (:k, 5, :ts)"
            ),
            {"k": f"user:{user_id}:hour", "ts": seed_ts},
        )
        session.commit()


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
    account_app: FastAPI,
    session_factory,
    upload_dirs: tuple[Path, Path],
) -> None:
    """User B's DELETE only affects User B; User A's tasks survive."""
    app = account_app
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
    account_app: FastAPI,
) -> None:
    """DELETE without cookie/bearer → 401."""
    app = account_app
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
    account_app: FastAPI,
) -> None:
    """Anonymous GET → 401 with the same generic detail used elsewhere (T-15-04)."""
    app = account_app
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


# ---------------------------------------------------------------
# DELETE /api/account — Plan 15-04 (SCOPE-06 full-row delete + cascade)
# ---------------------------------------------------------------


@pytest.mark.integration
def test_delete_account_cascade_full_universe(
    client: TestClient, session_factory, upload_dirs: tuple[Path, Path]
) -> None:
    """DELETE /api/account cascades to all 6 dependent tables + removes user row."""
    user_id = _register(client, "cascade@example.com")
    _seed_full_user_universe(session_factory, user_id=user_id)

    response = client.request(
        "DELETE",
        "/api/account",
        json={"email_confirm": "cascade@example.com"},
    )

    assert response.status_code == 204, response.text
    with session_factory() as session:
        for table_with_fk in (
            "tasks",
            "api_keys",
            "subscriptions",
            "usage_events",
            "device_fingerprints",
        ):
            count = session.execute(
                text(f"SELECT COUNT(*) FROM {table_with_fk} WHERE user_id = :uid"),
                {"uid": user_id},
            ).scalar_one()
            assert count == 0, f"{table_with_fk} not cascaded"
        bucket_count = session.execute(
            text(
                "SELECT COUNT(*) FROM rate_limit_buckets "
                "WHERE bucket_key LIKE :pattern"
            ),
            {"pattern": f"user:{user_id}:%"},
        ).scalar_one()
        assert bucket_count == 0, "rate_limit_buckets not pre-deleted"
        user_count = session.execute(
            text("SELECT COUNT(*) FROM users WHERE id = :uid"),
            {"uid": user_id},
        ).scalar_one()
        assert user_count == 0, "users row not deleted"


@pytest.mark.integration
def test_delete_account_email_mismatch_400(
    client: TestClient, session_factory, upload_dirs: tuple[Path, Path]
) -> None:
    """Email mismatch returns 400 + EMAIL_CONFIRM_MISMATCH; data preserved."""
    user_id = _register(client, "mismatch@example.com")
    _seed_full_user_universe(session_factory, user_id=user_id)

    response = client.request(
        "DELETE",
        "/api/account",
        json={"email_confirm": "different@example.com"},
    )

    assert response.status_code == 400, response.text
    body = response.json()
    flattened = str(body)
    assert "EMAIL_CONFIRM_MISMATCH" in flattened
    # Data preserved on mismatch
    with session_factory() as session:
        user_count = session.execute(
            text("SELECT COUNT(*) FROM users WHERE id = :uid"),
            {"uid": user_id},
        ).scalar_one()
        assert user_count == 1
        task_count = session.execute(
            text("SELECT COUNT(*) FROM tasks WHERE user_id = :uid"),
            {"uid": user_id},
        ).scalar_one()
        assert task_count == 1


@pytest.mark.integration
def test_delete_account_email_case_insensitive(
    client: TestClient, session_factory, upload_dirs: tuple[Path, Path]
) -> None:
    """Case-insensitive email match: FOO@Example.COM matches foo@example.com."""
    user_id = _register(client, "case@example.com")
    _seed_full_user_universe(session_factory, user_id=user_id)

    response = client.request(
        "DELETE",
        "/api/account",
        json={"email_confirm": "CASE@Example.COM"},
    )

    assert response.status_code == 204, response.text
    with session_factory() as session:
        user_count = session.execute(
            text("SELECT COUNT(*) FROM users WHERE id = :uid"),
            {"uid": user_id},
        ).scalar_one()
        assert user_count == 0


@pytest.mark.integration
def test_delete_account_clears_cookies(
    client: TestClient, upload_dirs: tuple[Path, Path]
) -> None:
    """Successful DELETE clears session + csrf cookies (Max-Age=0, T-15-04)."""
    _register(client, "cookies@example.com")

    response = client.request(
        "DELETE",
        "/api/account",
        json={"email_confirm": "cookies@example.com"},
    )

    assert response.status_code == 204, response.text
    set_cookie_headers = response.headers.get_list("set-cookie")
    joined = "\n".join(set_cookie_headers).lower()
    assert "session=" in joined
    assert "csrf_token=" in joined
    assert joined.count("max-age=0") == 2


@pytest.mark.integration
def test_delete_account_requires_auth(
    account_app: FastAPI,
) -> None:
    """Anonymous DELETE → 401 'Authentication required'."""
    app = account_app
    anon = TestClient(app)

    response = anon.request(
        "DELETE",
        "/api/account",
        json={"email_confirm": "noone@example.com"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.integration
def test_delete_account_preserves_other_user_data(
    account_app: FastAPI,
    session_factory,
    upload_dirs: tuple[Path, Path],
) -> None:
    """Cross-user isolation smoke: Bob's data fully intact after Alice's delete."""
    app = account_app

    alice_client = TestClient(app)
    alice_id = _register(alice_client, "alice-iso@example.com")
    _seed_full_user_universe(session_factory, user_id=alice_id)

    bob_client = TestClient(app)
    bob_id = _register(bob_client, "bob-iso@example.com")
    _seed_full_user_universe(session_factory, user_id=bob_id)

    response = alice_client.request(
        "DELETE",
        "/api/account",
        json={"email_confirm": "alice-iso@example.com"},
    )
    assert response.status_code == 204, response.text

    with session_factory() as session:
        for table in (
            "tasks",
            "api_keys",
            "subscriptions",
            "usage_events",
            "device_fingerprints",
        ):
            count = session.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE user_id = :uid"),
                {"uid": bob_id},
            ).scalar_one()
            assert count == 1, f"Bob lost data in {table}"
        bob_buckets = session.execute(
            text(
                "SELECT COUNT(*) FROM rate_limit_buckets "
                "WHERE bucket_key LIKE :pattern"
            ),
            {"pattern": f"user:{bob_id}:%"},
        ).scalar_one()
        assert bob_buckets == 1


@pytest.mark.integration
def test_delete_account_no_body_returns_422(
    client: TestClient, upload_dirs: tuple[Path, Path]
) -> None:
    """Missing body → 422 (Pydantic field-required for email_confirm)."""
    _register(client, "nobody@example.com")

    response = client.delete("/api/account")

    assert response.status_code == 422
