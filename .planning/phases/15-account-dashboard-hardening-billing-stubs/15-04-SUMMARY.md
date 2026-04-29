---
phase: 15-account-dashboard-hardening-billing-stubs
plan: 04
subsystem: api
tags: [fastapi, sqlalchemy, account-deletion, fk-cascade, anti-enumeration, tdd]

# Dependency graph
requires:
  - phase: 15-01-groundwork
    provides: clear_auth_cookies helper + DeleteAccountRequest schema
  - phase: 15-03-account-me
    provides: AccountService._user_repository constructor injection
  - phase: 13-05-account-data
    provides: AccountService.delete_user_data (Step 1 reuse)
  - phase: 11-03-repositories
    provides: SQLAlchemyUserRepository.delete with ORM CASCADE
  - phase: 10-04-fk-pragma
    provides: PRAGMA foreign_keys=ON enforced globally
provides:
  - DELETE /api/account end-to-end (SCOPE-06 closed)
  - 3-step service-orchestrated cascade (tasks → buckets → user→ORM CASCADE)
  - rate_limit_buckets prefix-match cleanup pattern (no-FK table)
  - Email-confirm guard (case-insensitive, anti-enumeration 400)
  - Cookie-clear-on-delete UX (T-15-04 fresh-Response idiom reused)
affects: [15-05-auth-hydration, 15-06-account-page, 16-gate-milestone-close]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Service-orchestrated multi-step cascade: pre-delete (no-FK + SET-NULL) → ORM-CASCADE delete"
    - "Route-local ValidationError → HTTPException(400) translation (handler default 422 preserved for other sites)"
    - "TestClient.delete() does not accept json= kwarg — use client.request('DELETE', url, json=...)"

key-files:
  created: []
  modified:
    - app/services/account_service.py
    - app/api/account_routes.py
    - tests/integration/test_account_routes.py

key-decisions:
  - "Strategy C LOCKED: service-orchestrated explicit pre-delete + ORM CASCADE (Pitfall 2: tasks.user_id NOT NULL after migration 0003 forbids bare user delete)"
  - "rate_limit_buckets prefix-match LIKE 'user:<uid>:%' — no FK on this table; pattern locked to never match ip:* keys"
  - "ValidationError translated to 400 EMAIL_CONFIRM_MISMATCH at route boundary (Option B per plan); global validation_error_handler 422 preserved for register/login flows"
  - "T-15-03 LOCKED: no token_version bump on delete — user-row-gone is the invalidation signal; cookie clearing is route-level UX cleanup"
  - "Logging discipline: user_id only, never user.email (T-15-11)"
  - "Tiger-style boundary assertions (user_id > 0, email_confirm non-empty); flat early-raise guards (no nested-if)"

patterns-established:
  - "Multi-table delete cascade: explicit pre-delete for non-CASCADE FKs (SET NULL) + no-FK tables (text prefix-match) BEFORE ORM CASCADE delete on parent row"
  - "Anti-enumeration: 400 EMAIL_CONFIRM_MISMATCH only reachable AFTER auth passed (401 path is fully separate); generic copy + structured code"
  - "Cookie-clear-on-delete (T-15-04): build new Response(204) and call clear_auth_cookies on it; never reuse Depends-injected Response"
  - "TestClient body-on-delete: client.request('DELETE', url, json=body) — Starlette TestClient.delete() does not accept json kwarg"

requirements-completed: [SCOPE-06]

# Metrics
duration: 9min
completed: 2026-04-29
---

# Phase 15 Plan 04: Delete Account Summary

**DELETE /api/account end-to-end with 3-step service-orchestrated cascade (tasks → rate_limit_buckets → user→ORM CASCADE), email-confirm guard (case-insensitive), and cookie clearing — SCOPE-06 closed.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-04-29T19:14:19Z
- **Completed:** 2026-04-29T19:23:10Z
- **Tasks:** 3 (all GREEN)
- **Files modified:** 3 (1 service + 1 route + 1 test)
- **Commits:** 3 (1 test RED + 2 feat GREEN)

## Accomplishments

- `AccountService.delete_account(user_id, email_confirm)` orchestrates 3-step cascade: `delete_user_data` (Step 1, SCOPE-05 reuse) → `DELETE FROM rate_limit_buckets WHERE bucket_key LIKE 'user:<uid>:%'` (Step 2, no-FK prefix-match) → `_user_repository.delete(user_id)` (Step 3, fires ORM CASCADE for the 4 CASCADE FKs).
- `DELETE /api/account` route: auth-gated, body validated via `DeleteAccountRequest`, ValidationError translated to 400 EMAIL_CONFIRM_MISMATCH locally, fresh `Response(204)` + `clear_auth_cookies` (T-15-04 idiom).
- 7 new integration tests cover the full FK matrix: cascade-full-universe (5 FK tables + buckets + user row), email-mismatch (400 + data preserved), case-insensitive match, cookie-clear (Max-Age=0 ×2), auth-required (401), cross-user isolation (Bob untouched), missing-body (422).
- Zero regression: 16/16 account_routes tests + 16/16 auth_routes tests green.

## Task Commits

Each task committed atomically with TDD discipline:

1. **Task 3 (RED): 7 failing tests + `_seed_full_user_universe` helper** — `06e8cb8` (test)
2. **Task 1 (GREEN): `AccountService.delete_account` 3-step cascade** — `a81e077` (feat)
3. **Task 2 (GREEN): `DELETE /api/account` route + Rule-1 fix to TestClient.delete kwarg** — `244f4f2` (feat)

_TDD ordering: RED tests first → service GREEN → route GREEN. All 7 tests pass after the route commit._

## Files Created/Modified

- `app/services/account_service.py` — Added `delete_account` method (3-step cascade orchestrator); imported `ValidationError` alongside existing `InvalidCredentialsError`; updated module docstring to reflect SCOPE-06.
- `app/api/account_routes.py` — Added `@account_router.delete("")` route; imported `clear_auth_cookies`, `DeleteAccountRequest`, `HTTPException`, `ValidationError`; route-local 400 translation for EMAIL_CONFIRM_MISMATCH.
- `tests/integration/test_account_routes.py` — Added `_seed_full_user_universe` helper (6-table seed) + 7 integration tests covering the full SCOPE-06 contract.

## Decisions Made

- **Strategy C LOCKED** (RESEARCH §"FK Cascade Coverage"): service-orchestrated explicit pre-delete + ORM CASCADE. Order matters per Pitfall 2 — `tasks.user_id` is NOT NULL after migration 0003, so a bare user delete would IntegrityError because `ON DELETE SET NULL` fires before user-row removal. Step 1 (`delete_user_data`) DELETEs tasks first.
- **rate_limit_buckets prefix-match locked**: `bucket_key LIKE 'user:<uid>:%'` matches `user:42:hour`, `user:42:tx:hour`, `user:42:audio_min:day`, `user:42:concurrent`; never matches `ip:10.0.0.0/24:*`. Cross-user isolation test exercises this.
- **Option B (route-local 400 translation)**: global `validation_error_handler` defaults to 422; the SCOPE-06 contract locks 400 EMAIL_CONFIRM_MISMATCH per CONTEXT D-RES. Catching `ValidationError` in the route and re-raising as `HTTPException(400)` preserves register/login 422 flows untouched.
- **No token_version bump on delete (T-15-03 LOCKED)**: user-row-gone is the invalidation signal — middleware `get_by_id` returns `None` on next request → 401. Cookie clearing in the route is UX cleanup (avoids stale-cookie zombie), not a security gate.
- **Email confirmation case-insensitive**: `email_confirm.strip().lower() == user.email.lower()` per UI-SPEC §190 + CONTEXT D-RES; allows Foo@Example.com to match foo@example.com.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] TestClient.delete() does not accept json= kwarg**
- **Found during:** Task 3 verification (running the new tests after Task 2 GREEN)
- **Issue:** Initial test code used `client.delete("/api/account", json={...})` but `TestClient.delete()` in this Starlette/httpx version does not accept a `json` kwarg — only `params/headers/cookies/auth/follow_redirects/timeout/extensions`. All 6 delete-with-body tests TypeError'd.
- **Fix:** Switched all 6 calls to `client.request("DELETE", "/api/account", json={...})`, which is the documented httpx idiom for non-GET/POST methods carrying a body. Plan body recommended `client.delete(..., json=...)` directly — the runtime API does not support it. The 7th test (`no_body_returns_422`) was already correct (no `json` kwarg).
- **Files modified:** `tests/integration/test_account_routes.py`
- **Verification:** All 7 tests pass after the swap; 16/16 account_routes + 16/16 auth_routes green.
- **Committed in:** `244f4f2` (rolled into Task 2 GREEN commit since service was already correct).

---

**Total deviations:** 1 auto-fixed (Rule 1 bug — test-only)
**Impact on plan:** No scope creep; service + route implemented exactly as written. The fix was test-side only and matches httpx documentation. Pattern recorded in tech-stack.patterns for future tests writing DELETE-with-body.

## Issues Encountered

None — TDD cycle ran cleanly after the kwarg fix. RED gate confirmed (404 missing route), GREEN gate confirmed (all 7 tests pass), no regression on the 9 existing tests.

## Verification Gates Passed

- `grep -c "def delete_account" app/services/account_service.py` → 1
- `grep "DELETE FROM rate_limit_buckets" app/services/account_service.py` → 1 hit (line 169)
- `grep "self.delete_user_data" app/services/account_service.py` → 1 hit (line 161, Step 1 reuse)
- `grep "_user_repository.delete" app/services/account_service.py` → 1 hit (line 177, Step 3)
- `grep -c "EMAIL_CONFIRM_MISMATCH" app/services/account_service.py` → 1
- `grep -c "assert user_id > 0" app/services/account_service.py` → 2 (get_account_summary + delete_account)
- `grep "assert email_confirm" app/services/account_service.py` → 1 hit (line 143)
- `grep -cE "^\s+if .*\bif\b" app/services/account_service.py` → 0 (no nested-if)
- `grep -c "clear_auth_cookies(response)" app/api/account_routes.py` → 1
- `grep -c "Depends(Response)" app/api/account_routes.py` → 0 (T-15-04 anti-pattern absent)
- `grep -c "body: DeleteAccountRequest" app/api/account_routes.py` → 1
- `grep -cE "^\s+if .*\bif\b" app/api/account_routes.py` → 0 (no nested-if)
- `pytest tests/integration/test_account_routes.py -k delete_account -q` → 7 passed
- `pytest tests/integration/test_account_routes.py -q` → 16 passed (zero regression)
- `pytest tests/integration/test_account_routes.py tests/integration/test_auth_routes.py -q` → 32 passed (cross-file zero regression)

## User Setup Required

None — no external service configuration required. SCOPE-06 is purely server-side.

## Next Phase Readiness

- Plan 15-05 (auth-hydration): `DELETE /api/account` is now wired end-to-end; the frontend `accountApi.deleteAccount(emailConfirm)` will work as soon as Plan 15-01's groundwork lands a typed wrapper. All 4 backend account routes (`/data`, `/me`, `/`, `/auth/logout-all`) now return correctly-typed JSON / 204 with cookie clearing.
- Plan 15-06 (account-page): `DeleteAccountDialog` can call `deleteAccount(emailConfirm)` and rely on:
  - 204 + cleared cookies on success (call `authStore.logout()` or rely on client-side cookie wipe)
  - 400 EMAIL_CONFIRM_MISMATCH on mismatch (route-local; status code stable)
  - 401 on auth lapse
  - 422 on missing body (Pydantic — should be impossible from the dialog form which gates on `isMatched` before submit)
- Phase 16 (gate-to-milestone-close): cross-user matrix tests can use the `_seed_full_user_universe` helper directly. The cascade test asserts COUNT=0 on all 6 tables — extends naturally to N users.

## Self-Check: PASSED

- File `app/services/account_service.py` exists — confirmed
- File `app/api/account_routes.py` exists — confirmed
- File `tests/integration/test_account_routes.py` exists — confirmed
- Commit `06e8cb8` (test RED) — confirmed in `git log`
- Commit `a81e077` (feat service GREEN) — confirmed in `git log`
- Commit `244f4f2` (feat route GREEN + Rule-1 test fix) — confirmed in `git log`

---

*Phase: 15-account-dashboard-hardening-billing-stubs*
*Completed: 2026-04-29*
