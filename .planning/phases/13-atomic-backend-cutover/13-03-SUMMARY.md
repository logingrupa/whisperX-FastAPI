---
phase: 13-atomic-backend-cutover
plan: 03
subsystem: backend-routes
tags: [auth, fastapi, slowapi, rate-limiting, anti-enumeration, anti-spam, csrf, cookie-session]
requires:
  - phase: 13-01
    provides: data/disposable-emails.txt blocklist data; AuthSettings.{V2_ENABLED, COOKIE_SECURE, COOKIE_DOMAIN, JWT_TTL_DAYS, TRUST_CF_HEADER}; slowapi 0.1.9 dep
  - phase: 13-02
    provides: get_auth_service / get_csrf_service / get_authenticated_user dependencies; CsrfMiddleware (consumed in plan 13-09); _logout_clear_cookies helper pattern
  - phase: 11
    provides: AuthService.register/login signatures + InvalidCredentialsError + UserAlreadyExistsError; TokenService.issue; CsrfService.issue
provides:
  - app.api.auth_routes.auth_router with POST /auth/register, /auth/login, /auth/logout
  - app.api.schemas.auth_schemas.{RegisterRequest, LoginRequest, AuthResponse}
  - app.core.disposable_email.is_disposable + DISPOSABLE_DOMAINS frozenset (5413 entries; O(1) lookup)
  - app.core.rate_limiter.{limiter, _client_subnet_key, rate_limit_handler} — slowapi singleton with /24/64 subnet key_func
  - app.api.exception_handlers.invalid_credentials_handler — maps InvalidCredentialsError to HTTP 401
  - tests/integration/test_auth_routes.py — 12 integration tests
affects:
  - plan 13-09 (atomic flip): mounts auth_router under is_auth_v2_enabled() guard; registers RateLimitExceeded + ValidationError + InvalidCredentialsError handlers; mounts limiter on app.state
  - phase 14 frontend: consumes /auth/register, /auth/login, /auth/logout + Set-Cookie session/csrf_token contract
tech-stack:
  added:
    - email-validator>=2.0.0 (transitive of pydantic[email] required by EmailStr)
  patterns:
    - Anti-enumeration via identical body+code on disposable + duplicate registration legs (T-13-09)
    - Anti-enumeration via shared InvalidCredentialsError on wrong-email + wrong-password (T-13-10)
    - Slowapi /24 IPv4 + /64 IPv6 subnet key_func for register/login throttles (CONTEXT §107)
    - 429 responses include Retry-After header (RATE-12)
    - Module-load frozenset blocklist read from bundled data file (DRY single load site)
    - Cookie attrs read from settings.auth.* (COOKIE_SECURE, COOKIE_DOMAIN, JWT_TTL_DAYS) — single source
    - Slim FastAPI test app (no main.py legacy middleware) + per-test Container override pattern for integration tests
key-files:
  created:
    - app/core/disposable_email.py
    - app/core/rate_limiter.py
    - app/api/schemas/auth_schemas.py
    - app/api/auth_routes.py
    - tests/integration/test_auth_routes.py
  modified:
    - app/api/exception_handlers.py (add invalid_credentials_handler)
    - pyproject.toml (add email-validator>=2.0.0)
key-decisions:
  - "Cookie-clear in /auth/logout sets Set-Cookie deletions on the SAME Response that's returned (FastAPI ignores injected Response when explicit Response is returned — discovered via test, fixed inline)"
  - "Registration auto-logs-in: success returns 201 + session/csrf cookies (no separate login round trip required)"
  - "Anti-enumeration via shared private constants _REGISTRATION_FAILED_MESSAGE / _CODE — single source for the canonical generic body across disposable + duplicate legs"
  - "Slowapi limiter is a module-level singleton (app.core.rate_limiter.limiter) — wired onto app.state in plan 13-09; @limiter.limit decorators on routes reference the same instance (no second Limiter)"
  - "_client_subnet_key resolves CF-Connecting-IP first only when AUTH__TRUST_CF_HEADER=true; ipaddress lib normalizes to /24 (IPv4) or /64 (IPv6) network address"
  - "limiter.reset() called in test fixture setup AND teardown so 3/hr + 10/hr counters are fresh per-test (avoids cross-test contamination from in-memory bucket)"
  - "Test app uses providers.Factory(TestSession) override (not bare TestSession) so each route call gets a fresh Session — matches Container.db_session_factory = providers.Factory(SessionLocal) shape"
patterns-established:
  - "Anti-enumeration: identical user-facing body+code on different rejection legs — disposable / duplicate / wrong-email / wrong-password all converge to single canonical error"
  - "DRY cookie helpers: _set_auth_cookies(response, session_token, csrf_token) + _clear_auth_cookies(response) — every auth route + future plans (13-04 keys, 13-08 ws ticket) reuse"
  - "Integration test isolation: per-test Container instance + providers.Factory override + limiter.reset() — never touch the module-global Container state"
requirements-completed:
  - AUTH-01 (registration with email/password)
  - AUTH-03 (login with cookie session)
  - AUTH-05 (logout clears session)
  - AUTH-07 (mailto:hey@logingrupa.lv password reset hint surfaced in OpenAPI)
  - ANTI-01 (register 3/hr/IP/24)
  - ANTI-02 (login 10/hr/IP/24)
  - ANTI-04 (disposable-email blocklist enforced at register)
duration: ~17 min
completed: 2026-04-29
---

# Phase 13 Plan 03: Auth Routes (register/login/logout) Summary

POST /auth/register, /auth/login, /auth/logout endpoints + slowapi 3/hr (register) + 10/hr (login) IP /24 throttles + disposable-email blocklist + anti-enumeration error parity, behind 12 passing integration tests.

## Performance

- **Duration:** ~17 min
- **Started:** 2026-04-29T13:05:00Z
- **Completed:** 2026-04-29T13:22:00Z
- **Tasks:** 3
- **Files created:** 5
- **Files modified:** 2

## Accomplishments

- 3 cookie-based auth endpoints exposed on `auth_router` (mounted under `is_auth_v2_enabled()` guard in plan 13-09)
- Slowapi 0.1.9 wired with CF-Connecting-IP-aware /24/64 subnet `key_func`; `Retry-After` header on every 429
- Disposable-email blocklist (5413 domains) loaded once at module import as `frozenset[str]`; O(1) `is_disposable()` lookup
- Anti-enumeration parity verified by integration test: disposable + duplicate registration return identical body+code; wrong-email + wrong-password login return identical body+code
- `InvalidCredentialsError → 401` exception handler defined (registration in plan 13-09)
- 12 integration tests cover happy paths, anti-enumeration parity (both legs), rate limiting (3/hr + 10/hr), disposable-email rejection, weak-password rejection, idempotent logout, and OpenAPI mailto AUTH-07 hint

## Task Commits

1. **Task 1: disposable_email loader + auth_schemas + slowapi limiter** — `5a814ff` (feat)
2. **Task 2: auth_routes (register/login/logout) + InvalidCredentials handler** — `0bad87c` (feat)
3. **Task 3: Integration tests + logout cookie-clear bug fix** — `b77962b` (test)

## Files Created/Modified

### Created

- `app/core/disposable_email.py` (50 lines) — Module-load frozenset reader of `data/disposable-emails.txt`; `is_disposable(email)` lowercases domain and tests membership; fail-soft on missing file
- `app/core/rate_limiter.py` (95 lines) — `limiter = Limiter(key_func=_client_subnet_key, default_limits=[])` singleton; `_client_subnet_key` resolves CF-Connecting-IP/X-Forwarded-For (gated on `AUTH__TRUST_CF_HEADER`) then groups IPv4→/24 and IPv6→/64 via `ipaddress.ip_network`; `rate_limit_handler` formats 429 JSON with `Retry-After` extracted from slowapi's detail string
- `app/api/schemas/auth_schemas.py` (40 lines) — Pydantic v2 `RegisterRequest` (`EmailStr` + 8-128 char password), `LoginRequest` (1-128 char password), `AuthResponse` (`user_id` + `plan_tier`)
- `app/api/auth_routes.py` (170 lines) — `auth_router = APIRouter(prefix="/auth", tags=["Authentication"])`; `_set_auth_cookies` + `_clear_auth_cookies` DRY helpers reading `settings.auth.{COOKIE_SECURE,COOKIE_DOMAIN,JWT_TTL_DAYS}`; `_registration_failed()` factory for the canonical anti-enumeration `ValidationError`
- `tests/integration/test_auth_routes.py` (315 lines, 12 cases) — Slim FastAPI app per test (`auth_app` fixture); `tmp_db_url` fixture creates per-test SQLite + `Base.metadata.create_all`; Container override via `providers.Factory(sessionmaker(bind=tmp_engine))`; `limiter.reset()` in setup AND teardown

### Modified

- `app/api/exception_handlers.py` — Imported `InvalidCredentialsError`; appended `invalid_credentials_handler(request, exc)` mapping to HTTP 401 with the exception's `to_dict()` body and structured logging
- `pyproject.toml` — Pinned `email-validator>=2.0.0` so pydantic `EmailStr` validates without `ImportError`

## Verification

### Acceptance Grep Gates

| Gate | Expected | Actual |
| ---- | -------- | ------ |
| `DISPOSABLE_DOMAINS` in disposable_email.py | ≥2 | 2 |
| `frozenset` in disposable_email.py | ≥1 | 6 |
| `RegisterRequest\|LoginRequest` in auth_schemas.py | ≥2 | 2 |
| `limiter = Limiter` in rate_limiter.py | 1 | 1 |
| `_client_subnet_key` in rate_limiter.py | ≥2 | 2 |
| `/24\|/64` in rate_limiter.py | ≥2 | 8 |
| `Retry-After` in rate_limiter.py | ≥1 | 2 |
| `@limiter.limit("3/hour")` in auth_routes.py | 1 | 1 |
| `@limiter.limit("10/hour")` in auth_routes.py | 1 | 1 |
| `hey@logingrupa.lv` in auth_routes.py | ≥1 | 2 |
| `is_disposable` in auth_routes.py | ≥1 | 2 |
| `_set_auth_cookies\|_clear_auth_cookies` in auth_routes.py | ≥4 | 6 |
| `Registration failed` in auth_routes.py | ≥2 | 2 |
| `def invalid_credentials_handler` in exception_handlers.py | 1 | 1 |
| nested-if (`^\s+if .*\bif\b`) in disposable_email.py + rate_limiter.py + auth_routes.py | 0 | 0 |
| `@pytest.mark.integration` in test_auth_routes.py | ≥10 | 12 |
| Test names matching plan list | ≥10 | 10 |
| `Retry-After` in test_auth_routes.py | ≥1 | 5 |
| `Registration failed` in test_auth_routes.py | ≥2 | 4 |

### Test Outcomes

```
$ pytest tests/integration/test_auth_routes.py -v -m integration
12 passed in 1.91s
```

| # | Test | Status |
| - | ---- | ------ |
| 1 | test_register_happy_path | PASS |
| 2 | test_register_duplicate_email_generic_error | PASS |
| 3 | test_register_disposable_email_rejected | PASS |
| 4 | test_register_weak_password_rejected | PASS |
| 5 | test_register_rate_limit_3_per_hour | PASS |
| 6 | test_login_happy_path | PASS |
| 7 | test_login_wrong_email_returns_401_generic | PASS |
| 8 | test_login_wrong_password_returns_401_same_shape | PASS |
| 9 | test_login_rate_limit_10_per_hour | PASS |
| 10 | test_logout_clears_cookies | PASS |
| 11 | test_logout_idempotent | PASS |
| 12 | test_password_reset_hint_in_openapi | PASS |

### Regression

```
$ pytest tests/unit/core tests/unit/api tests/unit/services/auth -q
142 passed in 2.38s
```

(Pre-existing collection failures in `tests/unit/domain` + `tests/unit/infrastructure` from missing `factory_boy` are out of scope — unchanged from before this plan.)

## Decisions Made

- **logout returns a fresh Response (not the injected one)** — discovered via failing `test_logout_clears_cookies`. FastAPI discards cookies set on the injected `Response` parameter when an explicit `Response` is returned from the handler. Fix: build the deletion-bearing `Response` as the return value itself.
- **Auto-login on register** — `/auth/register` issues session + CSRF cookies on success so the frontend doesn't need a second `/auth/login` round trip after sign-up.
- **Slowapi singleton imported by routes** — `@limiter.limit("3/hour")` decorators on `register`/`login` reference the module-level `limiter` from `app.core.rate_limiter`. Plan 13-09 will mount the same instance onto `app.state.limiter`.
- **In-memory storage acceptable for v1.2** — slowapi's default leaky bucket is per-process. Single-worker dev/prod deploys (the v1.2 target) are protected; multi-worker would require redis/limits storage swap, deferred to phase 18.
- **`providers.Factory(TestSession)` override pattern in tests** — matches `Container.db_session_factory = providers.Factory(SessionLocal)` shape so each route call constructs a fresh Session via the sessionmaker.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] /auth/logout did not emit Set-Cookie deletion headers**
- **Found during:** Task 3 (test_logout_clears_cookies failed with `assert 'session=' in ''`)
- **Issue:** The route signature took an injected `Response` parameter and called `_clear_auth_cookies(response)`, then returned `Response(status_code=204)`. FastAPI ignores the injected Response when the handler explicitly returns a different Response — so the deletion `Set-Cookie` headers were dropped on the wire.
- **Fix:** Removed the injected `response` parameter; built the deletion-bearing Response as the return value: `response = Response(status_code=204); _clear_auth_cookies(response); return response`.
- **Files modified:** `app/api/auth_routes.py` (logout function only)
- **Verification:** `test_logout_clears_cookies` now passes; response Set-Cookie headers contain both `session=` + `csrf_token=` with `max-age=0`.
- **Committed in:** `b77962b` (Task 3 commit, alongside the integration test that caught it)

**2. [Rule 3 - Blocking] email-validator missing for pydantic EmailStr**
- **Found during:** Task 1 (`from pydantic import EmailStr` triggered Pydantic to attempt loading email-validator at field validation time)
- **Issue:** `email-validator` is not installed by pydantic core; without it `EmailStr` fields raise on validation.
- **Fix:** Installed `email-validator==2.3.0` into `.venv` and pinned `email-validator>=2.0.0` in `pyproject.toml [project].dependencies`.
- **Files modified:** `pyproject.toml`
- **Verification:** `RegisterRequest(email='a@b.com', password='supersecret123')` constructs cleanly; integration test_register_happy_path passes.
- **Committed in:** `5a814ff` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 Rule 1 bug, 1 Rule 3 blocking)
**Impact on plan:** Both auto-fixes essential for correctness. Logout fix is not architectural — same logic, different return-value plumbing. email-validator pin matches the plan's own foreseen action ("If install fails, add `email-validator>=2.0.0` to pyproject.toml").

## Issues Encountered

- Pre-existing collection errors in `tests/unit/domain` + `tests/unit/infrastructure` from missing `factory_boy` package — out of scope, untouched.

## Threat Mitigations Applied

| Threat ID | Mitigation |
| --------- | ---------- |
| T-13-08 (email-harvest spoofing) | `is_disposable()` rejects 5413 known throwaway domains at /auth/register; module-load frozenset (O(1) check) |
| T-13-09 (registration enumeration) | Identical 422 body `{message: "Registration failed", code: "REGISTRATION_FAILED"}` on disposable + duplicate legs; verified by integration test |
| T-13-10 (login enumeration) | `AuthService.login` raises `InvalidCredentialsError` on either wrong-email or wrong-password (carry-over from Phase 11); route emits identical 401 body; integration test compares both legs byte-for-byte (excluding correlation_id) |
| T-13-11 (register DoS) | `@limiter.limit("3/hour")` keyed on /24 subnet; 4th attempt returns 429 with Retry-After |
| T-13-12 (login brute-force) | `@limiter.limit("10/hour")` keyed on /24 subnet; 11th attempt returns 429 with Retry-After |
| T-13-13 (sensitive logging) | Logger emits event labels only ("Registration rejected disposable_domain", "Login rejected invalid_credentials"); never email or password |
| T-13-14 (cookie tampering) | `secure=settings.auth.COOKIE_SECURE` + production-safety guard from Plan 13-01 refuses boot if V2_ENABLED=true with COOKIE_SECURE=false |

## User Setup Required

None — all changes are server-side. The `email-validator` dep is auto-installed via `pip install -e .` (pinned in pyproject.toml).

## Next Phase Readiness

- `auth_router` is built but **NOT yet mounted** on `app/main.py`. Plan 13-09 (atomic flip) handles wiring under `is_auth_v2_enabled()` guard, plus exception-handler registration and `app.state.limiter`.
- Cookie attribute lock (CONTEXT §60-67) honored — same `_set_auth_cookies` helper will be called by `/api/keys/*` future routes (plan 13-04) and `/api/ws/ticket` (plan 13-08) without code duplication.
- `_logout_clear_cookies` exists in BOTH `app/core/dual_auth.py` (from 13-02) and `app/api/auth_routes.py` (from 13-03 as `_clear_auth_cookies`). They're functionally equivalent (both clear `session` + `csrf_token` with `path="/"`); the one in dual_auth predates the route module so the route owns its own copy. Plan 13-09 may consolidate.

## Self-Check

Files created exist:
- `app/core/disposable_email.py` → FOUND
- `app/core/rate_limiter.py` → FOUND
- `app/api/schemas/auth_schemas.py` → FOUND
- `app/api/auth_routes.py` → FOUND
- `tests/integration/test_auth_routes.py` → FOUND

Files modified:
- `app/api/exception_handlers.py` → MODIFIED (invalid_credentials_handler appended)
- `pyproject.toml` → MODIFIED (email-validator>=2.0.0 added)

Commits exist:
- `5a814ff` → FOUND (Task 1)
- `0bad87c` → FOUND (Task 2)
- `b77962b` → FOUND (Task 3 + logout fix)

---
*Phase: 13-atomic-backend-cutover*
*Completed: 2026-04-29*
