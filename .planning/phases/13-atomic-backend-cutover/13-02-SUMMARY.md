---
phase: 13-atomic-backend-cutover
plan: 02
subsystem: backend-middleware
tags: [auth, middleware, csrf, dual-auth, sliding-refresh, request-state, dependencies]
requires:
  - Phase 11 jwt_codec, KeyService.verify_plaintext, TokenService.verify_and_refresh, CsrfService
  - Phase 13 Plan 01 AuthSettings (V2_ENABLED, COOKIE_SECURE, COOKIE_DOMAIN, JWT_TTL_DAYS, JWT_SECRET)
provides:
  - app.core.dual_auth.DualAuthMiddleware (cookie + bearer dual-auth resolution)
  - app.core.dual_auth.PUBLIC_ALLOWLIST (13 paths locked from MID-03)
  - app.core.dual_auth._logout_clear_cookies (DRY helper for /auth/logout, plan 13-03)
  - app.core.csrf_middleware.CsrfMiddleware (double-submit on cookie state-mutating)
  - app.api.dependencies.get_authenticated_user (Depends() for protected routes)
  - app.api.dependencies.get_current_user_id (int convenience)
  - app.api.dependencies.get_csrf_service / get_key_service / get_auth_service / get_rate_limit_service
affects:
  - app/api/dependencies.py (+5 helpers, +2 imports — auth + Request/HTTPException)
tech-stack:
  added: []
  patterns:
    - request.state.{user, plan_tier, auth_method, api_key_id} as single source of auth context (DRT)
    - Resolution order: bearer → cookie → public-allowlist → 401 (CONTEXT §50)
    - Bearer wins when both presented
    - Sliding-refresh JWT on every cookie-authenticated request (AUTH-04)
    - Single 401 shape (no leg-level leak) — T-13-05
    - Logging discipline: only auth_method+user_id; never raw token / plaintext key (T-13-04)
    - Pure middleware classes — NOT yet wired into app/main.py (plan 13-09)
key-files:
  created:
    - app/core/dual_auth.py
    - app/core/csrf_middleware.py
    - tests/unit/core/test_dual_auth.py
    - tests/unit/core/test_csrf_middleware.py
  modified:
    - app/api/dependencies.py
decisions:
  - PUBLIC_ALLOWLIST extended with PUBLIC_PREFIXES tuple (`/static/`, `/uploads/files/`) so static asset and TUS upload paths flow through DualAuthMiddleware unauthenticated; documented in module as "narrow" per plan author note
  - DualAuthMiddleware decodes cookie JWT once via jwt_codec.decode_session (recover sub) then delegates to TokenService.verify_and_refresh for token_version+sliding-refresh — never duplicates jwt logic (DRY; verifier-checked grep `jwt.decode(` returns 0)
  - WebSocket scopes bypass naturally — Starlette BaseHTTPMiddleware only dispatches HTTP scope; WS auth goes through ticket flow (plan 13-08)
  - Single 401 detail string "Authentication required" used for ALL bearer / cookie / missing-auth failures (T-13-05 mitigates information disclosure about which leg failed)
  - _logout_clear_cookies module-level helper exported so /auth/logout (plan 13-03) reuses cookie attributes (DRY — never duplicate cookie knowledge)
  - CsrfMiddleware reads `getattr(request.state, "auth_method", None)` defensively — if mounted before DualAuthMiddleware (mis-order), the None fallback still safely bypasses
  - get_authenticated_user defence-in-depth raises 401 even though DualAuthMiddleware should already 401 protected paths — guards against future middleware mis-ordering
  - get_current_user_id casts via `int(user.id)` to satisfy `int | None` typing on User.id; user.id is never None at this point (post-persist invariant)
metrics:
  duration: "~6m"
  completed: "2026-04-29"
  tasks: 2
  commits: 4
  files_changed: 5
  lines_added: 794
---

# Phase 13 Plan 02: Dual-Auth + CSRF Middleware Summary

PURE middleware classes for cookie+bearer dual-auth resolution and CSRF
double-submit enforcement — wired into `app/main.py` in plan 13-09 (atomic
flip with route registration). Built behind no feature flag at this layer;
the V2_ENABLED flag gates registration in plan 13-09 only. All Phase 13
routes (auth, keys, account, billing, scoped tasks) consume
`request.state.user` populated by DualAuthMiddleware via
`Depends(get_authenticated_user)`.

## What Was Built

### Task 1: DualAuthMiddleware — `app/core/dual_auth.py` (214 lines)

Class `DualAuthMiddleware(BaseHTTPMiddleware)` plus 4 module helpers:

| Symbol | Purpose |
| --- | --- |
| `PUBLIC_ALLOWLIST` (tuple, 13 paths) | Locked from MID-03 — `/health`, `/health/live`, `/health/ready`, `/`, `/openapi.json`, `/docs`, `/redoc`, `/static`, `/favicon.ico`, `/auth/register`, `/auth/login`, `/ui/login`, `/ui/register` |
| `PUBLIC_PREFIXES` (tuple) | `/static/`, `/uploads/files/` — narrow prefix-match for nested routes |
| `SESSION_COOKIE`, `CSRF_COOKIE`, `BEARER_PREFIX` | Module constants — single source of cookie/header names |
| `_is_public(path) -> bool` | Public-allowlist test; flat returns; no nested-if |
| `_unauthorized() -> JSONResponse` | Single 401 shape: `{"detail": "Authentication required"}` + `WWW-Authenticate: Bearer realm="whisperx"` |
| `_set_state_anonymous(request)` | Stamps `request.state.{user, plan_tier, auth_method, api_key_id} = None` for public paths |
| `_logout_clear_cookies(response)` | DRY helper for `/auth/logout` (plan 13-03 consumer) — clears both `session` + `csrf_token` cookies with matching path |

`DualAuthMiddleware.dispatch` order:

1. `OPTIONS` → pass-through (CORS preflight).
2. `Authorization: Bearer <plaintext>` → `_dispatch_bearer`:
   - `KeyService.verify_plaintext(plaintext)` — typed exceptions (`InvalidApiKeyFormatError`, `InvalidApiKeyHashError`) → 401.
   - `user_repository.get_by_id(api_key.user_id)` — `None` → 401.
   - Sets `request.state.user`, `plan_tier`, `auth_method='bearer'`, `api_key_id`.
3. `Cookie session=<jwt>` → `_dispatch_cookie`:
   - `jwt_codec.decode_session(token)` — typed exceptions (`JwtExpiredError`, `JwtAlgorithmError`, `JwtTamperedError`) collapse to 401 (T-13-05).
   - `user_repository.get_by_id(int(payload['sub']))` — `None` → 401.
   - `TokenService.verify_and_refresh(token, user.token_version)` — token-version mismatch raises `JwtTamperedError` → 401 (T-13-03).
   - Sets `request.state.user`, `plan_tier`, `auth_method='cookie'`, `api_key_id=None`.
   - Sliding refresh: `_set_session_cookie(response, new_token)` re-issues `session=<new_jwt>` with refreshed `exp` on every authenticated cookie request (AUTH-04).
4. `_is_public(request.url.path)` → pass-through with `_set_state_anonymous`.
5. Else → `_unauthorized()`.

Constraints hit:
- DRY: never parses JWTs or API keys directly — delegates to `jwt_codec.decode_session` (recover `sub` only) + `TokenService.verify_and_refresh` + `KeyService.verify_plaintext`.
- SRP: auth resolution only. No DB writes (other than `KeyService.mark_used` inside `verify_plaintext`), no business logic.
- No nested-if (`grep -cE "^\s+if .*\bif\b" app/core/dual_auth.py` = 0).
- No direct `jwt.decode(` calls (`grep -c "jwt.decode(" app/core/dual_auth.py` = 0).
- WebSocket scopes (`scope["type"] == "websocket"`) bypass naturally — Starlette `BaseHTTPMiddleware` only dispatches HTTP; documented in module docstring.
- Logging discipline: only `auth_method=, user_id=` at DEBUG level; never raw token, never plaintext key (T-13-04). Verified by `test_logger_does_not_emit_raw_token`.

### Task 2a: CsrfMiddleware — `app/core/csrf_middleware.py` (69 lines)

Class `CsrfMiddleware(BaseHTTPMiddleware)` plus module constants:

| Symbol | Value |
| --- | --- |
| `STATE_MUTATING_METHODS` | `frozenset({"POST", "PUT", "PATCH", "DELETE"})` |
| `CSRF_COOKIE` | `"csrf_token"` |
| `CSRF_HEADER` | `"x-csrf-token"` |
| `_csrf_error(detail)` | 403 JSON helper |

`dispatch` flat-guard sequence:

1. method not in `STATE_MUTATING_METHODS` → pass-through (GET/HEAD/OPTIONS bypass).
2. `getattr(request.state, "auth_method", None) != "cookie"` → pass-through (bearer + public allowlist skip CSRF — `request.state.auth_method == 'bearer'` or `None`).
3. Missing `X-CSRF-Token` header → 403 `{"detail": "CSRF token missing"}`.
4. `CsrfService.verify(cookie_token, header_token)` returns `False` → 403 `{"detail": "CSRF token mismatch"}`.
5. Else → pass-through.

Wired AFTER DualAuthMiddleware in plan 13-09 so `request.state.auth_method` is populated. Defensive `getattr(..., None)` guards against accidental misordering.

### Task 2b: `app/api/dependencies.py` extension

Five new auth helpers appended (preserves existing 7 helpers):

| Helper | Returns | Use |
| --- | --- | --- |
| `get_authenticated_user(request)` | `User` | `Depends()` on every protected route; raises 401 if state empty (defence-in-depth) |
| `get_current_user_id(request)` | `int` | Convenience for routes needing only the id |
| `get_csrf_service()` | `CsrfService` (singleton) | `/auth/login` + `/auth/register` issue tokens |
| `get_key_service()` | `KeyService` (factory; fresh DB session) | `/api/keys/*` routes |
| `get_auth_service()` | `AuthService` (factory; fresh DB session) | `/auth/*` routes |
| `get_rate_limit_service()` | `RateLimitService` (factory; fresh DB session) | Free-tier gates + anti-DDOS |

Imports added: `fastapi.HTTPException, Request, status`; `app.domain.entities.user.User`; `app.services.auth.{AuthService, CsrfService, KeyService, RateLimitService}`.

### Task 2c: Tests — `tests/unit/core/test_csrf_middleware.py` (186 lines)

11 CsrfMiddleware tests + 3 dependency tests (14 total):

- GET with cookie auth + no header → 200 (CSRF only on state-mutating)
- POST cookie auth + valid X-CSRF-Token → 200
- POST cookie auth + missing X-CSRF-Token → 403 with `"CSRF token missing"`
- POST cookie auth + mismatched header → 403 with `"CSRF token mismatch"`
- POST bearer auth (no header) → 200 (skip)
- PUT/PATCH/DELETE under cookie auth → 403 (parametrized)
- OPTIONS → not 403 (bypass)
- Public allowlist (auth_method=None) POST → 200 (bypass)
- HEAD on cookie auth → not 403 (bypass)
- `get_authenticated_user(request_with_user)` returns User
- `get_authenticated_user(request_no_user)` raises HTTPException(401)
- `get_current_user_id` returns int

A tiny `_StateInjector` middleware mounted before CsrfMiddleware injects `request.state.auth_method` so the unit tests don't depend on DualAuthMiddleware (proper unit-test isolation).

### Tests — `tests/unit/core/test_dual_auth.py` (325 lines)

15 DualAuthMiddleware tests (exceeds plan target of ≥10):

| # | Test | What it proves |
| -- | --- | --- |
| 1 | `test_public_health_passes_without_auth` | `/health` allowlist; `request.state` set to None |
| 2 | `test_public_auth_register_passes_without_auth` | `/auth/register` POST passes |
| 3 | `test_options_preflight_passes` | `OPTIONS` is exempt |
| 4 | `test_bearer_valid_sets_request_state` | `auth_method='bearer'`, `user.id`, `plan_tier`, `api_key_id` populated |
| 5 | `test_bearer_malformed_returns_401` | `InvalidApiKeyFormatError` → 401 |
| 6 | `test_bearer_unknown_returns_401` | `InvalidApiKeyHashError` → 401 |
| 7 | `test_cookie_valid_sets_state_and_refreshes_cookie` | `auth_method='cookie'`; `Set-Cookie: session=...` present (sliding refresh) |
| 8 | `test_cookie_expired_returns_401` | `JwtExpiredError` collapses to 401 |
| 9 | `test_cookie_tampered_returns_401` | `JwtTamperedError` collapses to 401 |
| 10 | `test_cookie_token_version_mismatch_returns_401` | `TokenService` raises → 401 |
| 11 | `test_cookie_user_missing_returns_401` | user_repository miss → 401 |
| 12 | `test_bearer_wins_when_both_present` | bearer + cookie both present → bearer wins |
| 13 | `test_no_auth_on_protected_path_returns_401` | bare protected request → 401 + `WWW-Authenticate` |
| 14 | `test_bearer_with_no_user_for_key_returns_401` | api_key references non-existent user → 401 |
| 15 | `test_logger_does_not_emit_raw_token` | T-13-04 — caplog scrubbing assertion |

Mocking: `_settings_stub` patches `app.core.dual_auth.get_settings` to return a known JWT secret + cookie attrs; `_build_container` returns a `MagicMock()` whose `key_service`, `token_service`, `user_repository` providers behave like the real ones for happy paths and raise the documented typed exceptions for failure paths.

## Verification

Final automated gates — all green:

```
$ .venv/Scripts/python -m pytest tests/unit/core/test_dual_auth.py tests/unit/core/test_csrf_middleware.py -v
============================== 29 passed ==============================

$ .venv/Scripts/python -m pytest tests/unit/core/ tests/unit/api/test_exception_handlers.py tests/unit/services/auth/
============================== 136 passed (regression-free) ============================

$ .venv/Scripts/python -c "from app.core.dual_auth import DualAuthMiddleware; from app.core.csrf_middleware import CsrfMiddleware"
[ok]
```

Acceptance grep counts (Plan 13-02 acceptance_criteria):

| Pattern                                                  | Expected | Actual |
| -------------------------------------------------------- | -------- | ------ |
| `class DualAuthMiddleware` in dual_auth.py               | 1        | 1      |
| `PUBLIC_ALLOWLIST` mentions in dual_auth.py              | ≥2       | 3      |
| `/auth/register` in dual_auth.py                         | ≥1       | 1      |
| `/auth/login` in dual_auth.py                            | ≥1       | 1      |
| `auth_method.*"bearer"` in dual_auth.py                  | ≥1       | 1      |
| `auth_method.*"cookie"` in dual_auth.py                  | ≥1       | 1      |
| `set_cookie` in dual_auth.py                             | ≥1       | 1      |
| nested `if .* if` in dual_auth.py                        | 0        | 0      |
| `jwt.decode(` in dual_auth.py                            | 0        | 0      |
| direct `import jwt` in dual_auth.py                      | 0        | 0      |
| `class CsrfMiddleware` in csrf_middleware.py             | 1        | 1      |
| `STATE_MUTATING_METHODS` in csrf_middleware.py           | ≥1       | 2      |
| `auth_method != "cookie"` in csrf_middleware.py          | 1        | 1      |
| nested `if .* if` in csrf_middleware.py                  | 0        | 0      |
| `def get_authenticated_user` in dependencies.py          | 1        | 1      |
| `def get_current_user_id` in dependencies.py             | 1        | 1      |
| `def get_csrf_service` in dependencies.py                | 1        | 1      |
| `def get_key_service` in dependencies.py                 | 1        | 1      |
| `def get_auth_service` in dependencies.py                | 1        | 1      |
| `def get_rate_limit_service` in dependencies.py          | 1        | 1      |

Test counts:
- DualAuthMiddleware: 15 unit tests (plan: ≥10).
- CsrfMiddleware + dependencies: 14 unit tests (plan: ≥9 + 2).
- **Total Phase 13-02 tests: 29 (plan ≥19, exceeds by 50%).**

## Public-Allowlist Contents (locked from MID-03)

```
/health
/health/live
/health/ready
/
/openapi.json
/docs
/redoc
/static
/favicon.ico
/auth/register
/auth/login
/ui/login
/ui/register
```

Plus PUBLIC_PREFIXES (prefix-match): `/static/`, `/uploads/files/`.

## request.state Contract (the SINGLE source of auth context)

| Attribute | Bearer auth | Cookie auth | Public path | Description |
| --- | --- | --- | --- | --- |
| `request.state.user` | `User` | `User` | `None` | Authenticated user entity |
| `request.state.plan_tier` | `user.plan_tier` | `user.plan_tier` | `None` | trial/free/pro/team |
| `request.state.auth_method` | `"bearer"` | `"cookie"` | `None` | Resolution leg used |
| `request.state.api_key_id` | `api_key.id` (int) | `None` | `None` | For audit logs / scoping |

All Phase 13 routes (auth, keys, account, billing, scoped tasks) read this contract via `Depends(get_authenticated_user)` — never parse `Authorization` or session cookie directly (DRT enforced).

## Dependencies API Surface (5 new helpers)

```python
from app.api.dependencies import (
    get_authenticated_user,   # Depends() on protected routes
    get_current_user_id,      # int convenience
    get_csrf_service,         # CsrfService singleton
    get_key_service,          # KeyService factory (fresh DB session)
    get_auth_service,         # AuthService factory
    get_rate_limit_service,   # RateLimitService factory
)
```

## Threat Mitigations Applied

| Threat ID | Mitigation |
| --- | --- |
| T-13-01 (spoofing — bearer) | KeyService.verify_plaintext uses indexed prefix + `secrets.compare_digest` on SHA-256 hash; typed exception → single 401 |
| T-13-02 (spoofing — cookie) | `jwt_codec.decode_session` enforces `algorithms=["HS256"]`; tampered/expired/wrong-alg → typed exception → 401 |
| T-13-03 (replay — token_version) | TokenService.verify_and_refresh compares `payload['ver']` against `user.token_version`; mismatch → JwtTamperedError → 401 |
| T-13-04 (logging) | DualAuthMiddleware logs only `auth_method=, user_id=` at DEBUG; never raw token / plaintext (verified by test_logger_does_not_emit_raw_token) |
| T-13-05 (info disclosure on 401) | Single error string `"Authentication required"` for ALL 401 paths — no enumeration of which leg failed |
| T-13-06 (CSRF cross-site write) | CsrfMiddleware verifies double-submit on cookie POST/PUT/PATCH/DELETE via `secrets.compare_digest` (CsrfService.verify) |
| T-13-07 (DoS — DB lookup per request) | accept (KEY-08 idx_api_keys_prefix + user_repository.get_by_id PK lookup — both O(1)) |

## Deviations from Plan

None — plan executed exactly as written.

The plan body included an explicit author note about `/static/` + `/uploads/files/` prefix-match (`# tus uploads need own auth via dual middleware too — keep narrow`); preserved verbatim as `PUBLIC_PREFIXES` tuple. TUS upload routes will get their own auth via DualAuthMiddleware request.state in plan 13-04 / 13-09 (route registration phase).

No architectural deviations, no auto-fixes triggered, no auth gates encountered.

## Commits

| # | Hash       | Type  | Message                                                                  |
| - | ---------- | ----- | ------------------------------------------------------------------------ |
| 1 | `97672f4`  | test  | add failing tests for DualAuthMiddleware (RED)                          |
| 2 | `3ca7869`  | feat  | implement DualAuthMiddleware (GREEN)                                    |
| 3 | `b893ddb`  | test  | add failing tests for CsrfMiddleware + auth dependencies (RED)          |
| 4 | `9c512d0`  | feat  | implement CsrfMiddleware + auth dependencies (GREEN)                    |

TDD discipline: per-task RED → GREEN gate sequence (4 commits for 2 tasks).

## Requirements Marked Complete

- **MID-01** — DualAuthMiddleware accepts both `Authorization: Bearer whsk_*` and cookie `session=<jwt>` (resolution order: bearer → cookie)
- **MID-02** — CsrfMiddleware enforces double-submit on cookie+state-mutating; bearer skips
- **MID-03** — PUBLIC_ALLOWLIST tuple locked (13 paths) + `/static/`, `/uploads/files/` prefix-match
- **MID-04** — request.state.{user, plan_tier, auth_method, api_key_id} contract; sliding-refresh cookie
- **AUTH-04** — sliding-refresh JWT (`_set_session_cookie` re-issues with refreshed exp on every authenticated cookie request)

Note: MID-01..04 + AUTH-04 are marked **complete at the middleware-layer**; their HTTP enforcement requires wiring in plan 13-09 (atomic flip with route registration). The PLAN frontmatter declared this plan delivers the pure middleware surface.

## Self-Check

Files created exist:
- `app/core/dual_auth.py` → FOUND (214 lines)
- `app/core/csrf_middleware.py` → FOUND (69 lines)
- `tests/unit/core/test_dual_auth.py` → FOUND (325 lines, 15 tests)
- `tests/unit/core/test_csrf_middleware.py` → FOUND (186 lines, 14 tests)

Files modified:
- `app/api/dependencies.py` → MODIFIED (+5 helpers, +imports)

Commits exist:
- `97672f4` → FOUND (RED dual_auth)
- `3ca7869` → FOUND (GREEN dual_auth)
- `b893ddb` → FOUND (RED csrf_middleware + deps)
- `9c512d0` → FOUND (GREEN csrf_middleware + deps)

## Self-Check: PASSED
