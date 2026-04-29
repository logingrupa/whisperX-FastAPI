---
phase: 13-atomic-backend-cutover
plan: 09
subsystem: backend-atomic-cutover
tags: [middleware-stack, dual-auth, csrf, cors-lockdown, atomic-flip, w4-fallback, slowapi-mount, exception-handlers, feature-flag, prod-safety]
requires:
  - phase: 13-01
    provides: AuthSettings (V2_ENABLED, FRONTEND_URL); is_auth_v2_enabled feature flag; production-safety model_validator
  - phase: 13-02
    provides: DualAuthMiddleware + CsrfMiddleware (cookie + bearer + double-submit)
  - phase: 13-03
    provides: auth_router (/auth/register, /auth/login, /auth/logout) + slowapi limiter + invalid_credentials_handler
  - phase: 13-04
    provides: key_router (/api/keys CRUD)
  - phase: 13-05
    provides: account_router (DELETE /api/account/data) + billing_router (501 stubs)
  - phase: 13-06
    provides: ws_ticket_router (POST /api/ws/ticket; WS ticket-validated handler)
  - phase: 13-07
    provides: per-user scoped task repository (already wired into existing task_router)
  - phase: 13-08
    provides: 4 typed exception handlers (trial_expired/free_tier_violation/rate_limit_exceeded/concurrency_limit)
provides:
  - app/main.py — Phase 13 middleware stack + 5 routers + 6 exception handlers wired behind is_auth_v2_enabled()
  - app/main.py — CORS locked to settings.auth.FRONTEND_URL with allow_credentials=True (BOTH branches)
  - app/main.py — production safety guard refusing boot when ENVIRONMENT=production AND V2_ENABLED=false
  - app/main.py — slowapi limiter mounted on app.state for @limiter.limit decorators
  - app/api/__init__.py — barrel re-exporting 5 new Phase 13 routers
  - app/core/auth.py — legacy BearerAuthMiddleware (DEPRECATED header per W4) — V2_ENABLED=false fallback retained until Phase 16+
affects:
  - phase 14 frontend cutover — relies on V2_ENABLED=true serving /auth/*, /api/keys, /api/account/data, /api/ws/ticket
  - phase 16 verification — must add cross-user / JWT-attack matrix tests against the wired stack
  - phase 16+ cleanup ticket — schedule deletion of app/core/auth.py and the V2-OFF else-branch once V2 is verified stable in prod

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single is_auth_v2_enabled() check at app boot decides middleware + router stack (atomic flip)"
    - "ASGI middleware reverse-order registration: CSRF → DualAuth → CORS so request flow is CORS → DualAuth → CSRF → route"
    - "CORS allowlist parsed from comma-separated FRONTEND_URL: [origin.strip() for origin in FRONTEND_URL.split(',') if origin.strip()]"
    - "Tiger-style fail-loud production guard: ENVIRONMENT=production AND V2_ENABLED=false → RuntimeError refuses boot"
    - "W4 fallback: legacy BearerAuthMiddleware retained as V2-OFF else-branch — fail-CLOSED when API_BEARER_TOKEN unset (no zero-auth window)"
    - "slowapi state mounted unconditionally (app.state.limiter) — required by @limiter.limit decorators on auth_routes regardless of V2 branch"
    - "All 6 typed exception handlers registered in BOTH branches (domain exceptions can surface from non-Phase-13 code paths too)"
key-files:
  created:
    - app/core/auth.py — legacy BearerAuthMiddleware retained as V2-OFF fallback (DEPRECATED header)
  modified:
    - app/main.py — full Phase 13 wiring (middleware stack + routers + handlers + prod guard)
    - app/api/__init__.py — barrel re-export of 5 new routers

key-decisions:
  - "[13-09]: app/core/auth.py was missing from disk (initial git status snapshot was stale) — recreated with legacy BearerAuthMiddleware + W4 deprecation header to satisfy the V2-OFF else-branch import; deletion deferred to Phase 16+"
  - "[13-09]: BearerAuthMiddleware fail-CLOSED on unset API_BEARER_TOKEN (denies all non-public traffic with 401, logs warning at boot) instead of fail-OPEN or fail-LOUD-at-import — keeps app boot succeeding for verifier scenarios while preserving zero-auth-window protection"
  - "[13-09]: CORS allow_origins parsed from comma-separated FRONTEND_URL — single string env var supports multi-origin allowlist (e.g., 'http://localhost:5173,https://app.example.com') without breaking single-origin default"
  - "[13-09]: Existing v1.1 routers (stt/task/service/websocket/streaming_upload/tus_upload) registered UNCONDITIONALLY in both branches; only the 5 Phase 13 routers are gated on is_auth_v2_enabled()"
  - "[13-09]: All 6 typed exception handlers registered in BOTH branches — domain exceptions (e.g., RateLimitExceededError from slowapi via @limiter.limit on auth routes) can surface even under V2-OFF if those routes were ever decorated"
  - "[13-09]: Comment in main.py rephrased ('NEVER use wildcard origins') to avoid the literal string 'allow_origins=[\"*\"]' tripping verifier grep gate that requires count==0"

patterns-established:
  - "Atomic-flip wiring pattern: a single feature-flag check at app boot decides BOTH middleware stack and router registration; downstream code never re-checks the flag"
  - "W4 fallback pattern: deprecated module retained as alternate branch with explicit DEPRECATED header + Phase-N+ deletion ticket (audit trail prevents indefinite drift)"
  - "Production safety guard pattern: app/main.py raises RuntimeError when env+flag combination is unsafe — surfaces config errors at deploy time, not first request"

requirements-completed: [MID-01, MID-05, ANTI-06]

# Metrics
duration: 10min
completed: 2026-04-29
---

# Phase 13 Plan 09: Atomic Backend Cutover Summary

**Phase 13 atomic flip — DualAuth+CSRF middleware + 5 Phase 13 routers + 6 typed exception handlers wired into app/main.py behind is_auth_v2_enabled(), with locked-down CORS (FRONTEND_URL allowlist + credentials) and W4 legacy BearerAuthMiddleware fallback retained for the V2-OFF else-branch.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-29T11:49:02Z
- **Completed:** 2026-04-29T11:59:08Z
- **Tasks:** 3 (Task 1 split into 1a routers + 1b auth.py recreation)
- **Files modified:** 3 (app/main.py, app/api/__init__.py, app/core/auth.py [created])

## Accomplishments

- Wired DualAuthMiddleware + CsrfMiddleware as the V2-ON middleware stack (CSRF → DualAuth → CORS registration order so request flow is CORS → DualAuth → CSRF → route)
- Wired legacy BearerAuthMiddleware as the V2-OFF else-branch (W4 — preserves dev/CI authentication during the cutover window)
- Locked CORS to `settings.auth.FRONTEND_URL` with `allow_credentials=True` in BOTH branches (T-13-42 mitigation; never wildcard origins)
- Conditionally registered 5 Phase 13 routers (auth_router, key_router, account_router, billing_router, ws_ticket_router) only when V2_ENABLED=true
- Registered 6 typed exception handlers (InvalidCredentialsError → 401, TrialExpiredError → 402, FreeTierViolationError → 403, RateLimitExceededError → 429+Retry-After, ConcurrencyLimitError → 429+Retry-After, slowapi RateLimitExceeded → 429+Retry-After)
- Mounted slowapi limiter on `app.state.limiter` (required by `@limiter.limit` decorators on auth routes)
- Production-safety boot guard: `ENVIRONMENT=production AND V2_ENABLED=false` → `RuntimeError` refuses to start
- Recreated `app/core/auth.py` (was missing from working tree but referenced as W4 fallback target) with legacy BearerAuthMiddleware + DEPRECATED header

## Middleware Stack Diagrams

### V2_ENABLED=true (Phase 13 stack — production target)

```
Request (HTTP):
  client → [CORS] → [DualAuth] → [CSRF] → route handler
                       │             │
                       │             └── enforces double-submit on
                       │                 cookie-auth POST/PUT/PATCH/DELETE
                       └── resolves Authorization: Bearer whsk_*  OR
                           cookie session=<jwt>  OR  PUBLIC_ALLOWLIST  OR
                           returns 401 {"detail": "Authentication required"}

Response: route → [CSRF] → [DualAuth (re-issues sliding cookie)] → [CORS]
```

ASGI registration order (reverse of request flow): `CsrfMiddleware → DualAuthMiddleware → CORSMiddleware`.

### V2_ENABLED=false (legacy fallback — dev/CI only; W4)

```
Request: client → [CORS] → [BearerAuthMiddleware] → route handler
                                  │
                                  └── checks Authorization: Bearer <API_BEARER_TOKEN>
                                      against env-var-loaded shared secret;
                                      PUBLIC_ALLOWLIST bypass;
                                      fail-CLOSED 401 if API_BEARER_TOKEN unset
```

ASGI registration order: `BearerAuthMiddleware → CORSMiddleware`.
Phase 13 routes (`/auth/*`, `/api/keys`, `/api/account/data`, `/billing/*`, `/api/ws/ticket`) are NOT registered.

## CORS Allowlist Sample

Input env: `AUTH__FRONTEND_URL=http://localhost:5173`
Parsed: `cors_origins = ["http://localhost:5173"]`

Multi-origin example: `AUTH__FRONTEND_URL=http://localhost:5173,https://app.example.com`
Parsed: `cors_origins = ["http://localhost:5173", "https://app.example.com"]`

CORS settings (BOTH branches):
- `allow_origins`: parsed list (NEVER wildcard)
- `allow_credentials`: `True`
- `allow_methods`: `["GET", "POST", "PUT", "DELETE", "OPTIONS"]`
- `allow_headers`: `["*"]`
- `expose_headers`: `TUS_HEADERS` (Location / Upload-Offset / Upload-Length / etc.)

## Self-Verified 5 Critical Scenarios

All 5 verification scenarios run via TestClient against `app.main:app`. Results:

| # | Scenario | Result | Evidence |
|---|----------|--------|----------|
| 1 | V2-OFF returns 401 on `/task/all` (NOT 200 — legacy BearerAuthMiddleware fallback active) | PASS | `GET /task/all` (no auth) → 401; `GET /health` → 200; `GET /auth/register` → 401 (route not registered + middleware rejects) |
| 2 | V2-ON returns 401 on protected route without auth; serves 5 Phase 13 routers; `/openapi.json` lists them | PASS | `GET /api/keys` (no auth) → 401; OpenAPI paths include `/auth/register`, `/api/keys`, `/api/account/data`, `/billing/checkout`, `/api/ws/ticket` |
| 3 | CORS preflight from `FRONTEND_URL` succeeds with `Access-Control-Allow-Credentials: true`; from random origin fails (no ACAO header) | PASS | `OPTIONS /auth/register` with `Origin: http://localhost:5173` → 200, ACAO=`http://localhost:5173`, ACAC=`true`; with `Origin: https://evil.example.com` → 400, ACAO=`None` |
| 4 | `app/core/auth.py` EXISTS (kept as fallback per W4); contains BearerAuthMiddleware (≥1) + DEPRECATED marker (==1) | PASS | `test -f app/core/auth.py` ✓; `grep -c BearerAuthMiddleware app/core/auth.py` → 3; `grep -c "DEPRECATED — RETAINED FOR ATOMIC CUTOVER FALLBACK" app/core/auth.py` → 1 |
| 5 | else-branch in middleware-stack wires BearerAuthMiddleware (V2-OFF safety net) | PASS | `app.user_middleware` under V2-OFF lists `[CORSMiddleware, BearerAuthMiddleware]` (2 middlewares); `add_middleware(BearerAuthMiddleware)` count in main.py == 1 |

Production safety guard verified: `ENVIRONMENT=production AUTH__V2_ENABLED=false` boot → `RuntimeError("Production refuses to boot with AUTH_V2_ENABLED=false …")`.

## Grep Acceptance Gate Results

| Gate | Required | Actual | Pass |
|------|----------|--------|------|
| `from app.core.auth import BearerAuthMiddleware` in main.py | ==1 | 1 | ✓ |
| `BearerAuthMiddleware` total in main.py | ≥2 | 3 | ✓ |
| `add_middleware(BearerAuthMiddleware)` in main.py | ==1 | 1 | ✓ |
| `DualAuthMiddleware` in main.py | ≥2 | 2 | ✓ |
| `CsrfMiddleware` in main.py | ≥2 | 2 | ✓ |
| `allow_origins=["*"]` (literal) in main.py | ==0 | 0 | ✓ |
| `allow_credentials=True` in main.py | ==1 | 1 | ✓ |
| `is_auth_v2_enabled` in main.py | ≥3 | 5 | ✓ |
| `FRONTEND_URL` in main.py | ≥1 | 3 | ✓ |
| Phase 13 router refs in main.py | ≥10 | 10 | ✓ |
| `RateLimitExceeded` in main.py | ≥2 | 4 | ✓ |
| Phase 13 typed exc class refs | ≥4 | 8 | ✓ |
| `Production refuses to boot` in main.py | ==1 | 1 | ✓ |
| `BearerAuthMiddleware` in app/core/auth.py | ≥1 | 3 | ✓ |
| DEPRECATED marker in app/core/auth.py | ==1 | 1 | ✓ |
| Routers exported from app/api/__init__.py | ≥10 | 10 | ✓ |

## Task Commits

1. **Task 1: Export Phase 13 routers + retain BearerAuthMiddleware fallback (W4)** — `630170f` (feat)
2. **Task 2: Atomic flip — wire DualAuth+CSRF / 5 routers / 6 handlers / locked CORS** — `1f2a721` (feat)
3. **Task 3: Human-verify checkpoint** — auto-approved in autonomous mode; all 5 scenarios self-verified inline

## Files Created/Modified

- `app/core/auth.py` — **CREATED** — Legacy BearerAuthMiddleware (DEPRECATED header per W4); fail-CLOSED when `API_BEARER_TOKEN` unset; PUBLIC_ALLOWLIST mirrors DualAuth allowlist (DRY)
- `app/main.py` — **MODIFIED** — Phase 13 wiring: feature-flag middleware stack, locked CORS, 6 exception handlers, 5 conditional routers, slowapi mount, production safety guard
- `app/api/__init__.py` — **MODIFIED** — Barrel re-export of auth_router, key_router, account_router, billing_router, ws_ticket_router

## Decisions Made

- **app/core/auth.py recreation:** Initial git status snapshot reported `?? app/core/auth.py` (untracked), but the file was actually missing from disk. The plan and W4 rule explicitly say "KEEP" the file — interpreted this as "ensure it exists with the legacy middleware so the V2-OFF else-branch can import it" rather than "do not delete what isn't there". Recreated with a minimal legacy BearerAuthMiddleware that fails CLOSED when API_BEARER_TOKEN is unset, plus the mandated DEPRECATED header.
- **Fail-CLOSED on unset token:** When `API_BEARER_TOKEN` env var is missing, BearerAuthMiddleware constructs successfully but every non-public route returns 401. Rejected fail-LOUD (raise at construction) because it would block app boot in default dev (no API_BEARER_TOKEN set), failing the verifier `python -c "from app.main import app"` smoke test. Fail-CLOSED preserves zero-auth-window protection without breaking smoke tests.
- **Existing v1.1 routers stay unconditional:** Only the 5 Phase 13 routers are gated on V2_ENABLED. `stt_router`, `task_router`, `service_router`, etc. remain registered in BOTH branches — they're authenticated by the active middleware (BearerAuth or DualAuth), not by router-level conditional registration.
- **Phase 13 exception handlers in BOTH branches:** Even under V2-OFF, code paths that import slowapi or raise typed Phase 13 exceptions could surface them. Registering all 6 handlers unconditionally is safer than conditional + risks a 500 leaking via `generic_error_handler`.
- **Comment de-literalization:** Original comment said `NEVER allow_origins=["*"]` which tripped the verifier grep gate `grep -c 'allow_origins=\["\*"\]' == 0`. Rephrased to "NEVER use wildcard origins" — preserves doc intent without satisfying the literal regex.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Recreated app/core/auth.py (was missing from disk)**
- **Found during:** Task 1
- **Issue:** Plan instructed to "KEEP" `app/core/auth.py` and add a deprecation header, but the file did not exist in the working tree (git history confirms it was never tracked — initial status snapshot showing `?? app/core/auth.py` was stale). Without the file, the V2-OFF else-branch `app.add_middleware(BearerAuthMiddleware)` would crash on import.
- **Fix:** Created `app/core/auth.py` containing a minimal legacy `BearerAuthMiddleware` (single-shared-token via `API_BEARER_TOKEN` env, fail-CLOSED behaviour, PUBLIC_ALLOWLIST mirroring DualAuth) plus the mandated `DEPRECATED — RETAINED FOR ATOMIC CUTOVER FALLBACK (W4)` header.
- **Files modified:** `app/core/auth.py` (created)
- **Verification:** `from app.core.auth import BearerAuthMiddleware` succeeds; V2-OFF boot test wires it (`app.user_middleware` includes `BearerAuthMiddleware`); `/task/all` under V2-OFF returns 401 (Scenario 1 W4 critical assertion).
- **Committed in:** 630170f (Task 1)

**2. [Rule 1 - Bug] Comment text tripped grep gate `grep -c 'allow_origins=["\*"]' == 0`**
- **Found during:** Task 2 verification
- **Issue:** Initial CORS comment included the literal string `NEVER allow_origins=["*"]` for documentation. The verifier grep gate counts that exact pattern — count must be 0. Comment text caused count=1 (false positive).
- **Fix:** Rephrased comment to "NEVER use wildcard origins" — preserves documentation intent without matching the literal regex.
- **Files modified:** `app/main.py`
- **Verification:** `grep -c 'allow_origins=\["\*"\]' app/main.py` returns 0 (post-fix)
- **Committed in:** 1f2a721 (Task 2)

---

**Total deviations:** 2 auto-fixed (1 Rule 3 blocking, 1 Rule 1 bug)
**Impact on plan:** Rule 3 fix essential — without the recreated module, the V2-OFF branch would not boot. Rule 1 fix essential — without it, the verifier grep gate would block plan completion. No scope creep.

## Issues Encountered

- **Pre-existing test failures (out of scope):** 3 audio_processing_service unit tests assert `update.assert_called_once` but the production code now emits 4 update calls (queued / transcribing / complete / status). 3 task-related test files fail to collect due to missing `factory` package. Both pre-date plan 13-09 and are already logged in `.planning/phases/13-atomic-backend-cutover/deferred-items.md` (originally discovered during 13-06). Auth-route integration tests (12) all pass.
- **Default `ENVIRONMENT=production` in `app/core/config.py`:** The default environment value is `"production"`, which would trigger the production safety guard on every default-env boot. The repository `.env` file overrides this to `ENVIRONMENT=development`, so dev boot succeeds. Confirmed not a regression from this plan.

## TDD Gate Compliance

Plan type is `execute` (not `tdd`), so RED/GREEN gates don't apply. Both task commits use `feat:` type (correct for new wiring + new module file).

## Next Phase Readiness

- **Phase 14 (frontend cutover):** READY. The backend now serves the full Phase 13 stack when `AUTH__V2_ENABLED=true` is set. Frontend can target `/auth/register`, `/auth/login`, `/auth/logout`, `/api/keys`, `/api/account/data`, `/billing/checkout`, `/billing/webhook`, `/api/ws/ticket` against this app.
- **Phase 16 (verification):** READY for cross-user matrix tests, JWT attack tests, WS ticket reuse tests, migration smoke tests against the wired stack.
- **Phase 16+ (cleanup ticket):** Schedule deletion of `app/core/auth.py` and the V2-OFF else-branch in `app/main.py` once `AUTH__V2_ENABLED=true` is verified stable in production for ≥1 release window.
- **Operational note:** When deploying with `AUTH__V2_ENABLED=true`, ensure `AUTH__JWT_SECRET`, `AUTH__CSRF_SECRET`, `AUTH__FRONTEND_URL`, and `AUTH__COOKIE_SECURE=true` are set (the AuthSettings model_validator from 13-01 enforces these in production).

## Self-Check: PASSED

All files exist on disk; all commit hashes resolved in `git log --all --oneline`:

- `app/main.py` ✓
- `app/core/auth.py` ✓
- `app/api/__init__.py` ✓
- `.planning/phases/13-atomic-backend-cutover/13-09-SUMMARY.md` ✓
- Commit `630170f` (Task 1) ✓
- Commit `1f2a721` (Task 2) ✓

---

*Phase: 13-atomic-backend-cutover*
*Plan: 09 (atomic flip)*
*Completed: 2026-04-29*
