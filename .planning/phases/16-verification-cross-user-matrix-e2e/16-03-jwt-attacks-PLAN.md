---
phase: 16
plan: 03
type: execute
wave: 1
depends_on: [16-01]
files_modified:
  - tests/integration/test_jwt_attacks.py
autonomous: true
requirements: [VERIFY-02, VERIFY-03, VERIFY-04]
tags: [verification, jwt, alg-none, tampered, expired, security]
must_haves:
  truths:
    - "alg=none JWT sent via Authorization: Bearer header → 401"
    - "alg=none JWT sent via session cookie → 401"
    - "Tampered HS256 JWT (last sig char flipped) via Bearer → 401"
    - "Tampered HS256 JWT via session cookie → 401"
    - "Expired HS256 JWT (real signing key, exp in past) via Bearer → 401"
    - "Expired HS256 JWT via session cookie → 401"
  artifacts:
    - path: "tests/integration/test_jwt_attacks.py"
      provides: "VERIFY-02/03/04 — 6 attack cases (3 forgeries × 2 transports)"
      min_lines: 160
      contains: "_forge_jwt"
  key_links:
    - from: "tests/integration/test_jwt_attacks.py"
      to: "tests/integration/_phase16_helpers._forge_jwt"
      via: "import + call with alg/expired/tamper kwargs"
      pattern: "_forge_jwt\\(alg="
    - from: "test_jwt_attacks.auth_full_app fixture"
      to: "container.settings().auth.JWT_SECRET (SecretStr)"
      via: "extract real signing secret for expired-token forge"
      pattern: "JWT_SECRET.*get_secret_value"
---

<objective>
Implement VERIFY-02/03/04 JWT hardening tests. Caveman: 3 forgeries (alg=none / tampered / expired) × 2 transports (Bearer header / session cookie) = 6 cases. Each must 401.

Purpose: prove the single decode site `app/core/jwt_codec.py` rejects every malformed token regardless of how it arrives.
Output: tests/integration/test_jwt_attacks.py (~180 lines).
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

@tests/integration/test_auth_routes.py
@tests/integration/_phase16_helpers.py
@app/core/jwt_codec.py
@app/core/dual_auth.py
@app/core/exceptions.py
@app/core/container.py

<interfaces>
<!-- From _phase16_helpers -->
def _forge_jwt(*, alg, user_id, token_version=0, secret=None, expired=False, tamper=False) -> str
def _register(client, email, password=...) -> int
JWT_HS256: str
JWT_ALG_NONE: str

<!-- The Container exposes JWT_SECRET via nested settings — needed for HS256 forge of expired/tampered tokens -->
container.settings().auth.JWT_SECRET  # SecretStr (Pydantic v2)
# unwrap with: container.settings().auth.JWT_SECRET.get_secret_value()
# Phase 11-04 lesson: dependency-injector chain works directly via providers,
# but in tests we read it from the resolved settings instance.
```

</interfaces>
</context>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| client (forged token) → DualAuthMiddleware | bearer-then-cookie resolution; both must 401 on bad JWT |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-16-04 | Spoofing | JWT decode | mitigate | algorithms=["HS256"] explicit allow-list in jwt_codec.decode_session; alg=none surfaces InvalidAlgorithmError → 401 |
| T-16-05 | Spoofing | tampered HMAC | mitigate | PyJWT raises InvalidSignatureError → mapped JwtTamperedError → 401 |
| T-16-04 (subtype) | Tampering | expired token replay | mitigate | exp claim enforced by PyJWT → ExpiredSignatureError → JwtExpiredError → 401 |
| T-16-04 (catch-too-broad) | Spoofing | KeyError("ver") false-positive 401 | mitigate | tests forge with `ver=0` claim explicitly so 401 fires from algorithm/signature/expiry path, not KeyError |
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: auth_full_app fixture (full middleware stack including CSRF) + JWT secret access</name>
  <files>tests/integration/test_jwt_attacks.py</files>
  <read_first>
    - tests/integration/test_auth_routes.py lines 50-160 (auth_full_app fixture template — full middleware stack)
    - tests/integration/_phase16_helpers.py (full file)
    - app/core/container.py — confirm settings provider exposes auth.JWT_SECRET
    - app/core/jwt_codec.py — confirm decode_session signature + claim names (sub, iat, exp, ver, method)
    - app/core/dual_auth.py — confirm bearer-then-cookie resolution + which routes need auth
    - .planning/phases/16-verification-cross-user-matrix-e2e/16-PATTERNS.md §test_jwt_attacks.py
  </read_first>
  <action>
Create file with module docstring: "VERIFY-02/03/04 JWT attack tests — 3 forgeries × 2 transports = 6 cases. Each forged token must produce 401."

Imports:
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
from app.core.container import Container
from app.core.csrf_middleware import CsrfMiddleware
from app.core.dual_auth import DualAuthMiddleware
from app.core.exceptions import InvalidCredentialsError, ValidationError
from app.core.rate_limiter import limiter, rate_limit_handler
from app.infrastructure.database.models import Base

from tests.integration._phase16_helpers import (
    JWT_ALG_NONE,
    JWT_HS256,
    _forge_jwt,
    _register,
)
```

Fixtures:
- `tmp_db_url(tmp_path) -> str` (same shape as Plan 16-02 Task 1)
- `session_factory(tmp_db_url) -> sessionmaker`
- `auth_full_app(tmp_db_url, session_factory) -> Generator[tuple[FastAPI, Container], None, None]`:
  - Container(); container.db_session_factory.override(providers.Factory(session_factory)); dependencies.set_container(container); limiter.reset()
  - app = FastAPI(); app.state.limiter = limiter
  - 3 exception handlers (RateLimit, InvalidCredentials, ValidationError)
  - Routers: auth_router only (forge tests target /auth/logout-all — protected, state-mutating, exists)
  - Middleware in correct order: CsrfMiddleware first, then DualAuthMiddleware
  - yield (app, container)
  - Teardown: unwire, reset_override, limiter.reset()

Helper `_jwt_secret(container) -> str`:
- raw = container.settings().auth.JWT_SECRET
- Handle Pydantic SecretStr: return raw.get_secret_value() if hasattr(raw, "get_secret_value") else str(raw)
- Flat early-return; no nesting.

Helper `_register_user(client, email="attacker@phase16.example.com") -> int`:
- Wraps `_register(client, email)` to keep tests one-line.
- Returns user_id.

Why /auth/logout-all is the target:
- POST /auth/logout-all is auth-protected, state-mutating, exists in v1.2 (Plan 15-02), and bumps token_version on success → if forged auth bypassed, the user_id resolved from forged token would mutate that user's row. Side-channel detection: 401 means rejection BEFORE handler fires.
- No CSRF concern: alg=none Bearer-header tests don't hit cookie path; the cookie-path tests still need CSRF to be the issue WHY the request fails ONLY if 401 layer is reached. Best practice: clear cookies entirely so neither valid session nor csrf cookie exists; forge attaches only the bad token.

Code quality: same gates as Plan 16-02 (DRT, SRP, tiger-style, no nested-if, self-explanatory names like `forged_token`, `auth_full_app`, never `t`, `app2`).
  </action>
  <verify>
    <automated>cd /c/laragon/www/whisperx && uv run pytest tests/integration/test_jwt_attacks.py --collect-only -q 2>&1 | head -20</automated>
  </verify>
  <done>
    - File created; imports resolve; pytest collects fixtures
    - auth_full_app fixture mounts auth_router + CsrfMiddleware + DualAuthMiddleware
    - _jwt_secret helper unwraps SecretStr
  </done>
  <acceptance_criteria>
    - `grep -c "add_middleware(CsrfMiddleware\\|add_middleware(DualAuthMiddleware" tests/integration/test_jwt_attacks.py` == 2
    - `grep -nE "add_middleware\\(CsrfMiddleware|add_middleware\\(DualAuthMiddleware" tests/integration/test_jwt_attacks.py` shows CSRF before DualAuth (Pitfall 3)
    - `grep -c "limiter.reset()" tests/integration/test_jwt_attacks.py` >= 2
    - `grep -c "from tests.integration._phase16_helpers import" tests/integration/test_jwt_attacks.py` == 1
  </acceptance_criteria>
</task>

<task type="auto">
  <name>Task 2: 6 attack cases — alg=none, tampered, expired × {Bearer, session cookie}</name>
  <files>tests/integration/test_jwt_attacks.py</files>
  <read_first>
    - tests/integration/test_jwt_attacks.py (current state from Task 1)
    - app/core/dual_auth.py — confirm Authorization: Bearer header pattern + session cookie name "session"
    - app/core/jwt_codec.py — confirm exception → 401 mapping
    - .planning/phases/16-verification-cross-user-matrix-e2e/16-PATTERNS.md §test_jwt_attacks.py code samples
  </read_first>
  <action>
Append 6 test cases to test_jwt_attacks.py. Use kwargs-only forge calls.

Pattern for every test (six identical-shape tests):
```python
@pytest.mark.integration
def test_<attack>_via_<transport>_returns_401(
    auth_full_app: tuple[FastAPI, Container],
) -> None:
    app, container = auth_full_app
    client = TestClient(app)
    user_id = _register_user(client, "attacker-<unique>@phase16.example.com")
    # forge token (varies per test)
    forged_token = _forge_jwt(...)
    # clear all cookies — test ONLY the forged-token path
    client.cookies.clear()
    # attach via header OR cookie (varies per test)
    if transport == "bearer":
        response = client.post("/auth/logout-all", headers={"Authorization": f"Bearer {forged_token}"})
    else:
        client.cookies.set("session", forged_token)
        response = client.post("/auth/logout-all")
    assert response.status_code == 401, response.text
```

Replace inline `if/else` with two separate test functions to keep nested-if 0. Six functions:

1. `test_alg_none_via_bearer_returns_401` — `_forge_jwt(alg=JWT_ALG_NONE, user_id=user_id)`; attach as `Authorization: Bearer <token>`.

2. `test_alg_none_via_session_cookie_returns_401` — `_forge_jwt(alg=JWT_ALG_NONE, user_id=user_id)`; `client.cookies.set("session", forged_token)`.

3. `test_tampered_via_bearer_returns_401` — `_forge_jwt(alg=JWT_HS256, user_id=user_id, secret=_jwt_secret(container), tamper=True)`; Bearer header.

4. `test_tampered_via_session_cookie_returns_401` — same forge call; cookie path.

5. `test_expired_via_bearer_returns_401` — `_forge_jwt(alg=JWT_HS256, user_id=user_id, secret=_jwt_secret(container), expired=True)`; Bearer header.

6. `test_expired_via_session_cookie_returns_401` — same forge call; cookie path.

Each test:
- Calls _register_user with a unique email so rate-limit per-IP/24 doesn't fire — register limit is 3/hr — so SHARE one register across tests via parametrize OR use distinct emails AND limiter.reset() per test (the fixture handles this).
- Cleared cookies before attaching forged token (Pitfall 2).
- Asserts only response.status_code == 401 with `response.text` in the message; deeper body assertion deferred to Phase 17 docs (we just need the 401 invariant).

Tiger-style hardening (optional defence-in-depth): assert response.headers.get("WWW-Authenticate", "").startswith("Bearer") on bearer-path tests. Phase 13-02 STATE confirms this header is set on 401.

DRT: extract a parametrize for transport if it doesn't introduce nested-if or break per-test independence:
```python
_TRANSPORTS = [
    pytest.param("bearer", id="bearer"),
    pytest.param("cookie", id="cookie"),
]

@pytest.mark.parametrize("transport", _TRANSPORTS)
@pytest.mark.integration
def test_alg_none_returns_401(transport, auth_full_app):
    app, container = auth_full_app
    client = TestClient(app)
    user_id = _register_user(client, f"alg-none-{transport}@phase16.example.com")
    forged_token = _forge_jwt(alg=JWT_ALG_NONE, user_id=user_id)
    client.cookies.clear()
    response = _send_with(client, transport, forged_token)
    assert response.status_code == 401, response.text
```

Helper `_send_with(client, transport, token)`:
- if transport == "bearer": return client.post("/auth/logout-all", headers={"Authorization": f"Bearer {token}"})
- if transport == "cookie": client.cookies.set("session", token); return client.post("/auth/logout-all")
- raise ValueError(f"unknown transport: {transport}")
(Two flat early-return guards + raise. No nesting.)

This collapses 6 tests into 3 test functions × 2 transport params = 6 cases, while keeping nested-if 0.

Final test count: 3 parametrized × 2 = 6 cases on collection.
  </action>
  <verify>
    <automated>cd /c/laragon/www/whisperx && uv run pytest tests/integration/test_jwt_attacks.py -x -q 2>&1 | tail -20</automated>
  </verify>
  <done>
    - 6 attack cases collected (3 functions × 2 transports)
    - All 6 return 401
    - alg=none case proves PyJWT decode rejection via algorithms allow-list
    - tampered case proves HMAC verify rejection
    - expired case proves exp claim enforcement
  </done>
  <acceptance_criteria>
    - `uv run pytest tests/integration/test_jwt_attacks.py -q --co 2>&1 | grep -c "::test_"` == 6
    - `uv run pytest tests/integration/test_jwt_attacks.py -x -q` exit code 0
    - `grep -c "_forge_jwt(alg=" tests/integration/test_jwt_attacks.py` >= 3
    - `grep -c "client.cookies.clear()" tests/integration/test_jwt_attacks.py` >= 1 (Pitfall 2 — clear before attaching forged)
    - Nested-if invariant: `grep -E "        if .*:$" tests/integration/test_jwt_attacks.py | wc -l` == 0 (only flat top-level early-returns inside _send_with)
  </acceptance_criteria>
</task>

</tasks>

<verification>
- `uv run pytest tests/integration/test_jwt_attacks.py -v` → 6 green
- VERIFY-02 closed (alg=none × 2 transports both 401)
- VERIFY-03 closed (tampered × 2 transports both 401)
- VERIFY-04 closed (expired × 2 transports both 401)
- Single decode site invariant verified: every rejection path collapses to 401 via DualAuthMiddleware
</verification>

<success_criteria>
- 6 cases pass; all assert 401
- _forge_jwt called via kwargs only (kwargs-only contract from Plan 16-01)
- Clear cookies before attaching forged token (Pitfall 2)
- limiter.reset() in fixture setup AND teardown (Pitfall 1)
- No nested-if; flat early-returns only
</success_criteria>

<output>
After completion, create `.planning/phases/16-verification-cross-user-matrix-e2e/16-03-SUMMARY.md`
</output>
