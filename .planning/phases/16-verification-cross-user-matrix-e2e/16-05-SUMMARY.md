---
phase: 16-verification-cross-user-matrix-e2e
plan: 05
subsystem: testing
tags: [verification, websocket, ticket, single-use, ttl, cross-user, integration, pytest]

# Dependency graph
requires:
  - phase: 16-verification-cross-user-matrix-e2e
    provides: _phase16_helpers (WS_POLICY_VIOLATION, _register, _insert_task)
  - phase: 13-auth-v2-mid
    provides: WsTicketService atomic single-use + 60s TTL; websocket_api defence-in-depth handler check
provides:
  - tests/integration/test_ws_ticket_safety.py — gold copy for VERIFY-07 (3 attack cases)
  - reuse → 1008 (T-13-25 single-use)
  - expired → 1008 (T-13-26 TTL)
  - cross-user drift → 1008 (MID-07 defence-in-depth)
affects: [16-VERIFICATION, future-phases-touching-ws-ticket-service]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - _FrozenDatetime monkeypatch on app.services.ws_ticket_service.datetime (single-line for grep gate)
    - Two TestClient instances for cross-user drift (FK-valid drift target)
    - direct UPDATE on tasks.user_id for drift simulation (avoid ORM round-trip)

key-files:
  created:
    - tests/integration/test_ws_ticket_safety.py
  modified: []

key-decisions:
  - "Drift target must be FK-valid: PRAGMA foreign_keys=ON (10-04) rejects non-existent user_ids; test registers User B and drifts tasks.user_id to user_id_b instead of 9999"
  - "monkeypatch.setattr(...) MUST stay on a single line — verifier grep gate matches per-line, not multi-line; line-wrapping the call would make the gate return 0"
  - "ws_app fixture omits CsrfMiddleware — WS handshake doesn't trigger HTTP CSRF, ticket flow IS the WS auth (mirrors test_ws_ticket_flow.py)"
  - "Each test instantiates a fresh TestClient inside the function rather than via a shared fixture — keeps test scope explicit and matches plan's per-test client pattern"

patterns-established:
  - "Pattern: VERIFY-07 attack-case structure — register → seed task → issue ticket → trigger drift/expiry/reuse → assert close 1008"
  - "Pattern: cross-user drift via real second user (FK-valid) not synthetic non-existent id"

requirements-completed: [VERIFY-07]

# Metrics
duration: 7min
completed: 2026-04-30
---

# Phase 16 Plan 05: WS Ticket Safety Summary

**VERIFY-07 closed: WS ticket reuse, TTL expiry (mocked clock), and cross-user drift each force a 1008 close — proves WsTicketService atomic single-use + 60s TTL + handler defence-in-depth all enforce.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-04-30T12:43:59Z
- **Completed:** 2026-04-30T12:51:06Z
- **Tasks:** 2
- **Files modified:** 1 (created)

## Accomplishments

- Created `tests/integration/test_ws_ticket_safety.py` (247 lines, plan min 180) with 3 attack-case integration tests
- All 3 tests pass deterministically in ~2.3s
- Mirrors `test_ws_ticket_flow.py:60-113` fixture shape — slim FastAPI app with auth + ws_ticket + websocket routers + DualAuthMiddleware
- Imports `WS_POLICY_VIOLATION` + `_register` + `_insert_task` from `_phase16_helpers` (DRT)
- `_FrozenDatetime` monkeypatch correctly targets `app.services.ws_ticket_service.datetime` (Pitfall 4)
- Cross-user drift uses two TestClients + real User B (FK-valid); single direct `UPDATE tasks SET user_id = :new` keeps the test fast and DB-shape-stable

## Task Commits

Each task was committed atomically:

1. **Task 1: ws_app fixture + helpers** — `b2ba092` (test) — module skeleton: imports, `tmp_db_url` + `session_factory` + `ws_app` fixtures, `_close_code_from_disconnect` + `_issue_ticket` helpers
2. **Task 2: 3 attack cases** — `1ebee3b` (test) — `test_reused_ticket_close_1008`, `test_expired_ticket_close_1008`, `test_cross_user_ticket_close_1008`

**Plan metadata commit:** Separate (this SUMMARY + state updates)

## Files Created/Modified

- `tests/integration/test_ws_ticket_safety.py` (new, 247 lines) — VERIFY-07 gold copy

## Decisions Made

- **CsrfMiddleware omitted from ws_app fixture** — WS handshake doesn't trigger HTTP CSRF and the ticket flow IS the WS auth path; matches `test_ws_ticket_flow.py` precedent. `POST /api/ws/ticket` succeeds without `X-CSRF-Token` because no CSRF guard is mounted in this stack.
- **Single-line monkeypatch.setattr** — `monkeypatch.setattr("app.services.ws_ticket_service.datetime", _FrozenDatetime)` stays on one line so the verifier grep gate `grep -c "monkeypatch.setattr.*ws_ticket_service.datetime"` returns ≥1. Line-wrapping the args dropped the count to 0 during initial implementation.
- **Two TestClients for cross-user drift** — User A holds the ticket-issuing cookie jar; User B is registered on a separate jar so the drift target FK is valid. Avoids cookie collision and respects Phase 10-04's `PRAGMA foreign_keys=ON`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Cross-user drift target must be FK-valid**
- **Found during:** Task 2 (test_cross_user_ticket_close_1008)
- **Issue:** Plan body specified `UPDATE tasks SET user_id = 9999 WHERE uuid = ...` (non-existent id). Phase 10-04 enabled `PRAGMA foreign_keys=ON` globally, so the UPDATE raised `sqlite3.IntegrityError: FOREIGN KEY constraint failed` and the test failed before the WS connection ever ran.
- **Fix:** Register a second user (User B) via `_register(client_b, "ws-crossuser-b@phase16.example.com")` and drift `tasks.user_id` to the real `user_id_b`. Two TestClient instances keep cookie jars isolated. Drift still triggers the handler's `consumed_user_id != task.user_id` check because the ticket was issued for User A.
- **Files modified:** tests/integration/test_ws_ticket_safety.py
- **Verification:** `pytest tests/integration/test_ws_ticket_safety.py -v` → 3/3 passed
- **Committed in:** `1ebee3b` (Task 2 commit)

**2. [Rule 1 - Bug] monkeypatch.setattr line-wrap broke verifier gate**
- **Found during:** Task 2 acceptance verification
- **Issue:** The plan's example used a wrapped form `monkeypatch.setattr(\n    "app.services.ws_ticket_service.datetime", _FrozenDatetime\n)`. The acceptance criterion `grep -c "monkeypatch.setattr.*ws_ticket_service.datetime"` matches per-line and returned 0.
- **Fix:** Inline the call to a single line: `monkeypatch.setattr("app.services.ws_ticket_service.datetime", _FrozenDatetime)`. Functionally identical; satisfies the grep gate.
- **Files modified:** tests/integration/test_ws_ticket_safety.py
- **Verification:** `grep -c "monkeypatch.setattr.*ws_ticket_service.datetime" tests/integration/test_ws_ticket_safety.py` → 1
- **Committed in:** `1ebee3b` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2× Rule 1 bug)
**Impact on plan:** Both fixes were small and necessary for green tests + grep-gate compliance. No scope creep; no architectural change.

## Issues Encountered

None — both deviations resolved inline during execution.

## Acceptance Criteria Results

### Task 1 (ws_app fixture + helpers)
- `grep -c "include_router(websocket_router\|include_router(ws_ticket_router\|include_router(auth_router"` = **3** (>=3) PASS
- `grep -c "WS_POLICY_VIOLATION"` = 1 in initial commit, **4** in final (>=1) PASS
- `grep -c "from tests.integration._phase16_helpers import"` = **1** (==1) PASS
- `grep -c "limiter.reset()"` = **2** (>=2) PASS

### Task 2 (3 attack cases)
- `pytest --collect-only`: **3** test functions collected (==3) PASS
- `pytest -x -q`: **exit 0**, 3 passed PASS
- `grep -c "WS_POLICY_VIOLATION"` = **4** (>=3) PASS
- `grep -c "monkeypatch.setattr.*ws_ticket_service.datetime"` = **1** (>=1) PASS
- `grep -c "UPDATE tasks SET user_id"` = **1** (>=1) PASS
- Nested-if invariant `grep -cE "        if .*:$"` = **0** (==0) PASS

### Plan-level
- 3 cases collected and pass (`pytest tests/integration/test_ws_ticket_safety.py -v` → 3 passed in ~2.3s)
- VERIFY-07 closed
- All 3 attack vectors close 1008 deterministically

## Self-Check: PASSED

- File `tests/integration/test_ws_ticket_safety.py` exists on disk (247 lines)
- Commit `b2ba092` (Task 1) present in `git log`
- Commit `1ebee3b` (Task 2) present in `git log`
- All plan acceptance criteria verified above
- All 3 tests run green

## Next Phase Readiness

- VERIFY-07 closed; gold copy in place for future regression suite
- Ready for Plan 16-06 (Migration Smoke, VERIFY-08) — no dependencies on this plan beyond `_phase16_helpers` (already provided by 16-01)
- Wave 1 (16-02..06) can continue in parallel — this plan modified only `tests/integration/test_ws_ticket_safety.py` (file-disjoint per plan design)

---
*Phase: 16-verification-cross-user-matrix-e2e*
*Plan: 05*
*Completed: 2026-04-30*
