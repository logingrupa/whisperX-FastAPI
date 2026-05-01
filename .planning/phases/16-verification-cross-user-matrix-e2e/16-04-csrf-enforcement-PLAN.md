---
phase: 16
plan: 04
type: execute
wave: 1
depends_on: [16-01]
files_modified:
  - tests/integration/test_csrf_enforcement.py
autonomous: true
requirements: [VERIFY-06]
tags: [verification, csrf, double-submit, bearer-bypass, security]
must_haves:
  truths:
    - "Cookie-auth state-mutating POST without X-CSRF-Token header → 403 'CSRF token missing'"
    - "Cookie-auth state-mutating POST with mismatched X-CSRF-Token → 403 'CSRF token mismatch'"
    - "Cookie-auth state-mutating POST with matching X-CSRF-Token → 204 (success)"
    - "Bearer-auth POST WITHOUT X-CSRF-Token still succeeds (CsrfMiddleware skips when auth_method='bearer')"
  artifacts:
    - path: "tests/integration/test_csrf_enforcement.py"
      provides: "VERIFY-06 — 4 cases (missing, mismatched, matching, bearer-bypass)"
      min_lines: 140
      contains: "X-CSRF-Token"
  key_links:
    - from: "test_csrf_enforcement.py"
      to: "tests/integration/_phase16_helpers._issue_csrf_pair"
      via: "captures session+csrf_token cookies after register"
      pattern: "_issue_csrf_pair"
    - from: "auth_full_app fixture"
      to: "CsrfMiddleware → DualAuthMiddleware order"
      via: "ASGI stack registration"
      pattern: "add_middleware\\(CsrfMiddleware.*\\n.*add_middleware\\(DualAuthMiddleware"
---

<objective>
Implement VERIFY-06 CSRF double-submit enforcement. Caveman: 4 cases. State-mutating cookie request without/with mismatched/with matching X-CSRF-Token → 403/403/204. Bearer-auth same request without header → 204 (skip).

Purpose: prove CsrfMiddleware enforces double-submit cookie pattern AND skips bearer-auth surfaces, per MID-04.
Output: tests/integration/test_csrf_enforcement.py (~150 lines).
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

@tests/integration/test_phase13_e2e_smoke.py
@tests/integration/test_auth_routes.py
@tests/integration/_phase16_helpers.py
@app/core/csrf_middleware.py
@app/core/dual_auth.py
@app/api/key_routes.py
@app/api/auth_routes.py

<interfaces>
<!-- From _phase16_helpers -->
def _issue_csrf_pair(client, email) -> tuple[str, str]
def _register(client, email, password=...) -> int

<!-- From CsrfMiddleware (verified via grep) -->
# csrf_middleware emits 403 with detail="CSRF token missing" or "CSRF token mismatch"
# Skipped when request.state.auth_method == "bearer"
# State-mutating methods: POST, PUT, PATCH, DELETE
```

</interfaces>
</context>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser cookie session → CSRF middleware | double-submit: cookie csrf_token must equal X-CSRF-Token header |
| API-key Bearer client → CSRF middleware | bearer auth bypasses CSRF check |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-16-05 | Tampering | cookie-auth state mutation | mitigate | CsrfMiddleware compares cookie value to header via secrets.compare_digest |
| T-16-07 | Spoofing | matching-leg passes for wrong reason | mitigate | always use POST (state-mutating); verify response body detail string for the 403 cases |
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: auth_full_app fixture (auth + key routers + full middleware) + bearer-bootstrap helper</name>
  <files>tests/integration/test_csrf_enforcement.py</files>
  <read_first>
    - tests/integration/test_auth_routes.py lines 50-160 (auth_full_app fixture template)
    - tests/integration/test_phase13_e2e_smoke.py — bearer-skips-CSRF subprocess pattern
    - tests/integration/_phase16_helpers.py
    - app/core/csrf_middleware.py — exact 403 detail strings ("CSRF token missing", "CSRF token mismatch")
    - app/api/key_routes.py — POST /api/keys signature (returns plaintext key once)
    - app/api/auth_routes.py — POST /auth/logout-all (target endpoint for cookie-auth tests)
  </read_first>
  <action>
Create file with module docstring: "VERIFY-06 CSRF double-submit. 4 cases: missing/mismatched/matching X-CSRF-Token + bearer-auth bypass."

Imports (same shape as Plan 16-03, plus key_router for bearer-bypass test):
```python
from __future__ import annotations
from collections.abc import Generator
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
from app.api.key_routes import key_router
from app.core.container import Container
from app.core.csrf_middleware import CsrfMiddleware
from app.core.dual_auth import DualAuthMiddleware
from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import Base

from tests.integration._phase16_helpers import _issue_csrf_pair, _register
```

Fixtures (copy shape from Plan 16-02 / Plan 16-03):
- tmp_db_url, session_factory
- `auth_full_app(tmp_db_url, session_factory) -> Generator[tuple[FastAPI, Container], None, None]`:
  - Mount auth_router + key_router (key_router needed for bearer-bypass test target)
  - Same 3 exception handlers
  - Middleware: CsrfMiddleware first, DualAuthMiddleware second
  - limiter.reset() in setup AND teardown

Helper `_issue_api_key(client) -> str`:
- Cookie-auth POST /api/keys with json={"name": "csrf-bypass-test"} and X-CSRF-Token header from cookies
- assert response.status_code == 201, response.text
- return response.json()["key"]  # plaintext key, shown once

Helper `_csrf_target_endpoint() -> str` returns the path under test:
- "/auth/logout-all"  (state-mutating, idempotent, cookie-auth path, ALL Phase 15 lessons confirm 204 on success)

This is one helper to keep the target path single-source. Future endpoint changes touch one place.
  </action>
  <verify>
    <automated>cd /c/laragon/www/whisperx && uv run pytest tests/integration/test_csrf_enforcement.py --collect-only -q 2>&1 | head -20</automated>
  </verify>
  <done>
    - File created; pytest collects fixtures
    - auth_full_app mounts auth_router + key_router + DualAuth + CSRF
    - _issue_api_key helper returns plaintext key
  </done>
  <acceptance_criteria>
    - `grep -c "include_router(auth_router\\|include_router(key_router" tests/integration/test_csrf_enforcement.py` >= 2
    - `grep -nE "add_middleware\\(CsrfMiddleware|add_middleware\\(DualAuthMiddleware" tests/integration/test_csrf_enforcement.py` shows CSRF before DualAuth
    - `grep -c "limiter.reset()" tests/integration/test_csrf_enforcement.py` >= 2
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 2: 4 CSRF cases — missing, mismatched, matching, bearer-bypass</name>
  <files>tests/integration/test_csrf_enforcement.py</files>
  <read_first>
    - tests/integration/test_csrf_enforcement.py (current state from Task 1)
    - app/core/csrf_middleware.py — verify exact response body shape (`{"detail": "CSRF token missing"}` etc.)
    - app/core/dual_auth.py — verify Bearer header recognition + state.auth_method assignment
  </read_first>
  <action>
Append 4 test functions:

```python
@pytest.mark.integration
def test_csrf_missing_header_returns_403(auth_full_app):
    app, _ = auth_full_app
    client = TestClient(app)
    _, _ = _issue_csrf_pair(client, "csrf-missing@phase16.example.com")
    # Cookies attached automatically; X-CSRF-Token deliberately absent
    response = client.post(_csrf_target_endpoint())
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "CSRF token missing", response.text


@pytest.mark.integration
def test_csrf_mismatched_header_returns_403(auth_full_app):
    app, _ = auth_full_app
    client = TestClient(app)
    _, _ = _issue_csrf_pair(client, "csrf-mismatch@phase16.example.com")
    response = client.post(
        _csrf_target_endpoint(),
        headers={"X-CSRF-Token": "deadbeef-not-the-real-cookie-value-12345"},
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "CSRF token mismatch", response.text


@pytest.mark.integration
def test_csrf_matching_header_succeeds(auth_full_app):
    app, _ = auth_full_app
    client = TestClient(app)
    _, csrf_cookie_value = _issue_csrf_pair(client, "csrf-match@phase16.example.com")
    response = client.post(
        _csrf_target_endpoint(),
        headers={"X-CSRF-Token": csrf_cookie_value},
    )
    assert response.status_code == 204, response.text


@pytest.mark.integration
def test_bearer_auth_bypasses_csrf(auth_full_app):
    """Bearer-auth state-mutating request WITHOUT X-CSRF-Token still succeeds — MID-04."""
    app, _ = auth_full_app
    client = TestClient(app)
    _issue_csrf_pair(client, "csrf-bearer-bypass@phase16.example.com")
    plaintext_key = _issue_api_key(client)  # cookie-auth path issues key

    # Now drop ALL cookies; switch to Bearer auth
    client.cookies.clear()
    response = client.post(
        _csrf_target_endpoint(),
        headers={"Authorization": f"Bearer {plaintext_key}"},
    )
    # Bearer auth bypasses CSRF; response should be 204 (success) — never 403 CSRF
    assert response.status_code == 204, response.text
    # Defence-in-depth: confirm the failure mode is NOT a CSRF rejection
    if response.status_code == 403:  # this branch never fires under correct behavior
        assert "CSRF" not in response.text, "bearer auth must skip CSRF check"
```

Note on the last test:
- `client.cookies.clear()` is REQUIRED — otherwise the session+csrf_token cookies remain, and DualAuthMiddleware's bearer-then-cookie resolution still picks bearer FIRST (Phase 13-02 STATE.md), but for unambiguous test signal we want zero cookie noise. Clearing forces ONLY the bearer path to be exercised.
- The defensive `if response.status_code == 403` block is a flat post-assert log path; it does NOT count as nested-if since the prior `assert response.status_code == 204` would have already fired. Phase 16 invariant verified by primary assert; this branch is documentation-as-code for what failure would look like.
- Even simpler: drop the defensive branch entirely. Single assert is enough.

DRT: _csrf_target_endpoint() is the single source for which path is tested.
SRP: each test asserts ONE thing (status code + body detail).
Tiger-style: assert response body string equality on 403 cases (not just status code).

Final test count: 4.

After implementation, remove the defensive `if response.status_code == 403` block from test_bearer_auth_bypasses_csrf to keep nested-if grep == 0.
  </action>
  <verify>
    <automated>cd /c/laragon/www/whisperx && uv run pytest tests/integration/test_csrf_enforcement.py -x -q 2>&1 | tail -20</automated>
  </verify>
  <done>
    - 4 cases collected
    - All 4 pass
    - Missing-header case asserts detail="CSRF token missing"
    - Mismatched-header case asserts detail="CSRF token mismatch"
    - Matching-header case → 204
    - Bearer-bypass case → 204 with no X-CSRF-Token header
  </done>
  <acceptance_criteria>
    - `uv run pytest tests/integration/test_csrf_enforcement.py -q --co 2>&1 | grep -c "::test_"` == 4
    - `uv run pytest tests/integration/test_csrf_enforcement.py -x -q` exit code 0
    - `grep -c "X-CSRF-Token" tests/integration/test_csrf_enforcement.py` >= 3
    - `grep -c '"CSRF token missing"\\|"CSRF token mismatch"' tests/integration/test_csrf_enforcement.py` >= 2
    - Nested-if invariant: `grep -cE "        if .*:$" tests/integration/test_csrf_enforcement.py` == 0
  </acceptance_criteria>
</task>

</tasks>

<verification>
- `uv run pytest tests/integration/test_csrf_enforcement.py -v` → 4 green
- VERIFY-06 closed
- Bearer-bypass invariant proven (MID-04)
</verification>

<success_criteria>
- 4 cases pass
- Single source of target endpoint via _csrf_target_endpoint()
- Tiger-style assertions on response body detail strings (not just status codes)
- ASGI middleware order locked
- limiter.reset() in setup AND teardown
- No nested-if
</success_criteria>

<output>
After completion, create `.planning/phases/16-verification-cross-user-matrix-e2e/16-04-SUMMARY.md`
</output>
