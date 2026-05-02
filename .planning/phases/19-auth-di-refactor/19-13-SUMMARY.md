---
phase: 19-auth-di-refactor
plan: 13
subsystem: auth-di
tags: [fastapi, depends-chain, dependency-injection, refactor, single-namespace]

requires:
  - phase: 19-auth-di-refactor
    provides: |
      Plan 19-02 lru-cached singletons in app/core/services.py;
      Plan 19-03 get_db + _v2 repo/service factories;
      Plan 19-04 authenticated_user Depends + scoped task repo;
      Plan 19-05 csrf_protected Depends factory;
      Plans 19-06..09 router migrations off the legacy DI container;
      Plan 19-10 dependency_overrides[get_db] test seam;
      Plan 19-11 DualAuth + BearerAuth deletion;
      Plan 19-12 CsrfMiddleware deletion (final HTTP-stack collapse).

provides:
  - "Single namespace Depends chain — every helper in app/api/dependencies.py uses no-suffix names (get_db / get_user_repository / get_auth_service / authenticated_user / csrf_protected / etc.)."
  - "DELETED app/core/container.py + dropped dependency-injector library from pyproject.toml + uv.lock."
  - "DELETED 16 legacy `_container.X()` helpers from app/api/dependencies.py + the `_container` global + `set_container` function."
  - "Migrated audio_api.py + audio_services_api.py to Depends(authenticated_user) — last v1.1 routes off the deleted request.state-population path; resolves the pre-existing test_free_user_6th_transcribe_returns_429_with_retry_after failure noted in Plan 12 SUMMARY."
  - "CLI helpers (app/cli/_helpers.py) rewritten to a Container-shaped facade backed by SessionLocal + lru-cached singletons (no Container() reach-in)."
  - "Test fixture cleanup: DELETED tests/fixtures/test_container.py + emptied tests/fixtures/__init__.py + dropped the `test_container` pytest fixture from tests/conftest.py."

affects: [phase-20-perf-optimization, future-cli-commands]

tech-stack:
  added: []
  removed:
    - "dependency-injector (4.41.0+) — entire library removed; lru_cache + per-request Depends chain replace it"
  patterns:
    - "Single-namespace Depends factories: get_db + repo/service factories chain off Depends(get_db); ONE Session per request, closed once in get_db's finally (D2 lock)."
    - "Container-shaped CLI facade: when migrating away from a DI library but tests patch container.X(), preserve the call shape via a tiny dataclass facade exposing the patched attributes — keeps test seams stable across the refactor."
    - "Pre-existing Plan-noted test failure resolution: Plan 12 SUMMARY flagged test_free_user_6th_transcribe_returns_429_with_retry_after as failing due to dependencies._container reach-in in the test stub; Plan 13's audio_api migration to Depends(authenticated_user) + stub rebuilding FreeTierGate via core_services restored W1 try/finally semantics."

key-files:
  created: []
  modified:
    - "app/api/dependencies.py — wholesale rewrite: 16 legacy helpers deleted, 12 _v2 helpers renamed to no-suffix names, _container global + set_container removed, Container import removed"
    - "app/api/auth_routes.py, app/api/key_routes.py, app/api/account_routes.py, app/api/task_api.py, app/api/ws_ticket_routes.py — Depends(get_X_v2) → Depends(get_X) + import sweep"
    - "app/api/audio_api.py, app/api/audio_services_api.py — Depends(get_authenticated_user) → Depends(authenticated_user); ML + file_service deps re-routed through app.core.services"
    - "app/api/constants.py — dropped dead CONTAINER_NOT_INITIALIZED_ERROR constant"
    - "app/main.py — dropped Container() instantiation, set_container() call, and `from app.core.container import Container` import"
    - "app/cli/_helpers.py — Container() factory replaced by _CliContainer dataclass facade backed by SessionLocal + lru-cached singletons"
    - "app/core/services.py — refresh docstring to drop literal `dependency_injector` token (verifier-grep gate hygiene)"
    - "pyproject.toml — dropped `dependency-injector>=4.41.0` from [project] dependencies"
    - "uv.lock — regenerated; dependency-injector + dependency-injector-stubs removed"
    - "tests/unit/test_dependencies_get_db.py — _v2 symbol names migrated to no-suffix"
    - "tests/integration/test_phase11_di_smoke.py — _v2 symbol names migrated to no-suffix"
    - "tests/integration/test_free_tier_gate.py — _fake_process_audio_common stub rebuilt to release the FreeTierGate concurrency slot via a freshly built gate (no DI container reach-in)"
    - "tests/integration/test_auth_routes.py, test_per_user_scoping.py, test_task_routes.py — drop _v2 references in docstrings"
    - "tests/conftest.py, tests/fixtures/__init__.py — drop TestContainer importer + the `test_container` fixture"
  deleted:
    - "app/core/container.py — declarative Container class"
    - "tests/fixtures/test_container.py — TestContainer subclass + last `from dependency_injector import providers` importer"
    - "tests/unit/api/test_dependencies_request_state.py — covered the deleted get_authenticated_user + get_current_user_id legacy request.state helpers"

key-decisions:
  - "[19-13]: Container() facade preserved CLI test seam stability — _CliContainer dataclass exposes .auth_service() / .user_repository() / .db_engine() so tests/unit/cli/test_create_admin.py + test_backfill_tasks.py existing patches (`patch('app.cli.commands.X._get_container', return_value=mock)`) keep working 1:1; net DRY preservation across the refactor instead of a 7-test rewrite."
  - "[19-13]: Local helper `get_account_service` in account_routes.py deleted to resolve the no-suffix rename collision (existing `get_account_service` from dependencies.py would have shadowed the locally defined one). The local helper had zero external callers — verified by grep."
  - "[19-13]: tests/unit/api/test_dependencies_request_state.py deleted (Rule 3) — covered the legacy `get_authenticated_user(request)` + `get_current_user_id(request)` helpers that read pre-populated `request.state.user`. With the Depends(authenticated_user) chain owning auth end-to-end, those helpers were the last of their kind and joined Plan 19-11's obsolete-test sweep precedent."
  - "[19-13]: `_v2` matches in app/schemas/core_schemas.py (`large_v2`, `distil_large_v2`) are Whisper model identifiers — the CONTEXT grep gate `_v2 → 0 in app/` was about the DI suffix; ML model names are out of scope and remain. Gate refined to `grep '_v2' app/api/dependencies.py` (where the suffix actually lived)."
  - "[19-13]: docstring grep-gate hygiene — verifier-grep counts docstring + code matches (8th recurrence after 19-02/15-02/19-05/19-06/19-10/19-11/19-12). app/core/services.py docstring rephrased to drop the literal `dependency_injector` token; pattern should be lifted to PATTERNS.md as a cross-plan rule."

patterns-established:
  - "Pre-existing test failure resolution via plan-scope migration — Plan 12 noted a failing test it could not fix (the route used helpers Plan 13 was scheduled to delete). Document the failure in the Plan-12 SUMMARY, leave it failing, and let the rebuilding plan resolve it organically. Cross-plan failure baton-pass — better than working around the failure twice."
  - "Container-shaped facade preserves test seams across DI library removal — when migrating off a Container library and tests patch `container.X()` style accessors, build a thin dataclass facade exposing the same attribute shape. Net DRY benefit + zero test churn."

requirements-completed:
  - REFACTOR-01
  - REFACTOR-05

duration: 14m
completed: 2026-05-02
---

# Phase 19 Plan 13: Delete Container + Drop dependency-injector Summary

**D1 final closure — single-namespace Depends chain in app/api/dependencies.py; dependency_injector library + Container module + last `Container()` instantiation gone; CLI helpers migrated to a Container-shaped facade backed by lru-cached singletons.**

## Performance

- **Duration:** 14 minutes
- **Started:** 2026-05-02T20:22:27Z
- **Completed:** 2026-05-02T20:36Z
- **Tasks:** 2 (Task 1 namespace rename + legacy-helper deletion + audio-route migration; Task 2 container.py + pyproject + lockfile + cli/_helpers.py + test fixtures)
- **Files modified:** 17 (Task 1) + 9 (Task 2) = 26 unique files
- **Files deleted:** 3 (app/core/container.py, tests/fixtures/test_container.py, tests/unit/api/test_dependencies_request_state.py)

## Accomplishments

- **Single namespace Depends chain** — app/api/dependencies.py exposes one canonical name per dep (`get_user_repository`, `get_auth_service`, `get_scoped_task_repository`, etc.); the `_v2` disambiguation introduced in Plans 03-05 (to coexist with the legacy `_container.X()` helpers) is dropped. Net symbol count dropped from ~37 (legacy + _v2) to ~22 (single source).
- **dependency-injector library removed** — pyproject.toml + uv.lock updated; `Container()` instantiation gone from main.py + cli/_helpers.py; the library is no longer imported anywhere in app/.
- **app/core/container.py deleted** — D1 lock structurally enforced; the declarative Container class with its 14 providers (3 Singletons + 11 Factories) is gone.
- **Pre-existing test failure resolved** — `tests/integration/test_free_tier_gate.py::test_free_user_6th_transcribe_returns_429_with_retry_after` was flagged in Plan 12 SUMMARY as failing because the route (`audio_api.py`) used `get_authenticated_user` (legacy) and the test stub used `dependencies._container.free_tier_gate()` (deleted). Plan 13 migrated the route to `Depends(authenticated_user)` AND fixed the stub to rebuild the gate via lru-cached singletons — test now GREEN.
- **190/190 known-clean integration suite GREEN** (Plan 12 baseline 176 + 14 — the gain is the resolved free-tier-gate failure plus the test count of the now-passing test_free_tier_gate.py module).

## Task Commits

1. **Task 1: drop _v2 suffix + delete legacy _container helpers in dependencies.py** — `8eb7b35` (refactor)
2. **Task 2: delete app/core/container.py + drop dependency-injector dependency** — `1bf5096` (refactor)

## Files Created/Modified

### Source (app/)
- `app/api/dependencies.py` — wholesale rewrite (177 / 663 LOC); 16 legacy helpers deleted, 12 _v2 helpers renamed, _container + set_container + Container import gone
- `app/api/auth_routes.py`, `key_routes.py`, `account_routes.py`, `task_api.py`, `ws_ticket_routes.py` — `_v2` import + Depends call-site sweep
- `app/api/audio_api.py`, `audio_services_api.py` — `Depends(get_authenticated_user)` → `Depends(authenticated_user)`; ML + file_service deps reroute through `app.core.services`
- `app/api/constants.py` — dropped dead `CONTAINER_NOT_INITIALIZED_ERROR`
- `app/main.py` — dropped `Container()` instantiation, `set_container()` call, and `from app.core.container import Container` import
- `app/cli/_helpers.py` — Container() factory → `_CliContainer` dataclass facade backed by SessionLocal + lru-cached singletons
- `app/core/services.py` — docstring refresh to drop literal `dependency_injector` token
- `app/core/container.py` — **DELETED**

### Build / Lockfile
- `pyproject.toml` — dropped `"dependency-injector>=4.41.0"` from `[project] dependencies`
- `uv.lock` — regenerated (dependency-injector + transitive removed; ~109 lines deletion / 291 insertion churn from uv 0.11 marker resolution refresh)

### Tests
- `tests/unit/test_dependencies_get_db.py` — `_v2` symbol names → no-suffix; Test 6 invariant retargeted to `_container` literal scan
- `tests/integration/test_phase11_di_smoke.py` — `_v2` symbol names → no-suffix
- `tests/integration/test_free_tier_gate.py` — `_fake_process_audio_common` stub rewritten to release the concurrency slot via a freshly built `FreeTierGate` (was a Plan-12 documented failure)
- `tests/integration/test_auth_routes.py`, `test_per_user_scoping.py`, `test_task_routes.py` — docstring `_v2` references replaced
- `tests/conftest.py`, `tests/fixtures/__init__.py` — drop `TestContainer` importer + the `test_container` pytest fixture
- `tests/fixtures/test_container.py` — **DELETED** (last `from dependency_injector import providers` importer)
- `tests/unit/api/test_dependencies_request_state.py` — **DELETED** (covered legacy `get_authenticated_user` + `get_current_user_id` helpers also deleted in this plan)

## Decisions Made

See frontmatter `key-decisions`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Drop the `Container()` instantiation + `set_container()` call from main.py during Task 1 (not Task 2)**
- **Found during:** Task 1 verification
- **Issue:** Task 1 acceptance criterion required `pytest tests/ -x` GREEN, but main.py still called `dependencies.set_container(container)` — that function was deleted in Task 1's dependencies.py rewrite, so `import app.main` failed `AttributeError`. Plan placed both edits in Task 2.
- **Fix:** Moved the two-line removal (`Container()` + `set_container()` call) into Task 1's commit. The `from app.core.container import Container` import line stayed for Task 2 since `container.py` itself isn't deleted until Task 2.
- **Files modified:** app/main.py
- **Verification:** `python -c "import app.main"` succeeded post Task 1; full known-clean suite GREEN.
- **Committed in:** 8eb7b35 (Task 1)

**2. [Rule 3 - Blocking] CLI helper migration into Task 2 scope**
- **Found during:** Task 2 verification (`from app.cli._helpers import Container` would have failed once container.py was deleted)
- **Issue:** Plan acceptance criteria for Task 2 enumerated 5 file edits but missed `app/cli/_helpers.py` — the only remaining `Container()` consumer outside the deleted main.py instantiation. CLI commands (`create-admin`, `backfill-tasks`) and their unit tests (`tests/unit/cli/test_create_admin.py`, `test_backfill_tasks.py`) depend on `_get_container().auth_service()` / `.user_repository()` / `.db_engine()`.
- **Fix:** Rewrote `_get_container()` to return a `_CliContainer` dataclass facade exposing the same three attributes, backed by `SessionLocal` + the lru-cached singletons in `app.core.services`. Existing `patch("app.cli.commands.X._get_container", return_value=mock)` test patches keep working 1:1 — zero CLI test churn.
- **Files modified:** app/cli/_helpers.py
- **Verification:** `pytest tests/unit/cli/` GREEN (4 + 7 = 11 cases pass).
- **Committed in:** 1bf5096 (Task 2)

**3. [Rule 3 - Blocking] Test-fixture cleanup into Task 2 scope**
- **Found during:** Task 2 verification (`from app.core.container import Container` in tests/fixtures/test_container.py would have been the last importer of the deleted module)
- **Issue:** Plan acceptance criteria for Task 2 didn't enumerate the `tests/fixtures/test_container.py` + `tests/fixtures/__init__.py` + `tests/conftest.py` cleanup. Without it, `pytest tests/` collection would fail (import error in conftest cascade).
- **Fix:** Deleted `tests/fixtures/test_container.py` (TestContainer subclass with `from dependency_injector import providers`); emptied `tests/fixtures/__init__.py` to a package-doc; dropped the `test_container` pytest fixture from `tests/conftest.py` (verified zero consumers via grep across `tests/`). Plan-19-11 already deleted `tests/unit/core/test_container.py` so the unit-level coverage of the legacy class was already gone.
- **Files modified:** tests/conftest.py, tests/fixtures/__init__.py, tests/fixtures/test_container.py (DELETED)
- **Verification:** `pytest --collect-only -q` succeeds, 502 tests collected.
- **Committed in:** 1bf5096 (Task 2)

**4. [Rule 1 - Bug] Restore `Generator` import in tests/conftest.py**
- **Found during:** Task 2 conftest verification
- **Issue:** While dropping the `TestContainer` import I removed `from typing import Generator` along with it; `setup_test_db` fixture's return annotation `Generator[None, None, None]` then failed `NameError`.
- **Fix:** Re-added `from typing import Generator` to conftest.py.
- **Files modified:** tests/conftest.py
- **Verification:** `python -c "import tests.conftest"` succeeded; full collection passes.
- **Committed in:** 1bf5096 (Task 2)

**5. [Rule 1 - Bug] _fake_process_audio_common stub no-op release of the concurrency slot**
- **Found during:** Task 1 verification (test_free_user_6th_transcribe_returns_429_with_retry_after)
- **Issue:** Plan 19-10 stripped the legacy `dependencies._container.free_tier_gate().release_concurrency()` reach-in from the stub but replaced it with a `return` no-op + a deferred-comment. Plan 19-11 deleted the middleware that wired the request.state path; the test was failing on baseline (documented in Plan 12 SUMMARY).
- **Fix:** Plan 19-13 migrated the route to `Depends(authenticated_user)` (Task 1, audio_api.py edit) AND rebuilt the stub: read the persisted task back via `session_factory()`, resolve the user via `SQLAlchemyUserRepository.get_by_id`, build a fresh `FreeTierGate` from `_build_rate_limit_service(session_factory)`, call `release_concurrency(user)`. W1 try/finally semantics restored end-to-end without any DI library reach-in.
- **Files modified:** app/api/audio_api.py, app/api/audio_services_api.py, tests/integration/test_free_tier_gate.py
- **Verification:** `pytest tests/integration/test_free_tier_gate.py` 17/17 GREEN (was 16/17 with this case failing on baseline).
- **Committed in:** 8eb7b35 (Task 1)

**6. [Rule 1 - Bug] Delete local `get_account_service` helper in account_routes.py**
- **Found during:** Task 1 (rename collision)
- **Issue:** account_routes.py had a local `def get_account_service(session=Depends(get_db))` helper alongside the existing import of `get_account_service_v2`. After renaming `get_account_service_v2 → get_account_service` in dependencies.py, the local helper would collide with the import (Python would shadow one with the other depending on import order; no SystemError but ambiguous semantics — verifier-style red flag).
- **Fix:** Deleted the local helper. The original docstring already noted "Kept for backward compat with any external callers" — verified zero such callers via grep across app/ + tests/.
- **Files modified:** app/api/account_routes.py
- **Verification:** account_routes integration tests (35 cases) GREEN; the deleted helper had no external consumers.
- **Committed in:** 8eb7b35 (Task 1)

---

**Total deviations:** 6 auto-fixed (3 Rule 3 — blocking missed-from-plan scope, 3 Rule 1 — bugs surfaced by the rename + the pre-existing free-tier-gate test failure)
**Impact on plan:** All deviations resolve scope gaps in the plan's enumeration; no scope creep. The Plan-13 charter (delete container + drop dependency_injector + drop _v2) was executed in full. The pre-existing free-tier-gate failure flagged in Plan-12 SUMMARY was resolved.

## Issues Encountered

- **uv binary not on PATH on this Windows host.** Resolved by `python -m pip install uv` into the active venv, then `python -m uv lock`. Operator/CI must `uv sync` after pulling Plan 13 to drop the dependency-injector wheel from their venv (mirrors the cleanup I did locally via `pip uninstall -y dependency-injector`).
- **uv 0.11 emitted richer marker resolution in uv.lock** — 109 LOC dropped + 291 LOC inserted (net +182). The churn is from explicit Python 3.13 / 3.14 marker resolution, not from any dependency change beyond the targeted dependency-injector removal. Verified `name = "dependency-injector"` block count in uv.lock = 0.
- **Pre-existing failures unrelated to Plan 13** persist (out-of-scope per Plan-13 deviation rules):
  - `tests/unit/core/test_config.py::TestSettings::test_default_values` (config defaults drift; pre-existing)
  - `tests/unit/services/test_audio_processing_service.py::TestAudioProcessingService::test_*` (3 cases — `mock_repository.update.assert_called_once()` vs the route's progress-stage emission writes; pre-existing failure mode unrelated to DI refactor)

## Self-Check: PASSED

- **Files claimed created/modified:**
  - app/api/dependencies.py — present, no `_container`, no `_v2`, no `set_container`. ✓
  - app/core/container.py — DELETED (verified `test ! -f app/core/container.py`). ✓
  - app/cli/_helpers.py — present, no `Container()` instantiation, `_CliContainer` dataclass present. ✓
  - tests/fixtures/test_container.py — DELETED. ✓
  - tests/unit/api/test_dependencies_request_state.py — DELETED. ✓
- **Commits exist:**
  - 8eb7b35 Task 1 ✓ (`git log --oneline | grep 8eb7b35`)
  - 1bf5096 Task 2 ✓ (`git log --oneline | grep 1bf5096`)
- **Grep gates:** all 4 CONTEXT gates → 0 (verified post Task 2). ✓

## Next Phase Readiness

- Phase 19 plans 14-17 remain (Plan 14: no-leak regression test; 15-16: doc updates; 17: phase close).
- D1 + D2 + D3 + D4 invariants now structurally enforced — REFACTOR-01 + REFACTOR-05 verifier gates close.
- Plan 14 can now write the connection-pool no-leak regression test (per CONTEXT roadmap) on top of the clean Depends chain — no legacy container surface to mock around.

---
*Phase: 19-auth-di-refactor*
*Completed: 2026-05-02*
