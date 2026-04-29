---
phase: 15-account-dashboard-hardening-billing-stubs
plan: 02
subsystem: auth
tags: [fastapi, jwt, token-version, cookie, dependency-injection, integration-testing]

# Dependency graph
requires:
  - phase: 15-01
    provides: app.api._cookie_helpers.clear_auth_cookies (DRY shared helper)
  - phase: 11
    provides: AuthService.logout_all_devices (token_version bump)
  - phase: 13
    provides: DualAuthMiddleware + get_authenticated_user dependency
provides:
  - POST /auth/logout-all HTTP route (AUTH-06) — bumps token_version + clears cookies
  - auth_full_app + auth_full_session_factory + auth_full_client test fixtures
    (auth_router with DualAuthMiddleware mounted) for future auth-required tests
  - _register helper in test_auth_routes.py mirroring test_account_routes.py
affects: [15-06, 16]  # 15-06 wires LogoutAllDialog to this route; 16 verifies cross-user JWT attack matrix

# Tech tracking
tech-stack:
  added: []  # No new deps — pure glue route
  patterns:
    - "Glue HTTP route pattern: route delegates to AuthService method, returns
      fresh Response(204) with clear_auth_cookies — mirrors /auth/logout"
    - "Dual-fixture pattern: slim auth_app (anonymous tests, allowlisted paths
      only) + auth_full_app (DualAuthMiddleware mounted, auth-required tests).
      Avoids breaking existing test_logout_idempotent which depends on no auth."

key-files:
  created: []
  modified:
    - app/api/auth_routes.py — +25 lines: imports get_authenticated_user + User, adds /logout-all route (AUTH-06)
    - tests/integration/test_auth_routes.py — +158 lines: auth_full_app fixture stack + 4 logout-all tests

key-decisions:
  - "Route is glue-only: AuthService.logout_all_devices already validated user existence (raises InvalidCredentialsError on missing user); route does HTTP only, no business logic, no nested-if. SRP locked."
  - "Mirror /auth/logout fresh-Response pattern (T-15-04): build new Response(204), call clear_auth_cookies on it, return that. Never reuse the injected Response — FastAPI drops Set-Cookie headers when the handler returns an explicit Response."
  - "Test placement: extend test_auth_routes.py with a NEW auth_full_app fixture (PATTERNS.md Option A) instead of mutating the existing auth_app fixture. Mounting DualAuthMiddleware on auth_app would 401 the existing test_logout_idempotent (no-cookie POST /auth/logout) since /auth/logout is NOT in PUBLIC_ALLOWLIST. Net: zero regression on the 12 existing tests."
  - "JWT-invalidation test snapshot pattern: client cookies cleared by the 204 response, so the next call would be anonymous (401 via path-not-allowlisted) and would NOT prove the token_version invariant. Snapshot the cookie BEFORE logout-all, re-attach via client.cookies.set('session', old_session_cookie), then assert 401 on retry — this exercises ver=N JWT vs server-side ver=N+1 explicitly. Matches plan behavior spec."
  - "Self-explanatory naming: version_before/version_after over v_before/v_after; old_session_cookie over saved_session_cookie. Per CLAUDE.md."

patterns-established:
  - "Auth-gated logout-style route: @router.post('/path', status_code=204) → user: User = Depends(get_authenticated_user), service: X = Depends(get_X_service) → service.method(int(user.id)) → response = Response(204); helper(response); return response"
  - "auth_full_app fixture: copy account_app shape (DualAuthMiddleware) into test_auth_routes.py for auth-required tests on /auth/* routes — keeps slim auth_app intact for anonymous tests"

requirements-completed: [AUTH-06]

# Metrics
duration: 4 min
completed: 2026-04-29
---

# Phase 15 Plan 02: Logout-All Devices Summary

**POST /auth/logout-all wired (AUTH-06) — bumps users.token_version atomically, clears session+csrf cookies on a fresh Response(204), invalidates every outstanding JWT for the user; 4 integration tests green, zero regression on existing /auth/* suite (16/16 pass).**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-29T19:04:51Z
- **Completed:** 2026-04-29T19:09:29Z
- **Tasks:** 1 (TDD: RED → GREEN, no REFACTOR needed — code minimal)
- **Files modified:** 2

## Accomplishments

- Wired `POST /auth/logout-all` HTTP route to existing `AuthService.logout_all_devices` (token_version bump) — closes AUTH-06.
- Added `auth_full_app` fixture stack to `test_auth_routes.py` (mounts `DualAuthMiddleware` for auth-required tests) without breaking the existing slim `auth_app` fixture (anonymous tests on allowlisted paths).
- Added 4 integration tests covering all 4 must-have truths from PLAN frontmatter:
  1. `test_logout_all_bumps_token_version` — token_version goes N → N+1 atomically.
  2. `test_logout_all_clears_cookies` — Set-Cookie deletes both `session` + `csrf_token` (Max-Age=0 ×2).
  3. `test_logout_all_invalidates_existing_jwt` — old JWT (ver=N) returns 401 on retry vs server-side ver=N+1.
  4. `test_logout_all_requires_auth` — anonymous POST returns 401 `"Authentication required"`.
- Verified all 5 acceptance-criteria grep gates: route declaration count, service-call count, `clear_auth_cookies(response)` count ≥2, nested-if count = 0, `Depends(Response)` anti-pattern count = 0.

## Task Commits

TDD cycle (RED → GREEN, no refactor needed):

1. **Task 1 RED: Failing tests for /auth/logout-all** — `5e71e5e` (test)
2. **Task 1 GREEN: Wire POST /auth/logout-all route** — `5d03e77` (feat)

**Plan metadata:** TBD (final docs commit follows this SUMMARY)

## Files Created/Modified

- `app/api/auth_routes.py` — Added `/logout-all` route (lines 199-217); imported `get_authenticated_user` + `User`. Glue only: 4 statements in the route body, zero `if`s.
- `tests/integration/test_auth_routes.py` — Added `auth_full_session_factory` + `auth_full_app` + `auth_full_client` fixtures (mount `DualAuthMiddleware`); added `_register` helper; added 4 `test_logout_all_*` integration tests.

## Decisions Made

- **Route is glue, not logic.** Service-layer guard already raises `InvalidCredentialsError` if user vanishes between auth and bump. Route does HTTP only — no validation, no nested-if, no logging beyond what `AuthService.logout_all_devices` already emits (`logger.info("Logout-all-devices id=%s", user_id)` in service). T-13-13 honored at service layer; route adds nothing.
- **Mirror /auth/logout cookie-clearing pattern verbatim** (T-15-04): `response = Response(204)` then `clear_auth_cookies(response)`. The Plan 13-03 lesson — never reuse `Depends(Response)` for cookie deletion because FastAPI silently drops Set-Cookie headers — applies identically here.
- **Test fixture choice: Option A (locked by PATTERNS.md).** Add `auth_full_app` mounting `DualAuthMiddleware` to `test_auth_routes.py` rather than mutating `auth_app` or putting tests in `test_account_routes.py`. Two reasons: (1) mutating `auth_app` would 401 the existing `test_logout_idempotent` (POST /auth/logout without cookie + path not allowlisted = 401), creating a regression cost. (2) Logically these are `/auth/*` tests and belong with their siblings.
- **JWT-invalidation cookie-snapshot pattern.** The 204 response clears the client-side cookie, so the natural next-request would be anonymous and would 401 for the wrong reason (no cookie at all). Snapshot the cookie BEFORE the logout-all call, then re-attach it on the retry — this exercises the token_version ver-check (server expects N+1, JWT carries N) explicitly, exactly as the plan's must-have truth #3 demands.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed literal `Depends(Response)` from docstring**
- **Found during:** Task 1 GREEN (acceptance-criteria gate run)
- **Issue:** First draft of the `/logout-all` docstring contained the literal phrase `"never use Depends(Response) here"` as a warning. Acceptance criterion AC5 (`grep -c "Depends(Response)" app/api/auth_routes.py` returns 0) flagged this — the verifier-grep does not distinguish docstring text from code, and the project locks the gate at 0 occurrences anywhere in the file.
- **Fix:** Paraphrased the docstring to `"see logout above for rationale"` without the literal anti-pattern token. Intent preserved, gate satisfied.
- **Files modified:** `app/api/auth_routes.py` (docstring only)
- **Verification:** All 5 acceptance grep gates pass; 4 logout-all tests still pass; 2 existing /auth/logout tests pass; full 16/16 auth_routes.py suite green.
- **Committed in:** Folded into `5d03e77` (Task 1 GREEN commit).

---

**Total deviations:** 1 auto-fixed (1 verifier-gate compliance bug)
**Impact on plan:** Trivial — docstring rewording only. No scope creep. Plan executed exactly as written.

## Issues Encountered

None — plan worked first try after applying Rule 1 docstring fix.

## Authentication Gates

None — no external services touched, no auth-required CLI commands run.

## User Setup Required

None — no external service configuration required.

## Threat Flags

None — implementation maps 1:1 to the plan's `<threat_model>` (T-15-03 mitigated by atomic UPDATE before response; T-15-04 mitigated by fresh-Response pattern; T-13-13 already covered by service-layer log discipline). No new surface introduced.

## Self-Check: PASSED

- [x] `app/api/auth_routes.py` modified — verified via `git log --oneline | head -3`
- [x] `tests/integration/test_auth_routes.py` modified — same
- [x] Commit `5e71e5e` (test RED) exists
- [x] Commit `5d03e77` (feat GREEN) exists
- [x] All 5 acceptance criteria pass (route=1, service-call=1, clear_auth_cookies(response)=2, nested-if=0, Depends(Response)=0)
- [x] 4 logout-all tests pass (`pytest tests/integration/test_auth_routes.py -k logout_all -q` → 4 passed)
- [x] 2 existing /auth/logout tests still pass (`pytest -k "logout and not logout_all" -q` → 2 passed)
- [x] Full auth_routes.py suite passes (16/16)

## TDD Gate Compliance

- RED gate: `5e71e5e` — `test(15-02): add failing tests for POST /auth/logout-all` (test commit precedes feat).
- GREEN gate: `5d03e77` — `feat(15-02): wire POST /auth/logout-all (AUTH-06)`.
- REFACTOR: not needed; route body is 4 statements, zero duplication, no smells.

## Next Phase Readiness

- Plan 15-03 (`/api/account/me` server-side hydration) ready: AUTH-06 backend closed; service surface unchanged; `clear_auth_cookies` helper still single-source per Plan 15-01.
- Frontend Plan 15-06 (LogoutAllDialog) can wire to MSW handler `POST /auth/logout-all` (already stubbed in `frontend/src/tests/msw/account.handlers.ts` per Plan 15-01) and the real route lands at deploy.
- Phase 16 (gate-to-milestone-close) can now exercise the cross-tab logout-all matrix end-to-end against the real route.

No blockers. No concerns.

---
*Phase: 15-account-dashboard-hardening-billing-stubs*
*Completed: 2026-04-29*
