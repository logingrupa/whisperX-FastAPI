---
phase: 19-auth-di-refactor
plan: 14
subsystem: auth-di
tags: [test, ci-gate, perf, regression, session-leak]

requires:
  - phase: 19-auth-di-refactor
    provides: |
      Plan 19-03 get_db single-Session per request;
      Plan 19-04 authenticated_user Depends path;
      Plan 19-10 app.dependency_overrides[get_db] test seam;
      Plan 19-13 single-namespace Depends chain (final D1 closure).

provides:
  - "tests/integration/test_no_session_leak.py — pytest CI gate firing 50 sequential authed GET /api/account/me via TestClient; per-request budget < 100ms; p95 < 100ms."
  - "Regression detection for the SQLAlchemy QueuePool exhaustion that produced commits 0f7bb09 + 61c9d61 — pre-fix this loop hung at iter ~16 on QueuePool checkout (default pool_size=5 + max_overflow=10 = 15)."
  - "Companion to scripts/verify_session_leak_fix.py — same drain shape, run in pytest on every PR (D6 lock; script deleted only after CI green for 2 weeks AND grep -rn '_container\\.' app/ stays at 0)."

affects: [ci, refactor-06-gate]

tech-stack:
  added: []
  patterns:
    - "Single-test fixture pattern: tmp_path + create_engine + Base.metadata.create_all + sessionmaker + app.dependency_overrides[get_db] = _override_get_db (yield/finally close); production app.main.app reused (no slim FastAPI subclass needed)."
    - "Boundary-asserted perf loop: time.perf_counter() per iter, fail-fast on status + elapsed inside the loop, p95 boundary assert AFTER the loop (mirrors test_argon2_benchmark p99 pattern; mirrors scripts/verify_session_leak_fix.py drain pattern)."
    - "limiter.reset() bookends fixture — slowapi 3/hr cap on /auth/register is a module-level singleton; reset on setup AND teardown so the test does not bleed across pytest invocations or other integration tests in the same suite."

key-files:
  created:
    - "tests/integration/test_no_session_leak.py — 129 LOC; 1 fixture (client_with_db), 1 helper (_register_user), 1 test class with 1 method; tiger-style flat early-returns; self-explanatory names (_PER_REQUEST_BUDGET_MS, durations_ms)."
  modified: []

decisions:
  - "Used the production app.main:app (NOT a slim FastAPI subclass) — exercises the FULL middleware + router stack on the leak path; the fixture overrides get_db only, no other deps mutated. Plan 19-10 already migrated 14 sibling integration tests to this same pattern."
  - "limiter.reset() added to fixture setup AND teardown (Rule 3 deviation: blocking issue mitigation) — without this, /auth/register would 429 if any prior test in the same pytest invocation triggered the slowapi 3/hr/IP/24 cap. Mirrors test_set_cookie_attrs.py + test_auth_routes.py + 13 other integration tests."
  - "tmp_path engine + Base.metadata.create_all gives a fresh schema per test invocation — no Alembic stamp needed (matches Plan 19-10 fixtures); engine.dispose() in teardown for full pool cleanup."

metrics:
  duration: "8 min"
  tasks_completed: 1
  files_modified: 1
  completed: 2026-05-02
---

# Phase 19 Plan 14: No-Session-Leak Regression Test Summary

**One-liner:** pytest CI gate firing 50 sequential authed `GET /api/account/me` calls via TestClient against the production `app.main:app` — locks in REFACTOR-06's structural fix and detects any future regression to the QueuePool-exhaustion class of bug.

## What was built

A single integration test file at `tests/integration/test_no_session_leak.py` (129 LOC):

- **Fixture `client_with_db`:** builds a `TestClient` bound to the production FastAPI app (`from app.main import app`), with `app.dependency_overrides[get_db]` pointing at a fresh tmp-SQLite engine per test invocation. `limiter.reset()` bookends setup AND teardown so the slowapi 3/hr cap on `/auth/register` cannot bleed across tests.
- **Helper `_register_user`:** `POST /auth/register` then asserts the `session` cookie landed (boundary precondition).
- **Test method `test_fifty_sequential_authed_requests_under_budget`:** registers a user, then loops 50 iterations of `GET /api/account/me` measuring `time.perf_counter()` per iter. Fails fast inside the loop on status != 200 OR elapsed >= 100ms. Asserts `p95 < 100ms` after the loop.

## Why this is the CI gate REFACTOR-06 needed

Before the Phase 19 structural refactor, this exact 50-iter loop hung at iter ~16 on `QueuePool checkout` — the default SQLAlchemy pool (`pool_size=5 + max_overflow=10 = 15`) was exhausted because `DualAuthMiddleware` + direct `_container.X()` callsites leaked a Session per HTTP request. Two consecutive fix commits (0f7bb09, 61c9d61) added inline `try/finally` blocks but did not fix the structural cause. Phase 19 fixed the structure: `get_db` is the SOLE site that owns `Session.close()` for the request scope; every repo/service factory chains off `Depends(get_db)`; FastAPI's per-request dep cache shares ONE Session across the entire call graph.

The test makes that structural invariant CI-enforceable. If a future commit reintroduces a direct-container reach-in or a leaked `Session` outside the `get_db` finally, this test will hang — and the per-iter `< 100ms` assertion (well below the 30s `pool_timeout`) will fail at iter ~16, pinpointing the regression.

## Verification

- **Single-file pytest run:** `.venv/Scripts/python.exe -m pytest tests/integration/test_no_session_leak.py -x --tb=short -v` → **1 passed in 7.73s** (50 iters all < 100ms, p95 < 100ms; commit `a784986`).
- All 50 iters completed with substantial headroom (the test runtime including pytest startup + ML import side effects is < 10s wall-clock).
- Boundary preconditions verified: `session` cookie present after `POST /auth/register`.
- Boundary postcondition verified: `p95 < 100ms`.

Per the plan's `<verification>` block, this plan does NOT re-verify the full backend pytest suite green — Plans 11-13 already did that at each commit (atomic-commit invariant), and Plan 17 owns the final 21-gate verification.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] Added `limiter.reset()` to fixture setup + teardown**
- **Found during:** Task 1 implementation (pre-test-run review)
- **Issue:** The plan-prescribed locked code did not reset the slowapi limiter. `limiter` is a module-level singleton in `app/core/rate_limiter.py`; `/auth/register` carries `@limiter.limit("3/hour")` keyed on IP/24. TestClient hits `127.0.0.1`, so any prior integration test in the same pytest invocation that exercised `/auth/register` would have consumed slots — registering a 4th user would 429, breaking the test in CI.
- **Fix:** Added `limiter.reset()` at the top of the fixture body and in the teardown branch. Mirrors `test_set_cookie_attrs.py`, `test_auth_routes.py`, and 13 other integration tests already on disk (DRT — established project convention).
- **Files modified:** `tests/integration/test_no_session_leak.py`
- **Commit:** `a784986`

No Rule 1 / Rule 2 / Rule 4 deviations encountered.

## Self-Check: PASSED

- `tests/integration/test_no_session_leak.py` exists (FOUND, 129 LOC).
- Commit `a784986` exists in `git log` (FOUND).
- Test passes (FOUND — pytest output recorded above).
