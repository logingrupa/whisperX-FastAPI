---
phase: 16
plan: 01
type: execute
wave: 0
depends_on: []
files_modified:
  - tests/integration/_phase16_helpers.py
autonomous: true
requirements: []
tags: [verification, test-helpers, dry, jwt, csrf, alembic]
must_haves:
  truths:
    - "Five Phase-16 test files import helpers from a single source"
    - "Endpoint catalog hardcoded as one module-level constant"
    - "JWT forge / tamper / expire helpers reproducible (deterministic forge inputs)"
    - "Subprocess alembic helper portable on Windows venv"
    - "WS_POLICY_VIOLATION constant exposed (1008) — single source"
  artifacts:
    - path: "tests/integration/_phase16_helpers.py"
      provides: "ENDPOINT_CATALOG, _seed_two_users, _register, _insert_task, _forge_jwt, _issue_csrf_pair, _run_alembic, WS_POLICY_VIOLATION"
      min_lines: 130
      contains: "ENDPOINT_CATALOG"
  key_links:
    - from: "tests/integration/_phase16_helpers.py"
      to: "app.infrastructure.database.models.Task"
      via: "ORM import in _insert_task"
      pattern: "from app.infrastructure.database.models import Task"
    - from: "tests/integration/_phase16_helpers.py"
      to: "jwt (PyJWT)"
      via: "real HS256 sign for expired/tampered branches"
      pattern: "jwt.encode\\(.*algorithm=JWT_HS256\\)"
---

<objective>
Single DRT helper module for Phase 16's five test files. Caveman: ZERO test logic here — just shared building blocks. Plans 16-02..06 import these to stay file-disjoint and parallel-safe.

Purpose: SRP enforced — endpoint catalog, user seeding, JWT forging, CSRF cookie capture, subprocess alembic invocation each isolated in one named function.
Output: tests/integration/_phase16_helpers.py (~150 lines) — no test functions, no fixtures, no `@pytest.mark.*`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/16-verification-cross-user-matrix-e2e/16-CONTEXT.md
@.planning/phases/16-verification-cross-user-matrix-e2e/16-RESEARCH.md
@.planning/phases/16-verification-cross-user-matrix-e2e/16-PATTERNS.md
@.planning/phases/16-verification-cross-user-matrix-e2e/16-VALIDATION.md

@tests/integration/test_ws_ticket_flow.py
@tests/integration/test_alembic_migration.py
@tests/integration/test_per_user_scoping.py
@tests/integration/test_account_routes.py
@app/core/jwt_codec.py
@app/infrastructure/database/models.py

<interfaces>
<!-- Contracts the helper module exposes. Plans 16-02..06 consume these unchanged. -->

```python
# Constants
WS_POLICY_VIOLATION: int = 1008
JWT_HS256: str = "HS256"
JWT_ALG_NONE: str = "none"
REPO_ROOT: Path                # parents[2] of this file

# Endpoint catalog — single source for VERIFY-01 + VERIFY-06
# Tuple shape: (method, path_template, expected_foreign_status, requires_csrf)
ENDPOINT_CATALOG: list[tuple[str, str, int, bool]]
# Path placeholders: {task_uuid}, {key_id}

# Seeding
def _register(client: TestClient, email: str, password: str = "supersecret123") -> int
def _seed_two_users(client_a: TestClient, client_b: TestClient) -> tuple[int, int]
def _insert_task(session_factory, *, user_id: int, file_name: str = "audio.mp3") -> str

# JWT forging — kwargs-only to keep call sites self-explanatory
def _forge_jwt(
    *, alg: str, user_id: int, token_version: int = 0,
    secret: str | None = None, expired: bool = False, tamper: bool = False,
) -> str

# CSRF
def _issue_csrf_pair(client: TestClient, email: str) -> tuple[str, str]
#   returns (session_cookie_value, csrf_cookie_value)

# Migration
def _run_alembic(args: list[str], db_url: str) -> subprocess.CompletedProcess[str]
```

Verified ROUTE PATHS for ENDPOINT_CATALOG (grep app/api/ this session):
- task_router (no prefix): GET /task/all, GET /task/{identifier}, DELETE /task/{identifier}/delete, GET /tasks/{identifier}/progress
- key_router prefix=/api/keys: POST "", GET "", DELETE /{key_id}
- account_router prefix=/api/account: DELETE /data, GET /me, DELETE ""
- ws_ticket_router prefix=/api/ws: POST /ticket
</interfaces>
</context>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| test process → tmp SQLite | helper seeds rows; test owns DB lifecycle |
| test process → alembic subprocess | venv-portable env-passing; isolated DB_URL |

## STRIDE Threat Register (meta)

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-16-04 | Tampering | shared helpers | mitigate | ENDPOINT_CATALOG hardcoded; no env-driven branching; deterministic forge inputs |
| T-16-03 | Tampering | _run_alembic | mitigate | subprocess receives clean env with DB_URL pointing at tmp DB; never queries in-process engine |
| T-16-08 | Tampering | _forge_jwt | accept | helper returns raw strings; monkeypatch lifecycle owned by callers (test-scoped) |
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Write _phase16_helpers.py — constants + endpoint catalog + seeding helpers</name>
  <files>tests/integration/_phase16_helpers.py</files>
  <read_first>
    - tests/integration/test_ws_ticket_flow.py lines 1-75 (imports + tmp_db_url + session_factory + WS_POLICY_VIOLATION constant)
    - tests/integration/test_per_user_scoping.py lines 134-163 (_register, _insert_task helpers)
    - tests/integration/test_alembic_migration.py lines 1-65 (REPO_ROOT, _run_alembic)
    - app/api/task_api.py lines 16-117 (verify route paths: /task/all, /task/{identifier}, /task/{identifier}/delete, /tasks/{identifier}/progress)
    - app/api/key_routes.py lines 29-80 (verify /api/keys + /api/keys/{key_id})
    - app/api/account_routes.py lines 35-95 (verify /api/account/data, /api/account/me, /api/account)
    - app/api/ws_ticket_routes.py lines 40-65 (verify /api/ws/ticket)
    - app/infrastructure/database/models.py — Task ORM column shape for _insert_task
  </read_first>
  <action>
Create file with module docstring stating "DRT helpers for Phase 16 verification tests; imported by test_security_matrix / test_jwt_attacks / test_csrf_enforcement / test_ws_ticket_safety / test_migration_smoke."

Imports (top of file, alphabetized within stdlib/3rd-party/local groups):
```
from __future__ import annotations
import base64, json, os, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

import jwt
from fastapi.testclient import TestClient
```
Note: do NOT import from sqlalchemy here — _insert_task takes session_factory and imports ORMTask lazily inside the function body to keep this module loadable without DB engine bound.

Constants section:
- `WS_POLICY_VIOLATION = 1008`
- `JWT_HS256 = "HS256"`
- `JWT_ALG_NONE = "none"`
- `REPO_ROOT = Path(__file__).resolve().parents[2]`

ENDPOINT_CATALOG (verbatim from RESEARCH.md §Naming + DRY Surface, paths corrected against grep results):
```python
ENDPOINT_CATALOG: list[tuple[str, str, int, bool]] = [
    ("GET",    "/task/all",                       200, False),
    ("GET",    "/task/{task_uuid}",               404, False),
    ("DELETE", "/task/{task_uuid}/delete",        404, True),
    ("GET",    "/tasks/{task_uuid}/progress",     404, False),
    ("POST",   "/api/ws/ticket",                  404, True),
    ("DELETE", "/api/keys/{key_id}",              404, True),
    ("DELETE", "/api/account/data",               204, True),
    ("GET",    "/api/account/me",                 200, False),
]
```
The "self" expected status for /api/account/me is 200; for the delete endpoints with cross-user requests, foreign_status is the locked anti-enumeration outcome (404 not 403).

Implement `_register(client, email, password="supersecret123") -> int`:
- POST /auth/register with `{"email": email, "password": password}`
- assert response.status_code == 201, response.text
- return int(response.json()["user_id"])

Implement `_seed_two_users(client_a, client_b) -> tuple[int, int]`:
- a = _register(client_a, "user-a@phase16.example.com")
- b = _register(client_b, "user-b@phase16.example.com")
- return (a, b)

Implement `_insert_task(session_factory, *, user_id, file_name="audio.mp3") -> str`:
- Lazy import: `from app.infrastructure.database.models import Task as ORMTask`
- task_uuid = f"uuid-u{user_id}-{datetime.now(timezone.utc).timestamp()}"
- with session_factory() as session: session.add(ORMTask(uuid=task_uuid, status="pending", file_name=file_name, task_type="speech-to-text", user_id=user_id)); session.commit()
- return task_uuid

No nested-if. No conditionals beyond early-return. Self-explanatory names. Tiger-style assertions (assert response.status_code == 201 with response.text reason).
  </action>
  <verify>
    <automated>cd /c/laragon/www/whisperx && python -c "from tests.integration import _phase16_helpers as h; assert h.WS_POLICY_VIOLATION == 1008; assert h.JWT_HS256 == 'HS256'; assert h.JWT_ALG_NONE == 'none'; assert isinstance(h.ENDPOINT_CATALOG, list); assert len(h.ENDPOINT_CATALOG) == 8; assert h.REPO_ROOT.exists(); assert callable(h._register); assert callable(h._seed_two_users); assert callable(h._insert_task); print('OK')"</automated>
  </verify>
  <done>
    - File exists; module imports cleanly with no side effects
    - 8 entries in ENDPOINT_CATALOG with correct shape (method, template, expected_foreign_status, requires_csrf)
    - Three seeding functions defined with kwargs-only signatures where applicable
    - REPO_ROOT resolves to whisperx repo root
  </done>
  <acceptance_criteria>
    - `grep -c "def _register\|def _seed_two_users\|def _insert_task" tests/integration/_phase16_helpers.py` == 3
    - `grep -c "ENDPOINT_CATALOG" tests/integration/_phase16_helpers.py` >= 1
    - `grep -c "if .*:" tests/integration/_phase16_helpers.py` == 0 in this task's added code (no nested-if; conditionals introduced in Task 2 for forge branches only)
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 2: Add JWT forge + CSRF capture + alembic subprocess helpers</name>
  <files>tests/integration/_phase16_helpers.py</files>
  <read_first>
    - tests/integration/_phase16_helpers.py (current state from Task 1)
    - app/core/jwt_codec.py — confirm `algorithms=["HS256"]` decode path + claim names (sub, iat, exp, ver, method)
    - .planning/phases/16-verification-cross-user-matrix-e2e/16-RESEARCH.md §Pattern 3, 4, 5, 7 (JWT forge + alembic subprocess)
    - tests/integration/test_alembic_migration.py lines 34-53 (_run_alembic verbatim source)
  </read_first>
  <action>
Append to _phase16_helpers.py (do NOT touch Task-1 code):

`_b64url(raw: dict | bytes) -> str`:
- if isinstance(raw, dict): raw = json.dumps(raw, separators=(",", ":")).encode()
- return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

`_forge_jwt(*, alg, user_id, token_version=0, secret=None, expired=False, tamper=False) -> str`:
Three branches via early-return (no nested-if):
1. now = int(time.time())
2. payload = {"sub": str(user_id), "iat": now-86400 if expired else now, "exp": now-3600 if expired else now+86400, "ver": token_version, "method": "session"}
3. if alg == JWT_ALG_NONE: header = {"alg": "none", "typ": "JWT"}; return f"{_b64url(header)}.{_b64url(payload)}." (trailing dot, empty signature)
4. assert secret is not None, "HS256 forge requires secret"
5. token = jwt.encode(payload, secret, algorithm=JWT_HS256)
6. if not tamper: return token
7. head, body, sig = token.split("."); flipped = "A" if sig[-1] != "A" else "B"; return f"{head}.{body}.{sig[:-1]}{flipped}"

The two-step ternary on iat/exp keeps the body flat (no nested-if). The `if alg == JWT_ALG_NONE: ...; return ...` is a flat early-return guard. The `if not tamper: return token` is a flat early-return guard. The final two-line tamper construction is unconditional.

`_issue_csrf_pair(client, email) -> tuple[str, str]`:
- _register(client, email)
- session = client.cookies.get("session")
- csrf = client.cookies.get("csrf_token")
- assert session is not None, "session cookie missing after register"
- assert csrf is not None, "csrf_token cookie missing after register"
- return (session, csrf)

`_run_alembic(args, db_url) -> subprocess.CompletedProcess[str]` — copy verbatim from test_alembic_migration.py:34-53:
```python
env = os.environ.copy()
env["DB_URL"] = db_url
return subprocess.run(
    [sys.executable, "-m", "alembic", *args],
    cwd=REPO_ROOT, env=env, check=True, capture_output=True, text=True,
)
```

Self-check after edit:
- `grep -E "^def " tests/integration/_phase16_helpers.py | wc -l` returns 7 (_register, _seed_two_users, _insert_task, _b64url, _forge_jwt, _issue_csrf_pair, _run_alembic)
- No `if a: if b:` patterns. Nested-if grep == 0.
  </action>
  <verify>
    <automated>cd /c/laragon/www/whisperx && python -c "from tests.integration._phase16_helpers import _forge_jwt, _b64url, _issue_csrf_pair, _run_alembic, JWT_ALG_NONE, JWT_HS256; t = _forge_jwt(alg=JWT_ALG_NONE, user_id=42); parts = t.split('.'); assert len(parts) == 3 and parts[2] == '', f'alg=none token shape wrong: {t}'; t2 = _forge_jwt(alg=JWT_HS256, user_id=7, secret='x' * 32, tamper=True); parts2 = t2.split('.'); assert len(parts2) == 3 and len(parts2[2]) > 0, 'tampered token must keep all 3 segments'; t3 = _forge_jwt(alg=JWT_HS256, user_id=7, secret='x' * 32, expired=True); import jwt as _j; payload = _j.decode(t3, 'x' * 32, algorithms=['HS256'], options={'verify_exp': False}); assert payload['exp'] < payload['iat'] + 100000 and payload['exp'] < int(__import__('time').time()), 'expired token must have exp in the past'; print('OK')"</automated>
  </verify>
  <done>
    - _forge_jwt produces correct shape for all three branches (alg=none, HS256+expired, HS256+tamper)
    - alg=none token has empty signature segment (trailing dot)
    - tampered token's signature differs from a freshly-signed token by exactly 1 char
    - expired token's exp claim is in the past relative to now
    - _issue_csrf_pair returns 2 non-None strings after a successful register
    - _run_alembic accepts list args + db_url string; passes DB_URL via env
  </done>
  <acceptance_criteria>
    - `grep -c "def _b64url\|def _forge_jwt\|def _issue_csrf_pair\|def _run_alembic" tests/integration/_phase16_helpers.py` == 4
    - Total functions in file: `grep -cE "^def " tests/integration/_phase16_helpers.py` == 7
    - Nested-if invariant: `grep -E "    if .*:$" tests/integration/_phase16_helpers.py | wc -l` matches the early-return guards only (no nested branches)
  </acceptance_criteria>
</task>

</tasks>

<verification>
- Module loads without DB engine: `python -c "from tests.integration import _phase16_helpers"`
- All 7 helpers callable.
- ENDPOINT_CATALOG matches grep'd route paths in app/api/.
- No `pytest` references in the file (helpers are pytest-agnostic).
</verification>

<success_criteria>
- Plans 16-02..06 can `from tests.integration._phase16_helpers import ...` without import errors
- Endpoint catalog has 8 entries, all paths verified against actual @router decorators
- JWT forge supports 3 deterministic branches (none / expired / tamper)
- _run_alembic mirrors test_alembic_migration.py:34-53 exactly
- Tiger-style: every helper asserts at boundary (response.status_code, cookies present)
</success_criteria>

<output>
After completion, create `.planning/phases/16-verification-cross-user-matrix-e2e/16-01-SUMMARY.md`
</output>
