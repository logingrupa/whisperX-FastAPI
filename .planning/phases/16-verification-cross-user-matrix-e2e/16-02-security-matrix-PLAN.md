---
phase: 16
plan: 02
type: execute
wave: 1
depends_on: [16-01]
files_modified:
  - tests/integration/test_security_matrix.py
autonomous: true
requirements: [VERIFY-01]
tags: [verification, cross-user, anti-enumeration, parametrize, security-matrix]
must_haves:
  truths:
    - "User B receives 404 (or 204 for self-only delete /api/account/data) on every task-touching endpoint accessing User A's resources"
    - "Foreign-id 404 body bytewise-identical to unknown-id 404 body (anti-enumeration parity)"
    - "User A receives positive-control 200/204 on the same endpoints accessing own resources"
    - "Two TestClient instances; separate cookie jars; same FastAPI app + DB"
    - "Endpoint catalog imported from _phase16_helpers — single source"
  artifacts:
    - path: "tests/integration/test_security_matrix.py"
      provides: "VERIFY-01 cross-user matrix; ≥16 parametrized cases (8 endpoints × {self, foreign})"
      min_lines: 200
      contains: "ENDPOINT_CATALOG"
  key_links:
    - from: "tests/integration/test_security_matrix.py"
      to: "tests/integration/_phase16_helpers.py"
      via: "from tests.integration._phase16_helpers import ENDPOINT_CATALOG, _seed_two_users, _insert_task"
      pattern: "from tests.integration._phase16_helpers import"
    - from: "test_security_matrix.full_app fixture"
      to: "DualAuthMiddleware + CsrfMiddleware"
      via: "ASGI middleware stack registration order: CSRF first, DualAuth second"
      pattern: "add_middleware\\(CsrfMiddleware.*\\n.*add_middleware\\(DualAuthMiddleware"
---

<objective>
Implement VERIFY-01 cross-user matrix. Caveman: parametrize over 8 endpoints × {self, foreign} → 16+ cases. Two TestClients, same app, same DB. Foreign-leg expected status from ENDPOINT_CATALOG; self-leg confirms positive control.

Purpose: prove user A's tasks/keys/usage never visible to user B for any task-touching endpoint — the milestone-gate invariant.
Output: tests/integration/test_security_matrix.py (~250 lines).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/16-verification-cross-user-matrix-e2e/16-CONTEXT.md
@.planning/phases/16-verification-cross-user-matrix-e2e/16-RESEARCH.md
@.planning/phases/16-verification-cross-user-matrix-e2e/16-PATTERNS.md

@tests/integration/test_account_routes.py
@tests/integration/test_per_user_scoping.py
@tests/integration/_phase16_helpers.py
@app/api/task_api.py
@app/api/key_routes.py
@app/api/account_routes.py
@app/api/ws_ticket_routes.py
@app/core/dual_auth.py
@app/core/csrf_middleware.py

<interfaces>
<!-- Imported from Plan 16-01: ENDPOINT_CATALOG, _seed_two_users, _register, _insert_task -->
<!-- Imported from app: routers + middleware + Container + exception handlers -->

```python
# From _phase16_helpers
ENDPOINT_CATALOG: list[tuple[str, str, int, bool]]
def _seed_two_users(client_a, client_b) -> tuple[int, int]
def _register(client, email, password=...) -> int
def _insert_task(session_factory, *, user_id, file_name=...) -> str

# Routers needed in slim app
from app.api.auth_routes import auth_router
from app.api.task_api import task_router
from app.api.key_routes import key_router
from app.api.account_routes import account_router
from app.api.ws_ticket_routes import ws_ticket_router

# Middleware
from app.core.dual_auth import DualAuthMiddleware
from app.core.csrf_middleware import CsrfMiddleware
```

ASGI middleware order (CRITICAL — Pitfall 3): registration is REVERSED on dispatch.
Register CSRF FIRST in code → it runs SECOND on dispatch → DualAuth runs FIRST → request.state.auth_method set before CSRF reads it.
</interfaces>
</context>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| client_b → /task/{owned-by-A} | B forges resource id of A; must surface 404 with byte-identical body to unknown-id 404 |
| state-mutating route → CsrfMiddleware | DELETE/POST require X-CSRF-Token header from cookie |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-16-01 | Information Disclosure | cross-user resource enumeration | mitigate | Two TestClient instances + cookies.clear-free isolation; assert response.json() body parity between unknown-id and foreign-id legs |
| T-16-04 | Tampering | rate-limit poisoning between tests | mitigate | limiter.reset() in fixture setup AND teardown |
| T-16-07 | Spoofing | matching-CSRF bypass on GET | accept | catalog only marks state-mutating endpoints requires_csrf=True; self-leg sends X-CSRF-Token from cookie when required; GET endpoints never need it |
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Build full_app fixture + helpers (DRY) for cross-user matrix</name>
  <files>tests/integration/test_security_matrix.py</files>
  <read_first>
    - tests/integration/test_account_routes.py lines 1-130 (slim app fixture pattern, ASGI middleware order, exception handlers)
    - tests/integration/test_per_user_scoping.py lines 1-122 (TaskNotFoundError handler, container override, session_factory fixture)
    - tests/integration/_phase16_helpers.py (full file)
    - app/core/exceptions.py — TaskNotFoundError import path
    - .planning/phases/16-verification-cross-user-matrix-e2e/16-PATTERNS.md §test_security_matrix.py section
  </read_first>
  <action>
Create file with module docstring: "VERIFY-01 cross-user matrix. Parametrized 8 endpoints × {self, foreign}. Two TestClient instances, same app + DB."

Imports (alphabetized stdlib/third-party/local):
```python
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
```

Define `_task_not_found_handler(request, exc)` — returns `JSONResponse(status_code=404, content={"detail": "Task not found"})`. (Pattern from test_per_user_scoping.py:67-70.)

Fixtures (all module-private; per-test):
- `tmp_db_url(tmp_path) -> str` — copy from test_ws_ticket_flow.py:60-68 (file SQLite, Base.metadata.create_all, dispose engine).
- `session_factory(tmp_db_url) -> sessionmaker` — copy from test_ws_ticket_flow.py:71-75.
- `full_app(tmp_db_url, session_factory) -> Generator[tuple[FastAPI, Container], None, None]`:
  - Container(); container.db_session_factory.override(providers.Factory(session_factory)); dependencies.set_container(container); limiter.reset()
  - app = FastAPI(); app.state.limiter = limiter
  - 4 exception handlers: RateLimitExceeded → rate_limit_handler, InvalidCredentialsError → invalid_credentials_handler, ValidationError → validation_error_handler, TaskNotFoundError → _task_not_found_handler
  - Routers: auth, task, key, account, ws_ticket
  - Middleware (ORDER LOCKED — register CsrfMiddleware FIRST so DualAuth runs FIRST on dispatch): `app.add_middleware(CsrfMiddleware, container=container); app.add_middleware(DualAuthMiddleware, container=container)`
  - yield (app, container)
  - Teardown: container.unwire(); container.db_session_factory.reset_override(); limiter.reset()

Helper `_create_key(client) -> str` (returns key_id):
- POST /api/keys with json={"name": "test-key"} and X-CSRF-Token header from client.cookies["csrf_token"]
- assert 201
- return response.json()["id"]

Helper `_seed_resources(app, session_factory) -> tuple[TestClient, TestClient, dict]`:
- client_a = TestClient(app); client_b = TestClient(app)
- user_a_id, _ = _seed_two_users(client_a, client_b)
- task_uuid = _insert_task(session_factory, user_id=user_a_id)
- key_id = _create_key(client_a)  # owned by A
- return client_a, client_b, {"task_uuid": task_uuid, "key_id": key_id}

No nested-if. Self-explanatory names (no `c1`, `c2`, `t1`).
  </action>
  <verify>
    <automated>cd /c/laragon/www/whisperx && uv run pytest tests/integration/test_security_matrix.py --collect-only -q 2>&1 | head -40</automated>
  </verify>
  <done>
    - File exists with all imports resolving
    - full_app fixture wires Container, 4 exception handlers, 5 routers, 2 middleware in correct registration order
    - _seed_resources helper returns 2 clients + dict of resource ids
    - pytest --collect-only succeeds (no syntax errors)
  </done>
  <acceptance_criteria>
    - `grep -c "add_middleware(CsrfMiddleware" tests/integration/test_security_matrix.py` == 1
    - `grep -c "add_middleware(DualAuthMiddleware" tests/integration/test_security_matrix.py` == 1
    - `grep -nE "add_middleware\\(CsrfMiddleware|add_middleware\\(DualAuthMiddleware" tests/integration/test_security_matrix.py` shows CSRF line BEFORE DualAuth line (Pitfall 3)
    - `grep -c "limiter.reset()" tests/integration/test_security_matrix.py` >= 2
    - `grep -c "from tests.integration._phase16_helpers import" tests/integration/test_security_matrix.py` == 1
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 2: Parametrized cross-user matrix tests (foreign + self legs) + anti-enumeration parity</name>
  <files>tests/integration/test_security_matrix.py</files>
  <read_first>
    - tests/integration/test_security_matrix.py (current state from Task 1)
    - tests/integration/test_per_user_scoping.py lines 380-460 (cross-user 404 + body parity assertion patterns)
    - app/api/task_api.py — confirm /task/{identifier} URL placeholder name (`identifier` in code, `task_uuid` in our catalog template)
    - .planning/phases/16-verification-cross-user-matrix-e2e/16-RESEARCH.md §Code Examples — Cross-user matrix parametrization
  </read_first>
  <action>
Append to test_security_matrix.py (do NOT modify Task 1 code).

Helper `_request(client, method, url, *, requires_csrf, body=None)`:
- headers = {}
- if requires_csrf: headers["X-CSRF-Token"] = client.cookies.get("csrf_token") or ""
- return client.request(method, url, json=body, headers=headers)
(Flat — single conditional on requires_csrf, no nesting.)

Helper `_format_url(template, resources)`:
- return template.format(**resources)
(One-liner; resources dict has task_uuid + key_id.)

`@pytest.mark.parametrize("method,path_tmpl,expected_foreign_status,requires_csrf", ENDPOINT_CATALOG)`
`@pytest.mark.integration`
`def test_foreign_user_blocked(method, path_tmpl, expected_foreign_status, requires_csrf, full_app, session_factory)`:
- app, _ = full_app
- client_a, client_b, resources = _seed_resources(app, session_factory)
- Build body: for POST /api/ws/ticket → body={"task_id": resources["task_uuid"]}; otherwise None. Use a flat conditional `body = {"task_id": resources["task_uuid"]} if path_tmpl == "/api/ws/ticket" else None`.
- url = _format_url(path_tmpl, resources)
- response = _request(client_b, method, url, requires_csrf=requires_csrf, body=body)
- For DELETE /api/account/data the foreign-leg outcome IS 204 (route is caller-scoped — B deletes B's empty data; not a leak). Catalog already encodes this.
- assert response.status_code == expected_foreign_status, f"{method} {url} expected {expected_foreign_status}, got {response.status_code}: {response.text}"

`@pytest.mark.parametrize("method,path_tmpl,_foreign,requires_csrf", ENDPOINT_CATALOG)`
`@pytest.mark.integration`
`def test_self_user_succeeds(method, path_tmpl, _foreign, requires_csrf, full_app, session_factory)`:
- app, _ = full_app
- client_a, _, resources = _seed_resources(app, session_factory)
- Same body logic as foreign test
- url = _format_url(path_tmpl, resources)
- response = _request(client_a, method, url, requires_csrf=requires_csrf, body=body)
- self_status = 200 if method == "GET" else 204 if path_tmpl == "/api/account/data" else 201 if path_tmpl == "/api/ws/ticket" else 204
- Catalog "self" expectations: GET → 200, /api/account/me → 200, /task/all → 200, /task/{uuid} → 200, /tasks/{uuid}/progress → 200, /api/ws/ticket POST → 201, DELETE /task/{uuid}/delete → 200 (per task_api implementation), DELETE /api/keys/{key_id} → 204, DELETE /api/account/data → 204. Verify exact status codes against the four route files before locking the table.
- Implement self_status as a flat lookup dict keyed by (method, path_tmpl), NOT nested ifs.
- assert response.status_code == self_status, f"self-leg {method} {url}: expected {self_status}, got {response.status_code}: {response.text}"

Locked self-status table (verify against route source during implementation; adjust if the @router decorator's status_code= differs):
```python
_SELF_STATUS: dict[tuple[str, str], int] = {
    ("GET",    "/task/all"):                       200,
    ("GET",    "/task/{task_uuid}"):               200,
    ("DELETE", "/task/{task_uuid}/delete"):        200,
    ("GET",    "/tasks/{task_uuid}/progress"):     200,
    ("POST",   "/api/ws/ticket"):                  201,
    ("DELETE", "/api/keys/{key_id}"):              204,
    ("DELETE", "/api/account/data"):               204,
    ("GET",    "/api/account/me"):                 200,
}
```

`@pytest.mark.integration`
`def test_anti_enum_body_parity_unknown_vs_foreign_task(full_app, session_factory)`:
- app, _ = full_app
- client_a, client_b, resources = _seed_resources(app, session_factory)
- foreign_response = client_b.get(f"/task/{resources['task_uuid']}")
- unknown_response = client_b.get("/task/uuid-does-not-exist-xyz-12345")
- assert foreign_response.status_code == 404
- assert unknown_response.status_code == 404
- assert foreign_response.json() == unknown_response.json(), "anti-enumeration: foreign-id and unknown-id 404 bodies must be identical"

Code quality:
- DRT: ENDPOINT_CATALOG is the single source; _request, _format_url, _seed_resources are reused
- SRP: each test asserts ONE thing
- Tiger-style: every assertion has a failure-message containing the actual response.text
- No nested-if (only flat conditionals + dict lookups)
- Names: client_a, client_b, foreign_response, unknown_response — never c1/c2/r1/r2
  </action>
  <verify>
    <automated>cd /c/laragon/www/whisperx && uv run pytest tests/integration/test_security_matrix.py -x -q 2>&1 | tail -30</automated>
  </verify>
  <done>
    - test_foreign_user_blocked passes for all 8 catalog rows (8 cases)
    - test_self_user_succeeds passes for all 8 catalog rows (8 cases)
    - test_anti_enum_body_parity_unknown_vs_foreign_task passes
    - 17+ cases collected and green
  </done>
  <acceptance_criteria>
    - `uv run pytest tests/integration/test_security_matrix.py -q --co 2>&1 | grep -c "::test_"` >= 17
    - `uv run pytest tests/integration/test_security_matrix.py -x -q` exit code 0
    - `grep -cE "    if .*:\\s*$" tests/integration/test_security_matrix.py` shows only flat early-return / one-line conditionals (manual review acceptable; nested-if invariant 0)
    - `grep -c "anti.enum\\|body parity\\|identical" tests/integration/test_security_matrix.py` >= 1 (parity test exists)
  </acceptance_criteria>
</task>

</tasks>

<verification>
- `uv run pytest tests/integration/test_security_matrix.py -v` → all green
- VERIFY-01 closed: cross-user matrix proves user-A resources invisible to user-B for 8 endpoints
- Anti-enumeration parity proven for /task/{id} (extends naturally to other 404 paths via locked Plan 13-07 invariant)
- No nested-if anywhere in new file
</verification>

<success_criteria>
- 8 foreign-leg cases parametrized + 8 self-leg cases parametrized + 1 body-parity case = 17+ tests pass
- ENDPOINT_CATALOG imported (not redefined) — DRT
- ASGI middleware order locked: CsrfMiddleware registered before DualAuthMiddleware
- limiter.reset() in setup AND teardown (Pitfall 1)
- Two TestClient instances per test (Pitfall 2)
</success_criteria>

<output>
After completion, create `.planning/phases/16-verification-cross-user-matrix-e2e/16-02-SUMMARY.md`
</output>
