---
phase: 19-auth-di-refactor
plan: 12
subsystem: auth

tags: [fastapi, middleware, csrf, depends, deletion]

# Dependency graph
requires:
  - phase: 19-auth-di-refactor (Plans 05-07)
    provides: |
      csrf_protected Depends factory + every cookie-auth state-mutating
      router opted into dependencies=[Depends(csrf_protected)] (account,
      key, billing, task, ws_ticket; per-route on /auth/logout-all).
provides:
  - "CsrfMiddleware DELETED — CSRF lives only in Depends(csrf_protected)"
  - "Single-middleware stack: CORSMiddleware only (1 entry confirmed via app.user_middleware)"
  - "Obsolete unit test test_csrf_middleware.py DELETED in same commit as the class"
  - "TestGetAuthenticatedUser RELOCATED to tests/unit/api/test_dependencies_request_state.py — coverage of get_authenticated_user / get_current_user_id helpers preserved verbatim (still used by audio_api.py + audio_services_api.py)"
affects: [19-13 container-delete, 19-16 dead-code-sweep]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single-middleware stack invariant: app.add_middleware(CORSMiddleware) is the only middleware registration"
    - "Coverage-preservation discipline: when deleting a 'mixed' test module that holds tests for unrelated live code, relocate the orphan tests instead of dropping coverage"

key-files:
  created:
    - "tests/unit/api/test_dependencies_request_state.py — TestGetAuthenticatedUser (3 cases) relocated from deleted module; tests get_authenticated_user + get_current_user_id helpers still used by audio_api.py / audio_services_api.py"
  modified:
    - "app/main.py — removed `from app.core.csrf_middleware import CsrfMiddleware` import; removed `app.add_middleware(CsrfMiddleware, container=container)` registration; updated single-stack docstring to past-tense"
    - "app/api/dependencies.py — comment cleanup: stripped literal `CsrfMiddleware` tokens from csrf_protected docstring/section header (grep-gate hygiene, recurrence #7 of docstring-grep-tax pattern)"
    - ".planning/phases/19-auth-di-refactor/deferred-items.md — logged pre-existing test_free_tier_gate failure (Container-not-init in test fixture, Plan 19-13 territory)"
  deleted:
    - "app/core/csrf_middleware.py (73 lines)"
    - "tests/unit/core/test_csrf_middleware.py (TestCsrfMiddleware: 11 cases — obsolete, code deleted)"

key-decisions:
  - "Plan said 'delete the unit test file outright' — but the file held a TestGetAuthenticatedUser class testing live code (get_authenticated_user / get_current_user_id, used by audio_api.py:70/178 + audio_services_api.py:90/285). Blind deletion would have lost 3 unit-test cases for live helpers. Per Rule 2 (auto-add missing critical functionality / preserve correctness coverage), relocated TestGetAuthenticatedUser to a properly named module before deleting the original. CsrfMiddleware test cases (11) WERE deleted as the plan specified — they tested deleted code."
  - "Comment hygiene applied to app/api/dependencies.py + app/main.py — the literal token `CsrfMiddleware` appeared in 4 docstrings/comments. Plan acceptance criterion `grep -rn CsrfMiddleware app/` == 0 forces comment cleanup (recurrence #7 of the cross-plan docstring-grep-tax pattern documented in 19-11-SUMMARY decision #1)."
  - "Excluded app/docs/openapi.json + app/docs/openapi.yaml from this commit — both pre-existing modifications (set-ordering nondeterminism in audio/video extension lists) unrelated to Plan 12; staged individually per CLAUDE.md (`Stage task-related files individually, NEVER -A`)."

patterns-established:
  - "Mixed-module deletion rule: before deleting a test file, scan for unrelated test classes; relocate orphans before delete to preserve coverage"
  - "Single-middleware stack as a structural invariant: `len(app.user_middleware)` is now 1 (CORSMiddleware) — easy boot-time assertion if a future plan wants to enforce it"

requirements-completed:
  - REFACTOR-03

# Execution metrics
metrics:
  duration: ~14 min
  completed: 2026-05-02
  tasks-total: 1
  tasks-completed: 1
---

# Phase 19 Plan 12: delete-csrf-middleware Summary

CsrfMiddleware class + obsolete unit test deleted atomically. CSRF defence now lives exclusively in `Depends(csrf_protected)` on every cookie-auth state-mutating router (account, key, billing, task, ws_ticket; per-route on /auth/logout-all). Middleware stack collapsed to CORSMiddleware only (verified: `len(app.user_middleware) == 1`). Phase 16-04 + Plan 19-05 CSRF integration tests stay green — the 403 enforcement path is structurally identical, just relocated from middleware-dispatch to dep-resolution.

## What Changed

### Deleted
- `app/core/csrf_middleware.py` (73 lines, 1 class) — `CsrfMiddleware(BaseHTTPMiddleware)` with `dispatch()` method handling GET-bypass / bearer-skip / cookie-auth CSRF double-submit / public-allowlist branches.
- `tests/unit/core/test_csrf_middleware.py` — `TestCsrfMiddleware` (11 cases). Class tested deleted code; integration coverage in `test_csrf_enforcement.py` (Phase 16-04) + `test_csrf_protected_dep.py` (Plan 19-05) remains 1:1 equivalent.

### Modified
- `app/main.py` (lines 47-48 + 188-198): import + `app.add_middleware(CsrfMiddleware, ...)` call removed; single-stack docstring rewritten from "Plan 19-12 confirms…" to "Plan 19-12 deleted the legacy CSRF middleware". Final middleware stack: CORSMiddleware only.
- `app/api/dependencies.py` (csrf_protected section, lines 769-795): docstring + section header cleaned to drop the literal `CsrfMiddleware` token — required to pass `grep -rn 'CsrfMiddleware' app/` == 0 acceptance gate. Behavior unchanged.

### Created
- `tests/unit/api/test_dependencies_request_state.py` (50 lines, 3 cases): `TestGetAuthenticatedUser` relocated from the deleted module. Tests `get_authenticated_user` + `get_current_user_id` from `app.api.dependencies` — these helpers are STILL USED by `app/api/audio_api.py:70/178` and `app/api/audio_services_api.py:90/285`. Plan 19-13 will sweep those callsites; until then, coverage stays.

## Verification Results

| Check | Command | Result |
|-------|---------|--------|
| File deleted | `test ! -f app/core/csrf_middleware.py` | PASS |
| Test deleted | `test ! -f tests/unit/core/test_csrf_middleware.py` | PASS |
| Zero class refs in app/ | `grep -rn 'CsrfMiddleware' app/` | 0 matches |
| Zero imports anywhere | `grep -rn '^from app.core.csrf_middleware' app/ tests/` | 0 matches |
| App boots | `python -c "from app.main import app; print(len(app.user_middleware))"` | 1 (CORS only) |
| Phase 16-04 CSRF integration | `pytest tests/integration/test_csrf_enforcement.py` | 4/4 PASS |
| Plan 19-05 csrf_protected dep | `pytest tests/integration/test_csrf_protected_dep.py` | 5/5 PASS |
| Relocated unit cases | `pytest tests/unit/api/test_dependencies_request_state.py` | 3/3 PASS |
| pytest collection | `pytest --collect-only` | 484 collected, 0 errors |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Preserve coverage] Relocated TestGetAuthenticatedUser before deleting test module**

- **Found during:** Task 1 read-first pass on `tests/unit/core/test_csrf_middleware.py`
- **Issue:** The plan instructs `git rm tests/unit/core/test_csrf_middleware.py` justified as "tests deleted code". File contained two classes: `TestCsrfMiddleware` (11 cases — IS testing deleted code, plan-correct) and `TestGetAuthenticatedUser` (3 cases — testing `get_authenticated_user` / `get_current_user_id` in `app/api/dependencies.py:237-257`). Those helpers are LIVE code: `audio_api.py:70/178` + `audio_services_api.py:90/285` consume them via `Depends(get_authenticated_user)`. Plan 19-13 will sweep those callsites but doesn't yet — blind deletion would drop unit coverage for live helpers.
- **Fix:** Created `tests/unit/api/test_dependencies_request_state.py` with `TestGetAuthenticatedUser` content verbatim (50 lines, 3 cases preserved 1:1). Then proceeded with `git rm` of the original. Atomic in same commit.
- **Files modified:** `tests/unit/api/test_dependencies_request_state.py` (new), `tests/unit/core/test_csrf_middleware.py` (deleted)
- **Commit:** see "Final commit" below

**2. [Rule 3 — Unblock acceptance gate] Comment cleanup in app/api/dependencies.py + app/main.py**

- **Found during:** Verification grep
- **Issue:** After removing import + middleware registration, `grep -rn 'CsrfMiddleware' app/` still returned 4 matches — all in docstrings/comments at `app/main.py:189` (single-stack doc) and `app/api/dependencies.py:772/777/794` (csrf_protected section). Acceptance criterion is literal-token-zero.
- **Fix:** Rewrote affected comments to past-tense / paraphrase (`CsrfMiddleware` → `the legacy CSRF middleware` / `the legacy middleware`). Behavior unchanged; only literal token stripped.
- **Files modified:** `app/main.py`, `app/api/dependencies.py`
- **Pattern:** Recurrence #7 of the docstring-grep-tax pattern first noted in Plan 15-02; future planners should pre-audit every literal-token gate against docstrings.

### Auth Gates

None.

### Out-of-Scope (Logged to deferred-items.md)

**`tests/integration/test_free_tier_gate.py::test_free_user_6th_transcribe_returns_429_with_retry_after`** fails with `RuntimeError: Container not initialized` at `app/api/dependencies.py:366`. Verified pre-existing on HEAD (`c4dfbfd`) via `git stash` round-trip — same failure, same line, before any Plan 12 changes. Root cause: test bypasses `app/main.py`'s `dependencies.set_container(container)` boot path while exercising a v1.1 audio route that still routes through `_container`. Resolution lands naturally in Plan 19-13 when `_container` is deleted.

Pre-existing failure inventory (all confirmed unchanged by `git stash` round-trip):
- `tests/integration/test_free_tier_gate.py` — 11 cases (Container-not-init)
- `tests/integration/test_task_lifecycle.py` — 7 cases (sqlite3 FK constraint, Phase 11 deferred)
- `tests/integration/test_whisperx_services.py::test_process_audio_common_gpu` — 1 case (GPU)
- `tests/unit/core/test_config.py` + `tests/unit/services/test_audio_processing_service.py` — 4 cases (Phase 11 deferred)

Net effect of Plan 19-12 on suite: -11 deleted obsolete unit cases + 3 relocated unit cases. Zero new failures introduced.

## Final Commit

`refactor(19-12): delete CsrfMiddleware class — CSRF is now Depends(csrf_protected)`

Files in commit:
- DELETED: `app/core/csrf_middleware.py`
- DELETED: `tests/unit/core/test_csrf_middleware.py`
- MODIFIED: `app/main.py` (import + registration + docstring)
- MODIFIED: `app/api/dependencies.py` (comment cleanup)
- CREATED: `tests/unit/api/test_dependencies_request_state.py` (relocated coverage)

## Self-Check: PASSED

- FOUND: app/core/csrf_middleware.py is DELETED (intentional, per plan)
- FOUND: tests/unit/core/test_csrf_middleware.py is DELETED (intentional, per plan)
- FOUND: tests/unit/api/test_dependencies_request_state.py (new, relocated coverage)
- FOUND: .planning/phases/19-auth-di-refactor/19-12-SUMMARY.md
- FOUND: commit bb41522 in `git log`
