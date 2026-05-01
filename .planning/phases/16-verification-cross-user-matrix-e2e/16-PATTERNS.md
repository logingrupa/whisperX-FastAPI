# Phase 16: Verification + Cross-User Matrix + E2E — Pattern Map

**Mapped:** 2026-04-29
**Files analyzed:** 6 new test files
**Analogs found:** 6 / 6

---

## File Classification

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `tests/integration/_phase16_helpers.py` | utility/shared | CRUD + transform | `test_account_routes.py` + `test_ws_ticket_flow.py` | exact |
| `tests/integration/test_security_matrix.py` | test (parametrized) | request-response | `test_per_user_scoping.py` + `test_account_routes.py` | exact |
| `tests/integration/test_jwt_attacks.py` | test (negative path) | request-response | `test_auth_routes.py` + `app/core/jwt_codec.py` | role-match |
| `tests/integration/test_csrf_enforcement.py` | test (negative path) | request-response | `test_auth_routes.py` (auth_full_app fixture) | exact |
| `tests/integration/test_ws_ticket_safety.py` | test (WS) | event-driven | `test_ws_ticket_flow.py` | exact |
| `tests/integration/test_migration_smoke.py` | test (subprocess) | batch | `test_alembic_migration.py` | exact |

---

## Pattern Assignments

### `tests/integration/_phase16_helpers.py` (utility, CRUD + transform)

**Analogs:** `test_account_routes.py`, `test_ws_ticket_flow.py`, `test_per_user_scoping.py`

**Purpose:** Single DRY module; all five test files import from here. Exports:
- `_seed_two_users(app, session_factory)` → `(client_a, user_a_id, client_b, user_b_id)`
- `_endpoint_catalog` — module-level list of `(method, url_template, body_or_none)`
- `_forge_alg_none_token(user_id, token_version)` → str
- `_tamper_jwt(token)` → str
- `_forge_expired_token(user_id, secret, token_version)` → str
- `_issue_csrf_pair(client)` → `(session_cookie, csrf_cookie)` captured from register response
- `WS_POLICY_VIOLATION = 1008`

**Imports pattern** — copy from `test_ws_ticket_flow.py` lines 1-51:
```python
from __future__ import annotations

import base64
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from dependency_injector import providers
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
from app.core.container import Container
from app.core.dual_auth import DualAuthMiddleware
from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import Base
from app.infrastructure.database.models import Task as ORMTask
```

**`_register` helper pattern** — identical across 4 analog files; canonical source `test_per_user_scoping.py` lines 134-140:
```python
def _register(client: TestClient, email: str, password: str = "supersecret123") -> int:
    """Register via /auth/register; cookie set on the jar; returns user_id."""
    response = client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert response.status_code == 201, response.text
    return int(response.json()["user_id"])
```

**`_insert_task` helper pattern** — source `test_per_user_scoping.py` lines 143-163:
```python
def _insert_task(
    session_factory, *, user_id: int, uuid: str | None = None, status: str = "pending"
) -> str:
    if uuid is None:
        uuid = f"uuid-u{user_id}-{datetime.now(timezone.utc).timestamp()}-{id(session_factory)}"
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
```

**`_seed_two_users` helper pattern** — NEW; synthesized from `test_account_routes.py` lines 319-321 (two-client pattern):
```python
def _seed_two_users(
    app: FastAPI, session_factory
) -> tuple[TestClient, int, TestClient, int]:
    """Create two independent TestClient instances with separate cookie jars."""
    client_a = TestClient(app)
    client_b = TestClient(app)
    user_a_id = _register(client_a, "user-a@example.com")
    user_b_id = _register(client_b, "user-b@example.com")
    return client_a, user_a_id, client_b, user_b_id
```

**JWT forgery helpers** — from RESEARCH.md §Pattern 3/4/5 (verified against `app/core/jwt_codec.py`):
```python
def _b64url(obj: dict | bytes) -> str:
    raw = obj if isinstance(obj, bytes) else json.dumps(obj, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

def _forge_alg_none_token(*, user_id: int, token_version: int = 0) -> str:
    header = {"alg": "none", "typ": "JWT"}
    now = int(time.time())
    payload = {
        "sub": str(user_id), "iat": now, "exp": now + 86400,
        "ver": token_version, "method": "session",
    }
    return f"{_b64url(header)}.{_b64url(payload)}."  # empty sig, trailing dot

def _tamper_jwt(token: str) -> str:
    head, payload, sig = token.split(".")
    flipped = "A" if sig[-1] != "A" else "B"
    return f"{head}.{payload}.{sig[:-1]}{flipped}"

def _forge_expired_token(*, user_id: int, secret: str, token_version: int = 0) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id), "iat": now - 86400, "exp": now - 3600,
        "ver": token_version, "method": "session",
    }
    return jwt.encode(payload, secret, algorithm="HS256")
```

**`WS_POLICY_VIOLATION` constant** — from `test_ws_ticket_flow.py` line 52:
```python
WS_POLICY_VIOLATION = 1008
```

---

### `tests/integration/test_security_matrix.py` (test, request-response, VERIFY-01)

**Analogs:** `test_per_user_scoping.py` (cross-user 404), `test_account_routes.py` (two-client pattern)

**Imports pattern** — copy `test_per_user_scoping.py` lines 26-59 plus add `pytest.mark.parametrize`:
```python
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
from app.api.exception_handlers import invalid_credentials_handler, validation_error_handler
from app.api.task_api import task_router
from app.api.account_routes import account_router
from app.api.ws_ticket_routes import ws_ticket_router
from app.core.container import Container
from app.core.dual_auth import DualAuthMiddleware
from app.core.csrf_middleware import CsrfMiddleware
from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import Base

from tests.integration._phase16_helpers import (
    _seed_two_users, _endpoint_catalog, _insert_task,
)
```

**Full-stack fixture pattern** — from RESEARCH.md §Pattern 1 (verified against `test_account_routes.py` lines 88-117 and RESEARCH.md lines 224-254):
```python
@pytest.fixture
def full_app(tmp_db_url: str, session_factory) -> Generator[tuple[FastAPI, Container], None, None]:
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
    app.include_router(account_router)
    app.include_router(ws_ticket_router)
    # ASGI reversal: register CsrfMiddleware BEFORE DualAuth so DualAuth runs first
    app.add_middleware(CsrfMiddleware, container=container)
    app.add_middleware(DualAuthMiddleware, container=container)

    yield app, container

    container.unwire()
    container.db_session_factory.reset_override()
    limiter.reset()
```

**Parametrize pattern** — synthesized from `test_per_user_scoping.py` cross-user tests:
```python
_ENDPOINT_CATALOG = [
    ("GET",    "/task/all",              None),
    ("GET",    "/task/{task_id}",        None),
    ("DELETE", "/task/{task_id}/delete", None),
    ("GET",    "/tasks/{task_id}/progress", None),
    ("POST",   "/api/ws/ticket",         lambda tid: {"task_id": tid}),
    ("GET",    "/api/account/me",        None),
    # Add further endpoints per CONTEXT.md list
]

@pytest.mark.parametrize("method,url_tmpl,body_fn", _ENDPOINT_CATALOG)
@pytest.mark.integration
def test_foreign_user_gets_404_or_403(
    full_app: tuple[FastAPI, Container],
    session_factory,
    method: str,
    url_tmpl: str,
    body_fn,
) -> None:
    app, _ = full_app
    client_a, user_a_id, client_b, _ = _seed_two_users(app, session_factory)
    task_uuid = _insert_task(session_factory, user_id=user_a_id)
    url = url_tmpl.format(task_id=task_uuid)
    body = body_fn(task_uuid) if body_fn else None

    response = client_b.request(method, url, json=body)

    assert response.status_code in {403, 404}, (
        f"{method} {url} — expected 403/404 for foreign user, got {response.status_code}: {response.text}"
    )
```

**Anti-enumeration parity pattern** — from `test_per_user_scoping.py` lines 439-459:
```python
# Both unknown-id and foreign-id must produce IDENTICAL 404 body
cross = client_b.get(f"/task/{task_uuid}")
unknown = client_b.get("/task/uuid-does-not-exist")
assert cross.status_code == 404
assert unknown.status_code == 404
assert cross.json() == unknown.json()  # opaque shape parity
```

---

### `tests/integration/test_jwt_attacks.py` (test, request-response, VERIFY-02..04)

**Analog:** `test_auth_routes.py` (auth_full_app fixture, lines 127-159)

**Imports pattern** — auth_full_app fixture + jwt helpers:
```python
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.container import Container

from tests.integration._phase16_helpers import (
    _register,
    _forge_alg_none_token,
    _tamper_jwt,
    _forge_expired_token,
)
```

**auth_full_app fixture reuse** — copy verbatim from `test_auth_routes.py` lines 127-159; add key_router if needed. The fixture yields `(app, container)` — extract JWT secret from `container.settings().auth.jwt_secret`.

**Core attack test pattern** — VERIFY-02 (alg=none):
```python
@pytest.mark.integration
def test_alg_none_token_rejected_via_bearer(
    auth_full_app: tuple[FastAPI, Container],
) -> None:
    """alg=none token sent as Authorization: Bearer → 401 on every protected route."""
    app, container = auth_full_app
    client = TestClient(app)
    user_id = _register(client, "attacker@example.com")
    forged_token = _forge_alg_none_token(user_id=user_id, token_version=0)

    client.cookies.clear()
    response = client.post(
        "/auth/logout-all",
        headers={"Authorization": f"Bearer {forged_token}"},
    )
    assert response.status_code == 401, response.text
```

**Cookie path variant** — VERIFY-02 dual-path:
```python
@pytest.mark.integration
def test_alg_none_token_rejected_via_session_cookie(
    auth_full_app: tuple[FastAPI, Container],
) -> None:
    app, container = auth_full_app
    client = TestClient(app)
    user_id = _register(client, "attacker-cookie@example.com")
    forged_token = _forge_alg_none_token(user_id=user_id, token_version=0)

    client.cookies.clear()
    client.cookies.set("session", forged_token)
    response = client.post("/auth/logout-all")
    assert response.status_code == 401, response.text
```

**Expired token pattern** — VERIFY-04; needs secret from container:
```python
@pytest.mark.integration
def test_expired_token_rejected(auth_full_app: tuple[FastAPI, Container]) -> None:
    app, container = auth_full_app
    client = TestClient(app)
    user_id = _register(client, "expired@example.com")
    secret = container.settings().auth.jwt_secret
    expired_token = _forge_expired_token(user_id=user_id, secret=secret, token_version=0)

    client.cookies.clear()
    response = client.post(
        "/auth/logout-all",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401, response.text
```

---

### `tests/integration/test_csrf_enforcement.py` (test, request-response, VERIFY-06)

**Analog:** `test_auth_routes.py` — auth_full_app fixture + cookie capture from register

**Cookie capture pattern** — from RESEARCH.md §Pattern (verified against `test_auth_routes.py` lines 186-201):
```python
# After register, TestClient jar holds both cookies
user_id = _register(client, "csrf-test@example.com")
csrf_token = client.cookies.get("csrf_token")
assert csrf_token is not None
```

**CSRF missing header → 403 pattern**:
```python
@pytest.mark.integration
def test_csrf_missing_header_returns_403(auth_full_app: tuple[FastAPI, Container]) -> None:
    """Cookie-auth POST without X-CSRF-Token → 403 'CSRF token missing'."""
    app, _ = auth_full_app
    client = TestClient(app)
    _register(client, "csrf-missing@example.com")

    # Send state-mutating request with no X-CSRF-Token header
    response = client.post("/auth/logout-all")  # cookie attached automatically

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "CSRF token missing"
```

**CSRF mismatch → 403 pattern**:
```python
@pytest.mark.integration
def test_csrf_mismatched_header_returns_403(auth_full_app: tuple[FastAPI, Container]) -> None:
    """X-CSRF-Token != csrf_token cookie → 403 'CSRF token mismatch'."""
    app, _ = auth_full_app
    client = TestClient(app)
    _register(client, "csrf-mismatch@example.com")

    response = client.post(
        "/auth/logout-all",
        headers={"X-CSRF-Token": "definitely-wrong-token"},
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "CSRF token mismatch"
```

**CSRF matching → success pattern**:
```python
@pytest.mark.integration
def test_csrf_matching_header_succeeds(auth_full_app: tuple[FastAPI, Container]) -> None:
    """Matching X-CSRF-Token → request passes through (204)."""
    app, _ = auth_full_app
    client = TestClient(app)
    _register(client, "csrf-ok@example.com")
    csrf_token = client.cookies.get("csrf_token")

    response = client.post(
        "/auth/logout-all",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 204, response.text
```

**Bearer auth skips CSRF pattern** — from RESEARCH.md §CSRF strategy:
```python
@pytest.mark.integration
def test_bearer_auth_skips_csrf_check(auth_full_app: tuple[FastAPI, Container]) -> None:
    """Bearer-auth POST with no X-CSRF-Token still succeeds (middleware bypasses)."""
    # Bearer auth → request.state.auth_method == 'bearer' → CsrfMiddleware skips
    # Acquire API key via key_router, then call protected route without CSRF header
    ...  # exact endpoint depends on which router is mounted; pattern is bearer header = skip
```

**Middleware order — CRITICAL** (from `app/core/csrf_middleware.py` + RESEARCH.md Pitfall 3):
```python
# ASGI middleware reversal: register CsrfMiddleware FIRST so it runs SECOND
app.add_middleware(CsrfMiddleware, container=container)   # runs second on dispatch
app.add_middleware(DualAuthMiddleware, container=container)  # runs first on dispatch
```

---

### `tests/integration/test_ws_ticket_safety.py` (test, event-driven, VERIFY-07)

**Analog:** `test_ws_ticket_flow.py` — EXACT template; copy `ws_app` fixture, `_close_code_from_disconnect`, `WS_POLICY_VIOLATION`

**ws_app fixture** — copy verbatim from `test_ws_ticket_flow.py` lines 79-113:
```python
@pytest.fixture
def ws_app(
    tmp_db_url: str, session_factory
) -> Generator[tuple[FastAPI, Container], None, None]:
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
```

**Cross-user ticket pattern** — from `test_ws_ticket_flow.py` lines 206-219 (anti-enum + ticket isolation):
```python
@pytest.mark.integration
def test_ws_ticket_cross_user_task_close_1008(
    client: TestClient, session_factory
) -> None:
    """Ticket issued for User A's task; User B's WS connection → close 1008."""
    user_a = _register(client, "ticket-a@example.com")
    task_uuid = _insert_task(session_factory, user_id=user_a)
    ticket = client.post("/api/ws/ticket", json={"task_id": task_uuid}).json()["ticket"]

    # Switch to user B
    client.cookies.clear()
    _register(client, "ticket-b@example.com")
    # User B cannot issue ticket (404) but even if ticket token leaked:
    # WS endpoint verifies ticket.user_id == connection identity
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/tasks/{task_uuid}?ticket={ticket}"):
            pass
    assert _close_code_from_disconnect(exc_info.value) == WS_POLICY_VIOLATION
```

**Expired ticket pattern** — copy verbatim from `test_ws_ticket_flow.py` lines 295-328:
```python
@pytest.mark.integration
def test_ws_reject_expired_ticket(
    client: TestClient, session_factory, monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = _register(client, "expired-ticket@example.com")
    task_uuid = _insert_task(session_factory, user_id=user_id)
    ticket = client.post("/api/ws/ticket", json={"task_id": task_uuid}).json()["ticket"]

    real_now = datetime.now(timezone.utc)
    fake_now = real_now + timedelta(seconds=120)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fake_now

    monkeypatch.setattr("app.services.ws_ticket_service.datetime", _FrozenDatetime)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/tasks/{task_uuid}?ticket={ticket}"):
            pass
    assert _close_code_from_disconnect(exc_info.value) == WS_POLICY_VIOLATION
```

**Reuse pattern** — from `test_ws_ticket_flow.py` lines 268-292:
```python
# Second connect with same ticket → 1008
with client.websocket_connect(f"/ws/tasks/{task_uuid}?ticket={ticket}") as ws:
    ws.send_json({"type": "ping"})
    assert ws.receive_json() == {"type": "pong"}
# ticket consumed — second attempt must 1008
with pytest.raises(WebSocketDisconnect) as exc_info:
    with client.websocket_connect(f"/ws/tasks/{task_uuid}?ticket={ticket}"):
        pass
assert _close_code_from_disconnect(exc_info.value) == WS_POLICY_VIOLATION
```

---

### `tests/integration/test_migration_smoke.py` (test, batch, VERIFY-08)

**Analog:** `test_alembic_migration.py` — EXACT template for `_run_alembic`, `_make_engine`, `_build_tasks_table`

**Imports pattern** — from `test_alembic_migration.py` lines 1-31:
```python
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

REPO_ROOT = Path(__file__).resolve().parents[2]
```

**`_run_alembic` helper** — copy verbatim from `test_alembic_migration.py` lines 34-53:
```python
def _run_alembic(args: list[str], db_url: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DB_URL"] = db_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
```

**`_make_engine` helper** — copy verbatim from `test_alembic_migration.py` lines 56-61:
```python
def _make_engine(db_path: Path):
    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
```

**`_build_legacy_tasks_table` helper** — adapted from `test_alembic_migration.py` lines 64-86; VERIFY-08 needs synthetic v1.1 baseline (tasks table without user_id) + a seeded tasks row:
```python
def _build_v11_baseline(db_path: Path, *, n_tasks: int = 3) -> None:
    """Create pre-Phase-10 tasks table (no user_id col) + n orphan tasks rows."""
    engine = _make_engine(db_path)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE tasks ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  uuid TEXT, status TEXT, result TEXT, file_name TEXT,"
            "  url TEXT, callback_url TEXT, audio_duration REAL,"
            "  language TEXT, task_type TEXT, task_params TEXT,"
            "  duration REAL, start_time TEXT, end_time TEXT, error TEXT,"
            "  created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,"
            "  progress_percentage INTEGER DEFAULT 0, progress_stage TEXT"
            ")"
        )
        for i in range(n_tasks):
            conn.exec_driver_sql(
                "INSERT INTO tasks (uuid, status, task_type, created_at, updated_at) "
                "VALUES (?, 'pending', 'speech-to-text', "
                "'2026-01-01 00:00:00', '2026-01-01 00:00:00')",
                (f"legacy-task-{i}",),
            )
    engine.dispose()
```

**Core smoke test pattern**:
```python
@pytest.mark.integration
def test_migration_smoke_brownfield_preserves_rows_and_adds_user_id(
    tmp_path: Path,
) -> None:
    """Baseline → upgrade head: tasks rows preserved, user_id col added."""
    db_path = tmp_path / "smoke.db"
    _build_v11_baseline(db_path, n_tasks=3)
    db_url = f"sqlite:///{db_path}"
    _run_alembic(["stamp", "0001_baseline"], db_url)
    _run_alembic(["upgrade", "head"], db_url)

    engine = _make_engine(db_path)
    with engine.connect() as conn:
        row_count = conn.exec_driver_sql("SELECT COUNT(*) FROM tasks").scalar()
        cols = {c["name"] for c in inspect(engine).get_columns("tasks")}
    engine.dispose()

    assert row_count == 3, f"row count changed; got {row_count}"
    assert "user_id" in cols, f"tasks.user_id missing; cols={cols}"
```

**Row ownership assertion pattern** — from CONTEXT.md VERIFY-08 spec:
```python
    # user_id may be NULL (orphan) after backfill if no admin seeded.
    # VERIFY-08 asserts IS NOT NULL only when migration seeds an admin user.
    with engine.connect() as conn:
        null_count = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM tasks WHERE user_id IS NULL"
        ).scalar()
    assert null_count == 0, f"{null_count} tasks still have NULL user_id post-upgrade"
```

---

## Shared Patterns

### Full-stack Slim App Fixture
**Source:** `test_account_routes.py` lines 88-117, `test_auth_routes.py` lines 127-159
**Apply to:** `test_security_matrix.py`, `test_jwt_attacks.py`, `test_csrf_enforcement.py`

Core structure (ASGI middleware order is CRITICAL):
```python
# Register CsrfMiddleware BEFORE DualAuthMiddleware so dispatch order is:
#   request → DualAuthMiddleware → CsrfMiddleware → route
app.add_middleware(CsrfMiddleware, container=container)   # registered first → runs second
app.add_middleware(DualAuthMiddleware, container=container)  # registered second → runs first
```

### Container Override Pattern
**Source:** `test_auth_routes.py` lines 83-110, `test_per_user_scoping.py` lines 99-122
**Apply to:** all 5 new test files (except migration smoke)
```python
container = Container()
container.db_session_factory.override(providers.Factory(session_factory))
dependencies.set_container(container)
# ... teardown:
container.unwire()
container.db_session_factory.reset_override()
```

### Limiter Reset (both setup AND teardown)
**Source:** `test_account_routes.py` lines 97 + 111; `test_auth_routes.py` lines 96 + 110
**Apply to:** all 5 new test files using slim-app fixtures
```python
# In fixture body:
limiter.reset()
# ... yield ...
# In fixture teardown:
limiter.reset()
```

### Two-Client Cross-User Setup
**Source:** `test_account_routes.py` lines 319-321
**Apply to:** `test_security_matrix.py`, `test_ws_ticket_safety.py`
```python
client_a = TestClient(app)
client_b = TestClient(app)
user_a_id = _register(client_a, "alice@example.com")
user_b_id = _register(client_b, "bob@example.com")
# Each jar independent; no cookies.clear() needed between A and B ops
```

### TaskNotFoundError Handler (required for task routes)
**Source:** `test_per_user_scoping.py` lines 67-70
**Apply to:** any fixture that mounts `task_router`
```python
async def _task_not_found_handler(_request, exc: TaskNotFoundError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=404, content={"detail": "Task not found"})
# ... in fixture:
app.add_exception_handler(TaskNotFoundError, _task_not_found_handler)
```

### `@pytest.mark.integration` Marker
**Source:** all existing integration tests
**Apply to:** all test functions in all 5 new files

### DB tmp_db_url + session_factory Fixture Pair
**Source:** `test_auth_routes.py` lines 65-75 + 120-123
**Apply to:** all 5 new test files
```python
@pytest.fixture
def tmp_db_url(tmp_path: Path) -> str:
    db_file = tmp_path / "test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    engine.dispose()
    return url

@pytest.fixture
def session_factory(tmp_db_url: str):
    engine = create_engine(tmp_db_url, connect_args={"check_same_thread": False})
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

### WS `_close_code_from_disconnect`
**Source:** `test_ws_ticket_flow.py` lines 165-167
**Apply to:** `test_ws_ticket_safety.py`
```python
def _close_code_from_disconnect(exc: WebSocketDisconnect) -> int:
    return int(exc.code)
```

---

## No Analog Found

None. All 6 files have direct analogs in the codebase.

---

## Critical Anti-Patterns (from RESEARCH.md — do NOT do)

| Anti-Pattern | Why | Correct Pattern |
|---|---|---|
| `Base.metadata.create_all` in migration smoke | Bypasses alembic — tests wrong thing | Only `_run_alembic(["upgrade", "head"], db_url)` |
| Single TestClient for both users | Cookie jar collision masks isolation bugs | Two `TestClient(app)` instances |
| `time.monotonic` mock for WS expiry | `WsTicketService.consume` uses `datetime.now` | `_FrozenDatetime` monkeypatch on `app.services.ws_ticket_service.datetime` |
| `jwt.encode({"alg":"none"})` via PyJWT | PyJWT 2.x refuses | Direct base64 construction (`_forge_alg_none_token`) |
| DualAuth registered BEFORE Csrf | Csrf runs before auth_method set → bypasses | Register Csrf FIRST so it runs SECOND |
| `limiter.reset()` only in teardown | Previous test's 3/hr bucket poisons next | Reset in BOTH setup and teardown |
| `alg=None` (capital N) | RFC 7519 requires lowercase `none` | Use `"alg": "none"` |

---

## Metadata

**Analog search scope:** `tests/integration/` (20 files scanned), `app/core/`, `app/services/auth/`
**Files read:** 9 source files + RESEARCH.md + CONTEXT.md
**Pattern extraction date:** 2026-04-29
