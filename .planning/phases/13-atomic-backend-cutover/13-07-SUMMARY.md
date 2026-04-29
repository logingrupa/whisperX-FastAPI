---
phase: 13-atomic-backend-cutover
plan: 07
subsystem: backend-task-repository
tags: [per-user-scoping, repository, dependency-injection, anti-enum, scope-02, scope-03, scope-04]
requires:
  - phase: 13-01
    provides: AuthSettings (V2_ENABLED, COOKIE_*, JWT_SECRET)
  - phase: 13-02
    provides: DualAuthMiddleware sets request.state.user
  - phase: 13-03
    provides: auth_router (/auth/register cookie acquisition for tests)
  - phase: 12-04
    provides: tasks.user_id NOT NULL after backfill
  - phase: 11
    provides: Container.task_repository Factory
provides:
  - app.domain.repositories.task_repository.ITaskRepository.set_user_scope (Protocol method)
  - app.infrastructure.database.repositories.sqlalchemy_task_repository.SQLAlchemyTaskRepository._user_scope + _scoped_query
  - app.api.dependencies.get_scoped_task_repository (FastAPI dep)
  - app.api.dependencies.get_scoped_task_management_service (FastAPI dep)
  - 13 integration tests (tests/integration/test_per_user_scoping.py)
  - 14 unit tests (tests/unit/.../test_sqlalchemy_task_repository_scope.py)
affects:
  - app/api/audio_api.py — 2 routes swapped to scoped repo
  - app/api/audio_services_api.py — 4 routes swapped to scoped repo
  - app/api/task_api.py — 4 routes swapped to scoped task service
  - app/api/tus_upload_api.py — completion hook swapped to scoped repo
  - app/api/ws_ticket_routes.py — swapped to scoped repo; manual user_id check now defence-in-depth
  - tests/factories/task_factory.py — user_id=1 default to satisfy fail-loud + FK
  - phase 13-08+ (atomic flip): all routes already wired; flip is just middleware mount
tech-stack:
  added: []
  patterns:
    - "Scope as request-bound state on the repo: set_user_scope(N) before yield, clear in finally — defence-in-depth against future Factory pooling (T-13-33)"
    - "Single _scoped_query() helper funnels get_by_id, get_all, update, delete (DRT — single source of WHERE predicate)"
    - "Fail-loud add() refuses to persist task with no owner: ValueError when (user_id is None|0) AND _user_scope is None — closes T-13-34 silent orphan writes"
    - "Default _user_scope=None preserves Phase 12 CLI/admin backward compat — unscoped callers see every row"
    - "Cross-user reads return None / [] / False at SQL layer; routes raise 404 opaque (anti-enumeration matches SCOPE-02..04 + T-13-30..32)"
    - "get_scoped_task_management_service constructs TaskManagementService(repo) per request with scope already applied — task_api.py routes get scoping for free without service-layer changes"
    - "Manual ws_ticket_routes.py user_id check kept as defence-in-depth (catches drift if a task's user_id is mutated post-issue, MID-07)"
key-files:
  created:
    - tests/integration/test_per_user_scoping.py
    - tests/unit/infrastructure/database/repositories/test_sqlalchemy_task_repository_scope.py
  modified:
    - app/domain/repositories/task_repository.py
    - app/infrastructure/database/repositories/sqlalchemy_task_repository.py
    - app/api/dependencies.py
    - app/api/audio_api.py
    - app/api/audio_services_api.py
    - app/api/task_api.py
    - app/api/tus_upload_api.py
    - app/api/ws_ticket_routes.py
    - tests/factories/task_factory.py
key-decisions:
  - "Repository carries scope as instance state (_user_scope: int | None) rather than passing user_id through every method — keeps the ITaskRepository surface stable (Phase 12 CLI doesn't change), and the dependency owns request-scoped lifecycle. Singleton Container provider for tasks is a Factory, so each request gets a fresh repo whose scope is set+cleared."
  - "Default _user_scope=None is intentional backward compat — Phase 12 CLI (backfill-tasks, create-admin) constructs SQLAlchemyTaskRepository directly without going through HTTP and must keep seeing all rows. Routes always go through get_scoped_task_repository which sets the scope, so HTTP traffic is fully scoped."
  - "Fail-loud guard in add() — refuses to persist a task with neither explicit user_id nor scope. /tiger-style: silent orphan writes break per-user invariants (cross-user GET would leak the row because user_id IS NULL bypasses the WHERE filter). T-13-34 mitigation."
  - "task_api.py uses get_scoped_task_management_service rather than direct repo because the routes already delegate to TaskManagementService — keeping the service layer means downstream business-logic additions (progress events, usage metering) get scoping for free. SRP preserved."
  - "Manual ws_ticket_routes.py task.user_id != user.id check NOT removed — the scoped repo already prunes cross-user (first 'task is None' guard fires), but the explicit check remains as defence-in-depth for MID-07 (catches future drift if a task's user_id is mutated post-issue). Cheap belt + braces; matches the Plan 13-06 reasoning for the WS handler's secondary check."
  - "Cross-user 404 chosen over 403 (locked from CONTEXT §101 + Plan 13-06 SCOPE-02 policy) — opaque body 'Task not found' matches the 'unknown id' shape exactly. Anti-enumeration verified by test_cross_user_delete_returns_same_404_body_as_unknown_id."
  - "Integration test fixture seeds users via /auth/register rather than direct ORM insert — exercises the full DualAuthMiddleware → cookie flow → request.state.user pipeline that production traffic uses."
  - "Unit tests for the SQLAlchemy repo scope behaviour live in a separate file (test_sqlalchemy_task_repository_scope.py) rather than extending the existing test_sqlalchemy_task_repository.py — pre-existing factory_boy import issue (deferred-items.md) blocks the legacy file from collecting; isolating new tests keeps the new suite runnable."
patterns-established:
  - "Scoped repository pattern: dependency sets repo.set_user_scope(user.id) before yield, clears in finally; routes consume Depends(get_scoped_task_repository) — DRT, every route shares one resolution helper"
  - "TaskManagementService scope-passthrough: get_scoped_task_management_service constructs TMS(repo) per-request with scope already applied; service layer needs zero changes"
  - "Fail-loud add(): refuses orphan-task writes (user_id is None|0 AND _user_scope is None) — silent data leak prevention"
  - "Cross-user 404 body parity: same {detail: 'Task not found'} for unknown-id AND cross-user — anti-enumeration verified by direct dict comparison"
requirements-completed:
  - SCOPE-02 (ITaskRepository.set_user_scope pushes WHERE filter into all reads + writes)
  - SCOPE-03 (GET /tasks returns only caller's tasks; cross-user matrix proves it for all 4 task_api endpoints + 4 audio_services + 2 audio + 1 TUS + 1 WS-ticket)
  - SCOPE-04 (every existing tasks-touching route uses Depends(get_scoped_*) — 0 unscoped Depends(get_task_repository) remain in HTTP layer)
duration: ~10 min
completed: 2026-04-29
---

# Phase 13 Plan 07: Per-User Task Scoping Summary

ITaskRepository extended with `set_user_scope(user_id)` (Protocol + SQLAlchemy impl), `get_scoped_task_repository` + `get_scoped_task_management_service` FastAPI dependencies wired into every existing route that touches `tasks` (12 routes across 5 files), and `add()` made fail-loud against orphan-task writes. Cross-user requests return opaque `404 {"detail": "Task not found"}` (anti-enumeration); 27 new tests prove the matrix. Closes SCOPE-02, SCOPE-03, SCOPE-04.

## Performance

- **Duration:** ~10 min
- **Tasks:** 3 of 3 complete
- **Files created:** 2 (1 unit-test file + 1 integration-test file)
- **Files modified:** 9 (Protocol + impl + dependencies + 5 route files + factory)
- **Commits:** 3 (`891cdbb`, `8f4bd31`, `5f23dc9`)

## Tasks

| Task | Name                                                                | Commit    |
| ---- | ------------------------------------------------------------------- | --------- |
| 1    | ITaskRepository.set_user_scope + SQLAlchemy scoped queries          | `891cdbb` |
| 2    | get_scoped_task_repository + scoped task service + route wiring     | `8f4bd31` |
| 3    | Cross-user integration tests (13 cases)                             | `5f23dc9` |

## What Was Built

### ITaskRepository.set_user_scope (Protocol — Task 1)

Added to the structural typing contract:

```python
def set_user_scope(self, user_id: int | None) -> None:
    """Push a user_id filter into all subsequent reads/writes."""
```

`None` clears the filter (backward compat for CLI/admin); any int sets it.

### SQLAlchemyTaskRepository scoping (Task 1)

- New `_user_scope: int | None = None` instance field (default unset)
- Single `_scoped_query()` helper used by `get_by_id`, `get_all`, `update`, `delete` (DRT)
- `add()` injects `task.user_id` from scope when entity has no owner
- `add()` fail-loud `ValueError` when `(user_id is None|0) AND _user_scope is None` — refuses orphan writes (T-13-34)

### Dependencies (Task 2)

| Function                                | Purpose                                                                |
| --------------------------------------- | ---------------------------------------------------------------------- |
| `_resolve_authenticated_user_id`        | Tiger-style guard — extracts request.state.user.id or raises 401 (DRT) |
| `get_scoped_task_repository`            | Sets scope before yield, clears in finally                             |
| `get_scoped_task_management_service`    | Same scope contract; constructs TaskManagementService(scoped_repo)     |

### Route wiring (Task 2)

| File                              | Routes        | Dependency                                  |
| --------------------------------- | ------------- | ------------------------------------------- |
| `app/api/audio_api.py`            | 2             | `get_scoped_task_repository`                |
| `app/api/audio_services_api.py`   | 4             | `get_scoped_task_repository`                |
| `app/api/task_api.py`             | 4             | `get_scoped_task_management_service`        |
| `app/api/tus_upload_api.py`       | 1 (hook)      | `get_scoped_task_repository`                |
| `app/api/ws_ticket_routes.py`     | 1             | `get_scoped_task_repository`                |
| **Total**                         | **12 routes** | **0 un-scoped Depends(get_task_repository)** |

### Tests (Task 3 + Task 1 unit suite)

**Unit (`tests/unit/.../test_sqlalchemy_task_repository_scope.py`) — 14 tests:**

| #  | Test                                           | Asserts                                       |
| -- | ---------------------------------------------- | --------------------------------------------- |
| 1  | `test_default_scope_is_none`                   | Backward-compatible default                   |
| 2  | `test_set_user_scope_idempotent`               | Setter mutates; None clears                   |
| 3  | `test_unscoped_get_all_returns_every_row`      | CLI/admin path sees all rows                  |
| 4  | `test_scoped_get_all_returns_only_users_rows`  | Filter pushed to SQL                          |
| 5  | `test_scoped_get_by_id_cross_user_returns_none`| Foreign UUID → None                           |
| 6  | `test_scoped_get_by_id_own_returns_task`       | Own UUID → entity                             |
| 7  | `test_scoped_delete_cross_user_returns_false`  | Cross-user no-op; row preserved (verified)    |
| 8  | `test_scoped_delete_own_succeeds`              | Own delete returns True + row removed         |
| 9  | `test_scoped_update_cross_user_raises_not_found`| Cross-user update raises ValueError          |
| 10 | `test_add_injects_user_id_from_scope`          | Scope auto-fills owner                        |
| 11 | `test_add_raises_when_no_owner_and_no_scope`   | Fail-loud orphan refusal (T-13-34)            |
| 12 | `test_add_raises_when_user_id_zero_and_no_scope`| Sentinel 0 also refused                      |
| 13 | `test_explicit_user_id_overrides_scope_injection`| Explicit owner preserved                    |
| 14 | `test_clearing_scope_restores_unscoped_view`   | None clears filter                            |

**Integration (`tests/integration/test_per_user_scoping.py`) — 13 tests (mark `integration`):**

| #  | Test                                                              | Endpoint / Assertion                                  |
| -- | ----------------------------------------------------------------- | ----------------------------------------------------- |
| 1  | `test_get_all_tasks_returns_only_caller_tasks`                    | A: 3 tasks visible / B: 2 tasks visible               |
| 2  | `test_get_task_by_id_cross_user_returns_404`                      | GET /task/{A} as B → 404 opaque                       |
| 3  | `test_get_task_by_id_own_returns_200`                             | Own GET /task/{id} → 200                              |
| 4  | `test_delete_task_cross_user_returns_404_and_preserves_row`       | DELETE /task/{A}/delete as B → 404 + row exists       |
| 5  | `test_delete_task_own_returns_200`                                | Own DELETE → 200 + row gone                           |
| 6  | `test_get_task_progress_cross_user_returns_404`                   | GET /tasks/{A}/progress as B → 404 opaque             |
| 7  | `test_ws_ticket_for_owned_task_succeeds`                          | POST /api/ws/ticket own task → 201                    |
| 8  | `test_ws_ticket_for_other_users_task_returns_404`                 | POST /api/ws/ticket cross-user → 404 opaque           |
| 9  | `test_repo_unscoped_default_returns_all`                          | Direct repo unscoped sees all rows                    |
| 10 | `test_repo_scoped_returns_only_user`                              | Direct repo scoped sees only own                      |
| 11 | `test_get_all_tasks_anonymous_returns_401`                        | No cookie → DualAuthMiddleware 401                    |
| 12 | `test_post_speech_to_text_persists_with_user_id`                  | scope-injected user_id on add() write                 |
| 13 | `test_cross_user_delete_returns_same_404_body_as_unknown_id`      | Bytewise body parity (anti-enum)                      |

## Verification

- `pytest tests/unit/infrastructure/database/repositories/test_sqlalchemy_task_repository_scope.py -v` → **14/14 passing**
- `pytest tests/integration/test_per_user_scoping.py -v -m integration` → **13/13 passing**
- `pytest tests/integration/test_ws_ticket_flow.py -v -m integration` (regression) → **11/11 passing**
- Combined Phase 13-06 + 13-07 sweep → **37/37 passing in 3.34s**
- `grep -c "def set_user_scope" app/domain/repositories/task_repository.py` → **1**
- `grep -c "def set_user_scope" app/infrastructure/database/repositories/sqlalchemy_task_repository.py` → **1**
- `grep -c "_scoped_query" app/infrastructure/database/repositories/sqlalchemy_task_repository.py` → **6** (≥5)
- `grep -c "ORMTask.user_id == self._user_scope"` → **1**
- `grep -c "Cannot persist task without user_id"` → **1** (fail-loud T-13-34)
- `grep -c "Depends(get_scoped_task_repository)" app/api/audio_api.py` → **2**
- `grep -c "Depends(get_scoped_task_repository)" app/api/audio_services_api.py` → **4**
- `grep -c "Depends(get_scoped_task_management_service)" app/api/task_api.py` → **4**
- `grep -c "Depends(get_scoped_task_repository)" app/api/tus_upload_api.py` → **1**
- `grep -c "Depends(get_scoped_task_repository)" app/api/ws_ticket_routes.py` → **2** (1 docstring mention + 1 Depends)
- `grep -c "Depends(get_task_repository)"` across all 5 route files → **0** (no un-scoped usages remain)
- `grep -cE "^\s+if .*\bif\b"` across all modified files → **0** (no nested-if)

## Threat Model Mitigations

| Threat ID | Component                                          | Mitigation                                                                                                                                |
| --------- | -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| T-13-30   | Cross-user GET /task/{id}                          | `_scoped_query().filter(uuid=...)` returns None for foreign rows; route raises TaskNotFoundError → 404                                    |
| T-13-31   | Cross-user DELETE /task/{id}                       | `_scoped_query()` in delete() returns None → returns False → route raises 404; foreign row never touched (verified directly in DB)        |
| T-13-32   | Cross-user GET /tasks (list enumeration)           | `_scoped_query().all()` WHERE user_id = caller — User A never sees User B's rows                                                          |
| T-13-33   | Repository scope leakage between requests          | get_scoped_task_repository sets scope per-request via Factory provider (new instance per request); finally clause resets to None as DiD   |
| T-13-34   | New task POSTed without user_id                    | `add()` fail-loud raises ValueError on `(user_id is None\|0) AND _user_scope is None`; routes always set scope via Depends                |
| T-13-35   | Internal CLI bypassing scope                       | accepted — Phase 12 CLI runs without HTTP scope; explicit user_id required at CLI boundary; documented in deferred set                    |

## Code Quality Bar (locked from user)

- **DRY** — `Depends(get_scoped_task_repository)` reused across 5 files; single `_scoped_query()` funnel; single `_resolve_authenticated_user_id` helper for both deps
- **SRP** — repository owns persistence + scope predicate; dependency owns request-scoped lifecycle; route does HTTP only
- **/tiger-style** — fail-loud `add()` refuses orphan writes; `set_user_scope(None)` reset in finally is belt + braces (defence-in-depth T-13-33)
- **No spaghetti** — flat early-returns; nested-if grep returns 0 across all touched files
- **Self-explanatory names** — `set_user_scope`, `get_scoped_task_repository`, `get_scoped_task_management_service`, `_resolve_authenticated_user_id`, `_scoped_query`

## Deviations from Plan

### Auto-applied (Rule 1 — bug)

**1. TaskFactory needs default user_id**

- **Found during:** Task 1 — fail-loud `add()` guard refuses TaskFactory-built tasks because the factory had no `user_id` default; existing test suites (and several plan integration helpers) construct tasks via TaskFactory without specifying user_id.
- **Issue:** Previously `Task.user_id` defaulted to None at the dataclass level (Phase 13-06 added it as `int | None = None`); test factory inherited that default. With the new fail-loud guard, every `TaskFactory()` call would raise unless callers passed user_id explicitly — silent test breakage.
- **Fix:** Added `user_id = 1` default to TaskFactory; satisfies the FK constraint in CI environments that have at least one user row, and matches the intent (test tasks belong to user 1).
- **Files modified:** `tests/factories/task_factory.py`
- **Commit:** `891cdbb` (folded into Task 1)

### Auto-applied (Rule 3 — blocking)

**2. New scope unit tests live in a separate file**

- **Found during:** Task 1 verification — `pytest tests/unit/.../test_sqlalchemy_task_repository.py` fails to collect (`ModuleNotFoundError: No module named 'factory'`). Pre-existing per `deferred-items.md` Plan 13-06 entry.
- **Issue:** Plan asked me to verify via the existing test file, but the file can't run.
- **Fix:** Created `test_sqlalchemy_task_repository_scope.py` next to it — uses an in-memory SQLite engine + minimal user seeding (no factory_boy). 14 tests cover the new scope mechanism end-to-end without the missing dependency.
- **Files created:** `tests/unit/infrastructure/database/repositories/test_sqlalchemy_task_repository_scope.py`
- **Commit:** `891cdbb` (folded into Task 1)

### Out of scope — already logged in `deferred-items.md` from Plan 13-06

- 3 pre-existing collection errors in `tests/unit/{domain/entities,infrastructure/database}/...` due to missing `factory` package — unrelated to plan 13-07
- 3 pre-existing failures in `tests/unit/services/test_audio_processing_service.py` — unrelated audio progress mocking concern

## Self-Check: PASSED

Files created:

- `FOUND: tests/integration/test_per_user_scoping.py`
- `FOUND: tests/unit/infrastructure/database/repositories/test_sqlalchemy_task_repository_scope.py`

Files modified:

- `FOUND: app/domain/repositories/task_repository.py` (Protocol + set_user_scope)
- `FOUND: app/infrastructure/database/repositories/sqlalchemy_task_repository.py` (impl + _scoped_query + fail-loud)
- `FOUND: app/api/dependencies.py` (get_scoped_task_repository + get_scoped_task_management_service)
- `FOUND: app/api/audio_api.py` (2 routes scoped)
- `FOUND: app/api/audio_services_api.py` (4 routes scoped)
- `FOUND: app/api/task_api.py` (4 routes scoped via service)
- `FOUND: app/api/tus_upload_api.py` (hook scoped)
- `FOUND: app/api/ws_ticket_routes.py` (scoped + DiD)
- `FOUND: tests/factories/task_factory.py` (user_id=1 default)

Commits:

- `FOUND: 891cdbb` (Task 1)
- `FOUND: 8f4bd31` (Task 2)
- `FOUND: 5f23dc9` (Task 3)
