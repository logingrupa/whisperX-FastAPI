---
phase: 16-verification-cross-user-matrix-e2e
plan: 04
subsystem: testing
tags: [verification, csrf, double-submit, bearer-bypass, security, pytest, fastapi]

# Dependency graph
requires:
  - phase: 16
    provides: "_phase16_helpers._issue_csrf_pair, _register"
  - phase: 13
    provides: "CsrfMiddleware, DualAuthMiddleware, auth_router, key_router, csrf_service"
  - phase: 15
    provides: "/auth/logout-all (cookie-auth state-mutating 204 endpoint)"
provides:
  - "tests/integration/test_csrf_enforcement.py — 4 cases (missing/mismatched/matching/bearer-bypass)"
  - "VERIFY-06 closed — CSRF double-submit invariant proven on /auth/logout-all"
  - "MID-04 invariant proven — bearer-auth state-mutating POST without X-CSRF-Token still succeeds"
affects: [phase-16-05, phase-16-06, milestone-v1.2-gate]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ASGI middleware reversal: register CsrfMiddleware FIRST, DualAuthMiddleware LAST so dispatch order is DualAuth -> Csrf -> route"
    - "_csrf_target_endpoint() single-source helper for CSRF surface path (DRY)"
    - "_issue_api_key helper re-reads csrf_token from jar (zero parameter coupling to register step)"

key-files:
  created:
    - "tests/integration/test_csrf_enforcement.py"
  modified: []

key-decisions:
  - "Target endpoint /auth/logout-all chosen — idempotent, 204 on cookie-auth success, lives on auth_router (already mounted), satisfies all 4 CSRF cases on a single path"
  - "Bearer-bypass test uses cookie-auth path to issue API key first, THEN client.cookies.clear() before bearer POST — unambiguous test signal (zero cookie noise)"
  - "_issue_api_key reads csrf_token from cookie jar instead of taking it as a parameter — caller already invoked _issue_csrf_pair so the cookie is on the jar; zero coupling between helpers"
  - "Defensive 'if response.status_code == 403' branch from plan body REMOVED to keep nested-if grep == 0; single primary assert is sufficient (tiger-style)"

patterns-established:
  - "VERIFY-06 4-case template: missing-header / mismatched-header / matching-header / bearer-bypass — each test asserts ONE thing (status code + body detail string equality on 403 cases)"
  - "Test fixture mounts CsrfMiddleware AND DualAuthMiddleware in REVERSED registration order — verifier-checked locked invariant"

requirements-completed: [VERIFY-06]

# Metrics
duration: 3 min
completed: 2026-04-30
---

# Phase 16 Plan 04: Atomic CSRF Enforcement Tests Summary

**Locked VERIFY-06 — 4 pytest integration cases prove CsrfMiddleware enforces double-submit on cookie auth and skips bearer-auth surfaces (MID-04), all on `/auth/logout-all` as the single CSRF target.**

## Performance

- **Duration:** 3 min 12 s
- **Started:** 2026-04-30T12:44:03Z
- **Completed:** 2026-04-30T12:47:15Z
- **Tasks:** 2
- **Files modified:** 1 (created)
- **Lines:** 215 (≥ 140 min_lines invariant)

## Accomplishments

- **4 green tests** covering the full CSRF state machine of `CsrfMiddleware`:
  - `test_csrf_missing_header_returns_403` — cookie-auth POST with no `X-CSRF-Token` → 403 `"CSRF token missing"`
  - `test_csrf_mismatched_header_returns_403` — cookie-auth POST with wrong `X-CSRF-Token` → 403 `"CSRF token mismatch"`
  - `test_csrf_matching_header_succeeds` — cookie-auth POST with matching `X-CSRF-Token` → 204
  - `test_bearer_auth_bypasses_csrf` — bearer-auth POST WITHOUT `X-CSRF-Token` → 204 (MID-04 bypass)
- **ASGI middleware order locked** — verifier-grep confirms `add_middleware(CsrfMiddleware)` registered before `add_middleware(DualAuthMiddleware)` so dispatch resolves `DualAuth → Csrf → route`.
- **DRY single source for CSRF target path** via `_csrf_target_endpoint()` — future endpoint changes touch one line.
- **Tiger-style assertions on 403 cases** — body `detail` string compared, not just status code (catches future regression where some other 403 passes by accident).
- **Bearer-bypass invariant proven end-to-end** — issued an API key via the cookie-auth path, cleared all cookies, sent bearer POST without any X-CSRF-Token, asserted 204.

## Task Commits

1. **Task 1: auth_full_app fixture + bearer-bootstrap helpers** — `ccb5087` (test)
2. **Task 2: 4 CSRF cases (missing/mismatched/matching/bearer-bypass)** — `7b7d2e0` (test)

_Plan metadata commit added in step 8 below._

## Files Created/Modified

- `tests/integration/test_csrf_enforcement.py` — 215 lines. Module docstring, 3 fixtures (`tmp_db_url`, `session_factory`, `auth_full_app`), 2 helpers (`_csrf_target_endpoint`, `_issue_api_key`), 4 test functions, all marked `@pytest.mark.integration`.

## Decisions Made

- **`/auth/logout-all` as the CSRF target** — idempotent, returns 204 on cookie-auth success, lives on `auth_router` we already mount, exercises both auth legs (cookie + bearer-after-key). Single-target keeps the four cases clean and DRY.
- **Cookie-auth path issues the API key first, then `client.cookies.clear()`** — the bearer-bypass test then exercises ONLY the bearer leg with zero cookie noise. Phase 13-02 STATE notes that bearer wins on mixed presentation, but unambiguous test signal prefers no cookies in the jar at all.
- **`_issue_api_key` reads `csrf_token` from `client.cookies` instead of as a parameter** — the helper has zero coupling to the register step (which already seated the cookie). Caller composes via `_issue_csrf_pair(client, ...)` first, then `_issue_api_key(client)` — order-of-operations is the only contract.
- **Removed defensive `if response.status_code == 403` branch from plan body** — plan suggested removing it as a final step; we never wrote it. Result: `grep -cE "^        if .*:$"` returns 0 (nested-if invariant).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Pytest 9 collect-only output format change**

- **Found during:** Task 2 acceptance-criteria verification.
- **Issue:** Plan AC1 invariant `pytest tests/integration/test_csrf_enforcement.py -q --co | grep -c "::test_"` returned `0` because pytest 9.0.3 renders `--collect-only` as a tree (`<Function test_xxx>` nodes), not as nodeIDs (`module.py::test_xxx`). The intent (4 tests collected) is preserved; only the grep pattern is incompatible with pytest 9.
- **Fix:** Used two equivalent invariants — `grep -c "^def test_"` on the file (returns 4) AND `grep -c "<Function test_"` on the collect output (returns 4). Both confirm the same property the AC was checking.
- **Files modified:** None (verification-only deviation; the file already shipped 4 well-named tests).
- **Verification:** 4 test functions defined, 4 collected by pytest, 4 passed.
- **Committed in:** No code change required.

---

**Total deviations:** 1 auto-fixed (Rule 3 — pytest 9 collect-only format change).
**Impact on plan:** Zero scope creep. The AC1 grep pattern is a tooling detail, not a behavioral invariant. The behavioral invariant (4 tests pass) holds.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Self-Check: PASSED

- File exists: `tests/integration/test_csrf_enforcement.py` — FOUND
- Commit `ccb5087` (Task 1) — FOUND in `git log`
- Commit `7b7d2e0` (Task 2) — FOUND in `git log`
- All `<acceptance_criteria>` re-run:
  - Task 1 AC1: `include_router(auth_router|key_router)` count = 2 ≥ 2 — PASS
  - Task 1 AC2: `add_middleware(CsrfMiddleware)` line 98 BEFORE `add_middleware(DualAuthMiddleware)` line 99 — PASS
  - Task 1 AC3: `limiter.reset()` count = 2 ≥ 2 — PASS
  - Task 2 AC1: 4 tests collected — PASS (via equivalent grep, see deviation 1)
  - Task 2 AC2: `pytest -x` exit 0, 4 passed — PASS
  - Task 2 AC3: `X-CSRF-Token` count = 13 ≥ 3 — PASS
  - Task 2 AC4: `"CSRF token missing"|"CSRF token mismatch"` count = 4 ≥ 2 — PASS
  - Task 2 AC5: nested-if count = 0 — PASS
- `<verification>` re-run: `pytest tests/integration/test_csrf_enforcement.py -v` → 4 passed.
- `<success_criteria>` re-checked: 4 cases pass, single-source target endpoint, body-detail asserts, ASGI order locked, limiter.reset() in setup AND teardown, no nested-if.

## Next Phase Readiness

- VERIFY-06 closed; phase 16 wave 1 progresses (16-02 / 16-03 / 16-04 are wave-1 siblings — execute independently).
- Ready for 16-05 (WS ticket safety, VERIFY-07) and 16-06 (migration smoke, VERIFY-08).
- No blockers.

---
*Phase: 16-verification-cross-user-matrix-e2e*
*Completed: 2026-04-30*
