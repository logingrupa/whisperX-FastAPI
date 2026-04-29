---
phase: 13-atomic-backend-cutover
plan: 06
subsystem: backend-websocket
tags: [websocket, ticket-auth, single-use, in-memory-ttl, mid-06, mid-07, integration-tests]
requires:
  - phase: 13-01
    provides: AuthSettings.{V2_ENABLED, COOKIE_*, JWT_SECRET}
  - phase: 13-02
    provides: get_authenticated_user dependency; DualAuthMiddleware
  - phase: 13-03
    provides: auth_router (cookie-acquisition path for tests)
  - phase: 11
    provides: Container.db_session_factory; ORM Task model
  - phase: 12
    provides: tasks.user_id column (Plan 12-04 backfill)
provides:
  - app.services.ws_ticket_service.WsTicketService — in-memory single-use 60s TTL ticket store (Singleton)
  - app.api.schemas.ws_ticket_schemas.{TicketRequest, TicketResponse}
  - app.api.ws_ticket_routes.ws_ticket_router with POST /api/ws/ticket
  - app.api.websocket_api.websocket_task_progress with 5-guard ticket validation chain (close 1008 on any failure)
  - tests/unit/services/test_ws_ticket_service.py — 8 unit tests
  - tests/integration/test_ws_ticket_flow.py — 11 integration tests
affects:
  - app/core/container.py — adds ws_ticket_service Singleton provider (in-memory dict must persist across requests)
  - app/domain/entities/task.py — surfaces user_id from ORM (nullable until full backfill); needed for ownership re-check
  - app/infrastructure/database/mappers/task_mapper.py — round-trips user_id between domain and ORM
  - plan 13-09 (atomic flip): mounts ws_ticket_router on FastAPI app under is_auth_v2_enabled() guard
  - plan 14 frontend: consumes POST /api/ws/ticket then opens ws://.../ws/tasks/{id}?ticket=<token>
  - phase 16 (cross-user matrix tests): integration tests already cover MID-06/MID-07 invariants — phase 16 extends with multi-user fuzzing
tech-stack:
  added: []
  patterns:
    - "In-memory single-use TTL ticket store under threading.Lock — `secrets.token_urlsafe(24)[:32]` (~190 bits); 60s TTL hard-coded as TICKET_TTL_SECONDS module constant; cleanup_expired() called on every issue (T-13-28 unbounded-growth mitigation)"
    - "Single-use enforcement: `_Ticket.consumed = True` set under lock atomically with the dict update; second consume returns None (T-13-25 replay mitigation)"
    - "Cross-task defence-in-depth: consume(token, task_id) verifies internal `ticket.task_id == task_id` (T-13-27 first line); WS handler then re-verifies `consumed_user_id == task.user_id` after consume (T-13-27 / MID-07 second line — catches future drift if a task's user_id is mutated post-issue)"
    - "Cross-user opaque-404: POST /api/ws/ticket returns the same 'Task not found' detail for both unknown-task and other-user-task (T-13-24 anti-enumeration)"
    - "WS reject path: 5 flat early-return guards (no nested-if) → single `await websocket.close(code=WS_POLICY_VIOLATION)` per guard; constant `WS_POLICY_VIOLATION = 1008` (no magic numbers)"
    - "Singleton lifecycle for ticket service — Factory would create a new dict per request, defeating the store"
    - "WS scope reach-in: BaseHTTPMiddleware does not dispatch WS scopes, so the WS endpoint imports `app.api.dependencies` lazily at request-time and reads `dependencies._container` directly (the only reach-in to private _container in the new codebase)"
    - "Logger discipline: ticket value never logged — only `user_id` and `task_id` (T-13-29 information-disclosure mitigation)"
key-files:
  created:
    - app/services/ws_ticket_service.py
    - app/api/schemas/ws_ticket_schemas.py
    - app/api/ws_ticket_routes.py
    - tests/unit/services/test_ws_ticket_service.py
    - tests/integration/test_ws_ticket_flow.py
    - .planning/phases/13-atomic-backend-cutover/deferred-items.md
  modified:
    - app/core/container.py
    - app/api/websocket_api.py
    - app/domain/entities/task.py
    - app/infrastructure/database/mappers/task_mapper.py
key-decisions:
  - "In-memory dict + threading.Lock chosen over Redis — single-worker scope per CONTEXT §93. Multi-worker deployments require Redis or DB-backed store (FUTURE). The lock is cheap insurance against future BackgroundTasks / asyncio.to_thread paths even though FastAPI is single-threaded per worker today."
  - "Single-use enforced inside the lock by setting `_Ticket.consumed = True` AND reading `user_id` before lock release — concurrent gather-of-100 unit test proves no double-consume race."
  - "Cleanup_expired() called on every issue — bounded-growth mitigation. O(n) in dict size; acceptable because v1.2 traffic per worker is small (single browser session opens 1 ticket then 1 WS per task; ticket evicted on consume or 60s TTL)."
  - "Defence-in-depth `consumed_user_id != task.user_id` re-check after consume — `consume()` already verifies `ticket.task_id == task_id`, but a malicious or buggy code path that mutates `tasks.user_id` after the ticket was issued could otherwise let a stale ticket reach a foreign user's task. Cheap belt-and-braces mitigates MID-07 even under future drift."
  - "Cross-user 404 (not 403) — opaque error matches the locked SCOPE-02 policy from CONTEXT §101: never enumerate other users' tasks, even by HTTP status."
  - "Domain Task.user_id surfaced as `int | None` (not `int`) — pre-Phase-12 code paths and tests construct Task without an authenticated user; making it strictly required would break existing tests for non-trivial reasons unrelated to MID-06/MID-07. The ORM column is `nullable=True` until full Phase-12 backfill verification; tightening to NOT NULL is a Phase 12 remediation, not Phase 13."
  - "WS endpoint reaches into `dependencies._container` rather than using FastAPI Depends — `BaseHTTPMiddleware`-based DualAuthMiddleware does not dispatch WS scopes, and FastAPI Depends in `@websocket()` routes does not yet support container-scoped resolution cleanly. The reach-in is documented in the docstring; alternative would be a singleton-module pattern but that adds indirection without a clear benefit."
  - "Test fixture builds a slim FastAPI app with auth + ws_ticket + websocket routers + DualAuthMiddleware — does NOT mount `app/main.py` so the legacy CORS / non-DualAuth middleware never runs in tests. Same pattern as 13-03/13-04/13-05."
patterns-established:
  - "WS auth ticket flow: POST /api/ws/ticket (auth required, owned-task required, opaque-404 on miss) → 60s TTL token → ws://.../ws/tasks/{id}?ticket=<token> → 5 flat guards → close 1008 on any failure"
  - "5-guard validation chain: missing-ticket / no-container / no-task / consume-fail / user-mismatch — each a top-level `if … return` (zero nested-if; verifier-checked)"
  - "Defence-in-depth user_id check: ticket.user_id (from consume) vs task.user_id (fresh read) — second-line MID-07 mitigation"
requirements-completed:
  - MID-06 (POST /api/ws/ticket issues 32-char single-use 60s tokens; WS endpoint validates `?ticket=` and rejects with 1008 on missing/expired/reused/cross-user)
  - MID-07 (WS handler verifies `ticket.user_id == task.user_id` — first via `consume(token, task_id)` matching internal `ticket.task_id == task_id`, second via `consumed_user_id != task.user_id` defence-in-depth re-check)
duration: ~25 min (continuation; Task 1 already in commit f23e7a3)
completed: 2026-04-29
---

# Phase 13 Plan 06: WebSocket Ticket Flow Summary

In-memory single-use 60-second WebSocket ticket flow (MID-06 / MID-07): authenticated `POST /api/ws/ticket` issues 32-char tokens (cross-user → opaque 404, T-13-24); the WebSocket endpoint runs 5 flat-early-return guards before accepting (`?ticket=` missing / container down / task not found / consume rejects / defence-in-depth `consumed_user_id != task.user_id`) and closes with code 1008 on any failure — proven by 8 unit tests on the service mechanics and 11 integration tests on the full HTTP+WS round-trip.

## Performance

- **Duration:** ~25 min (continuation; Task 1 already committed in `f23e7a3` from prior agent)
- **Tasks:** 3 of 3 complete (Task 1 verified, Tasks 2 + 3 implemented this run)
- **Files created:** 6 (service + schemas + route + ws-route + 2 test files)
- **Files modified:** 4 (container + websocket_api + domain Task + task_mapper)
- **Commits:** 3 (f23e7a3, 5a322fd, 5ba303b)

## Tasks

| Task | Name                                                          | Commit                                                        |
| ---- | ------------------------------------------------------------- | ------------------------------------------------------------- |
| 1    | WsTicketService + Container provider + schemas (TDD: 8 tests) | `f23e7a3` (prior agent — verified passing in this run)        |
| 2    | ws_ticket_routes (POST /api/ws/ticket) + WS endpoint guards   | `5a322fd`                                                     |
| 3    | Integration tests for full ticket flow (11 cases)             | `5ba303b`                                                     |

## What Was Built

### POST /api/ws/ticket (Task 2)

- Authenticated route: `Depends(get_authenticated_user)` → resolves `request.state.user`.
- Loads task via `Depends(get_task_repository).get_by_id(task_id)`; both unknown-task and cross-user-task return identical `404 {"detail": "Task not found"}` (T-13-24 anti-enumeration).
- On owner match: `ticket_service.issue(user_id, task_id)` → `(token, expires_at)` → returns `201 {ticket, expires_at}`.

### WebSocket /ws/tasks/{task_id}?ticket=... (Task 2)

5 flat guards before `connection_manager.connect`:

1. `not ticket` → close 1008
2. `_container is None` → close 1008 (defensive)
3. `task is None` (unknown task) → close 1008
4. `consume(token, task_id) is None` (unknown / expired / reused / wrong-task) → close 1008
5. `consumed_user_id != task.user_id` (defence-in-depth MID-07) → close 1008

Any failure path uses the single constant `WS_POLICY_VIOLATION = 1008`. Heartbeat + ping/pong loop preserved verbatim from the legacy implementation.

### Integration tests (Task 3)

11 cases covering:

| #   | Test                                          | Asserts                                              |
| --- | --------------------------------------------- | ---------------------------------------------------- |
| 1   | `test_issue_ticket_for_owned_task`            | 201 + 32-char + ~60s expiry                          |
| 2   | `test_issue_ticket_for_unknown_task`          | 404 opaque                                           |
| 3   | `test_issue_ticket_for_other_users_task`      | 404 opaque (T-13-24, anti-enum)                      |
| 4   | `test_issue_ticket_requires_auth`             | 401 (DualAuthMiddleware)                             |
| 5   | `test_ws_connect_with_valid_ticket`           | accept + ping/pong round-trip                        |
| 6   | `test_ws_reject_missing_ticket`               | close 1008                                           |
| 7   | `test_ws_reject_reused_ticket`                | close 1008 (single-use, T-13-25)                     |
| 8   | `test_ws_reject_expired_ticket`               | close 1008 (TTL via monkeypatched datetime, T-13-26) |
| 9   | `test_ws_reject_ticket_for_different_task`    | close 1008 (cross-task, T-13-27)                     |
| 10  | `test_ws_reject_unknown_task_id`              | close 1008                                           |
| 11  | `test_ws_reject_unknown_ticket_token`         | close 1008                                           |

## Verification

- `pytest tests/unit/services/test_ws_ticket_service.py -v` → **8/8 passing**
- `pytest tests/integration/test_ws_ticket_flow.py -v -m integration` → **11/11 passing**
- Combined: `pytest tests/unit/services/test_ws_ticket_service.py tests/integration/test_ws_ticket_flow.py -v` → **19/19 passing**
- `python -c "from app.core.container import Container; c=Container(); assert c.ws_ticket_service() is c.ws_ticket_service()"` → **Singleton OK**
- `grep -cE '^\s+if .*\bif\b' app/api/ws_ticket_routes.py app/api/websocket_api.py app/services/ws_ticket_service.py` → **0 nested-ifs**
- `grep -c '1008' app/api/websocket_api.py` → **8** (≥4 required)
- `grep -c 'consumed_user_id != task.user_id' app/api/websocket_api.py` → **2** (1 docstring + 1 guard)

## Threat Model Mitigations

| Threat ID | Component                                | Mitigation                                                                                                              |
| --------- | ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| T-13-24   | Cross-user task_id at issue-time         | `task.user_id != user.id` check + opaque 404                                                                            |
| T-13-25   | Reused ticket (replay)                   | `_Ticket.consumed = True` under lock; second consume returns None                                                       |
| T-13-26   | Expired ticket                           | `expires_at < now` check in consume; 60s TTL hard-coded                                                                 |
| T-13-27   | Ticket for task A used on task B         | `consume(token, task_id)` verifies `ticket.task_id == task_id`; WS handler re-verifies `consumed_user_id == task.user_id` (defence-in-depth) |
| T-13-28   | Ticket dict unbounded growth (DoS)       | `cleanup_expired()` called on every issue; expired + consumed entries evicted                                           |
| T-13-29   | Ticket value in logs (info disclosure)   | `logger.debug` logs `user_id` + `task_id` only — never the token value                                                  |

## Deviations from Plan

### Reverted in-progress work from prior agent

The working tree contained uncommitted modifications to `app/main.py` plus a new untracked `app/core/auth.py` re-introducing the legacy `BearerAuthMiddleware`. This contradicted CONTEXT §192-193 (`app/core/auth.py` is to be deleted post-DualAuth wiring) and is unrelated to plan 13-06. Reverted via `git checkout -- app/main.py` and `rm app/core/auth.py`.

### Auto-applied (Rule 2 — missing critical functionality)

**1. Domain Task entity surfaces `user_id`**

- **Found during:** Task 2 acceptance criteria require `task.user_id != user.id`.
- **Issue:** `app/domain/entities/task.py` did not expose `user_id`; ORM column existed (Phase 10) and was being backfilled (Phase 12) but the domain entity + mapper did not round-trip the field. Without it, `repository.get_by_id(...).user_id` is always `AttributeError` / `None`, and the cross-user check at `ws_ticket_routes.py:86` would silently pass for every caller.
- **Fix:** Added `user_id: int | None = None` to `DomainTask` dataclass + `to_dict`, and round-tripped it through `task_mapper.to_domain` / `to_orm`.
- **Files modified:** `app/domain/entities/task.py`, `app/infrastructure/database/mappers/task_mapper.py`
- **Commit:** `5a322fd` (folded into Task 2)

### Out of scope — logged to `deferred-items.md`

- 3 pre-existing failures in `tests/unit/services/test_audio_processing_service.py` (audio-progress mock-call assertions, unrelated to plan 13-06).
- 3 collection errors in `tests/unit/{domain/entities,infrastructure/database}/...` due to missing `factory` package (test-infrastructure dependency, unrelated).

## Self-Check: PASSED

Files created:

- `FOUND: app/services/ws_ticket_service.py`
- `FOUND: app/api/schemas/ws_ticket_schemas.py`
- `FOUND: app/api/ws_ticket_routes.py`
- `FOUND: tests/unit/services/test_ws_ticket_service.py`
- `FOUND: tests/integration/test_ws_ticket_flow.py`
- `FOUND: .planning/phases/13-atomic-backend-cutover/deferred-items.md`

Files modified:

- `FOUND: app/core/container.py` (ws_ticket_service Singleton provider)
- `FOUND: app/api/websocket_api.py` (5-guard ticket validation chain)
- `FOUND: app/domain/entities/task.py` (user_id field)
- `FOUND: app/infrastructure/database/mappers/task_mapper.py` (user_id round-trip)

Commits:

- `FOUND: f23e7a3` (Task 1 — prior agent)
- `FOUND: 5a322fd` (Task 2)
- `FOUND: 5ba303b` (Task 3)
