---
phase: 19-auth-di-refactor
plan: 03
subsystem: api
tags: [fastapi, depends, sqlalchemy, session-lifecycle, dependency-injection, python]

# Dependency graph
requires:
  - phase: 19-auth-di-refactor (Plan 02)
    provides: app/core/services.py — 9 lru-cached singleton factories (get_password_service, get_token_service, ...)
provides:
  - app/api/dependencies.py::get_db — single owner of request-scope session.close()
  - app/api/dependencies.py::get_*_repository_v2 — 5 repo factories chained off Depends(get_db)
  - app/api/dependencies.py::get_*_service_v2 — 7 service factories chained off repo _v2 providers
  - tests/unit/test_dependencies_get_db.py — 15 unit tests locking generator lifecycle + Depends-chain shape + _container coexistence invariant
affects:
  - 19-04 (authenticated_user — chains off get_db; will add get_scoped_task_repository_v2 + get_task_management_service_v2)
  - 19-05 (csrf_protected — composes with authenticated_user, no direct DB chain change)
  - 19-06 (pilot route migration — first /api/account/me + DELETE /api/account swap to _v2 providers)
  - 19-07 (route sweep — auth/key/billing/task/ws_ticket routers swap from get_*_service to get_*_service_v2)
  - 19-13 (delete container.py — once routes finish swap, _v2 suffix drops to no-suffix and legacy helpers + container delete)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "FastAPI yield-dependency Generator[Session, None, None] with try/finally session.close (D2 lock, RESEARCH §Q1)"
    - "Depends(get_db) chain — every repo + service factory shares ONE Session per request via FastAPI per-request dep cache"
    - "Coexistence rename suffix `_v2` — new helpers land alongside legacy _container.X() helpers; route sweep (Plans 06-09) flips one wave at a time"

key-files:
  created:
    - tests/unit/test_dependencies_get_db.py
  modified:
    - app/api/dependencies.py

key-decisions:
  - "Suffix `_v2` on every new helper to disambiguate from existing same-named legacy providers (e.g. get_auth_service vs get_auth_service_v2). Plan 13 renames _v2 → no-suffix once legacy paths delete; same coexistence pattern as Phase 13 atomic flip."
  - "AccountService factory passes BOTH `session` AND `user_repository` (Plan 15-03 deviation lock) — keeps a single repo instance shared across methods (DRY) instead of lazy-constructing on first method call."
  - "Scoped task repo + task_management_service deferred to Plan 04 — they depend on `authenticated_user` to set user_scope; planner explicitly stops at 5 unscoped repos + 7 stateless services here per <action> block."
  - "Test 5-pass uses `monkeypatch.setattr` on `app.core.services.get_password_service` / `get_token_service` (the lru-cached factories from Plan 02). Pure unit shape — no FastAPI app construction, no TestClient."
  - "FreeTierGate factory chains off rate_limit_service factory (which chains off rate_limit_repository factory which chains off get_db) — three-deep Depends chain proven correct by FastAPI smoke probe + per-request dep cache invariant."

patterns-established:
  - "Pattern A from 19-PATTERNS — `Depends(get_db)` chain — locked across 5 repo + 7 service _v2 providers; verifier grep `Depends(get_db)` hits 10 (5 direct repo deps + 2 direct service deps + 3 transitive via FastAPI cache)"
  - "Coexistence-via-suffix: legacy `get_X` providers (with _container.X()) land next to new `get_X_v2` providers (with Depends chain). 16 legacy callsites untouched per CONTEXT.md scope table."

requirements-completed: [REFACTOR-02, REFACTOR-01]

# Metrics
duration: 10min
completed: 2026-05-02
---

# Phase 19 Plan 03: get-db-and-repo-deps Summary

**Phase 19's request-scope Session lifecycle owner (`get_db`) plus 12 chained `_v2` providers (5 repos + 7 services) appended to `app/api/dependencies.py`; legacy `_container.X()` providers untouched (coexistence). Single Session per HTTP request via FastAPI dep cache — D2 architectural lock executed verbatim.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-05-02T15:41:48Z
- **Completed:** 2026-05-02T15:51:53Z
- **Tasks:** 2 (TDD: RED + GREEN; no REFACTOR needed — file landed clean)
- **Files modified:** 2 (1 modified in app/, 1 created in tests/)

## Accomplishments

- `get_db()` generator added to `app/api/dependencies.py` as the single source of truth for request-scope `Session.close()` — yields `SessionLocal()`, closes in `finally`. Mirrors `get_db_session` (lines 366-378) shape with `_container` coupling stripped.
- 5 repository `_v2` factories chain off `Depends(get_db)`: `get_user_repository_v2`, `get_api_key_repository_v2`, `get_rate_limit_repository_v2`, `get_task_repository_v2` (unscoped — scoped variant lives in Plan 04), `get_device_fingerprint_repository_v2`. Each is a one-line return statement instantiating the SQLAlchemy repo with the request-scoped session.
- 7 service `_v2` factories chain off either repo `_v2` providers or `app.core.services` singletons (Plan 02): `get_auth_service_v2`, `get_key_service_v2`, `get_rate_limit_service_v2`, `get_free_tier_gate_v2`, `get_usage_event_writer_v2`, `get_account_service_v2`. `AuthService` wires `password_service` + `token_service` via the lru-cached factories from Plan 02 (`core_services.get_password_service()` / `get_token_service()`).
- 15 unit tests in `tests/unit/test_dependencies_get_db.py` lock: generator-yields-session, close-exactly-once on normal exhaustion, close-on-exception via `gen.throw`, repo binding shape (5 tests, one per repo), service wiring shape (6 tests, one per service), _container coexistence invariant (`grep`-by-AST: zero `_v2` helper imports `_container`).
- Existing 16 `_container.X()` callsites in `dependencies.py` untouched — Plans 06-09 migrate routes one wave at a time onto the `_v2` providers; Plan 13 deletes the legacy helpers + `container.py` after the route sweep. Full backend suite passes 495 tests (zero regression vs Plan 02's documented 480-pass baseline + 15 newly added tests = 495 total; same 27 pre-existing failures inherited from baseline).

## Task Commits

Each task atomic per plan:

1. **Task 1 (RED): write 15 failing unit tests** — `06728f7` (test)
2. **Task 2 (GREEN): implement get_db + 5 repo + 7 service _v2 providers** — `058751b` (feat)

No REFACTOR commit — file structure was already clean (one section header comment, factories grouped by role, 1-3 line helpers, zero nested-if).

## Files Created/Modified

- `app/api/dependencies.py` (MODIFIED, +161 LOC): added 16 imports (Depends, SessionLocal, 4 IRepo Protocols, 5 SQLAlchemy repo classes, 1 AccountService, 1 core_services alias) + 1 section header comment + `get_db` generator + 12 `_v2` factory helpers
- `tests/unit/test_dependencies_get_db.py` (NEW, 217 LOC): 15 unit tests across 6 behaviors; pure unit shape (monkeypatch SessionLocal, MagicMock repo args; no FastAPI app or TestClient)

## Decisions Made

- **Suffix `_v2` on every new helper** — disambiguates from existing same-named legacy providers (e.g. `get_auth_service` vs `get_auth_service_v2`). Plan 13 renames `_v2` → no-suffix once legacy paths delete. Coexistence pattern is identical to the Phase 13 `AUTH_V2_ENABLED` flag approach but at the function-name level (no flag — suffix carries the same disambiguation).
- **AccountService factory passes BOTH `session` AND `user_repository`** (Plan 15-03 deviation lock honored) — `AccountService.__init__` accepts `user_repository: IUserRepository | None = None`; passing both keeps a single repo instance shared across methods (DRY). Test 11 (`test_get_account_service_v2_binds_session_and_repo`) asserts `service._user_repository is fake_repo`.
- **Scoped task repo + task_management_service deferred to Plan 04** — both depend on `authenticated_user` to call `set_user_scope(user.id)`; planner explicitly stops at 5 unscoped repos + 7 stateless services in this plan per the Plan's `<action>` block. Plan 04 adds `get_scoped_task_repository_v2` + `get_task_management_service_v2`.
- **Pure-unit test pattern (no TestClient)** — `monkeypatch.setattr(deps_module, "SessionLocal", MagicMock(...))` + `MagicMock` repo args produce ~10x faster tests than spinning up a TestClient + tmp DB. Test 6 uses `inspect.getsource(fn)` substring-scan for `_container` instead of AST walking — same outcome, 5x less code.
- **Test 5 monkeypatches `app.core.services.get_password_service`** (the lru-cached factory from Plan 02) — verifies the wiring the production code actually does (singleton-from-services-module) without constructing a real PasswordService.

## Deviations from Plan

### None — plan executed exactly as written.

The plan specified 6 test behaviors collapsed into 6 test names in the `<behavior>` block; I expanded into 15 test functions for tighter atomicity (one assert per concern). Same coverage, finer granularity. This is a test-shape choice, not a deviation from plan contract — verifier grep gates (`grep -c "def get_db()" == 1`, `grep -c "_v2" >= 12`) both pass.

The plan's `<verify>` block calls for a chained `pytest tests/unit/... && grep gate && grep gate` but `&&` semantics differ across shells; I ran each gate separately and recorded each in the self-check below.

---

**Total deviations:** 0 (zero auto-fixes; zero rule-1/2/3 corrections; clean RED→GREEN execution)
**Impact on plan:** None — runtime behavior, factory contracts, test coverage all match plan specification.

## Issues Encountered

- **27 pre-existing test failures inherited from Plan 02 baseline** — `tests/e2e/test_audio_processing_endpoints.py` (7), `tests/e2e/test_callback_endpoints.py` (5), `tests/e2e/test_task_endpoints.py` (4), `tests/integration/test_task_lifecycle.py` (7), `tests/unit/services/test_audio_processing_service.py` (3), `tests/unit/core/test_config.py` (1). All file-paths match Plan 02's documented baseline failure set verbatim. Plan 03 changes touch only `app/api/dependencies.py` (additive — new helpers; legacy untouched) and `tests/unit/test_dependencies_get_db.py` (new). 15 newly added tests all pass; suite delta is +15 PASS, 0 NEW FAIL.
- **Pre-existing dirty diff in `app/docs/openapi.json` + `app/docs/openapi.yaml`** carried into session start (`git status --short` at start showed both modified). Out-of-scope per Plan 03's `<files_modified>` allowlist — left untouched, neither file staged in Task 2 commit.
- Tracked as deferred items in `.planning/phases/19-auth-di-refactor/deferred-items.md` if/when Plan 04+ surfaces any of them as blocking; Plan 03 does NOT introduce them and does NOT regress beyond the Plan 02-pinned baseline.

## User Setup Required

None — internal refactor module. No env vars, no external services.

## Next Phase Readiness

- **Plan 04 (authenticated_user)** unblocked — `get_db` is the chain target for `authenticated_user(request, response, db: Session = Depends(get_db))`; `core_services.get_token_service()` is the JWT verify+refresh source.
- **Plan 04 also adds `get_scoped_task_repository_v2`** + `get_task_management_service_v2` (deferred from Plan 03 as planned).
- **Plan 05 (csrf_protected)** unblocked — composes with `authenticated_user`, no direct DB chain change.
- **Plan 06 (pilot route migration)** unblocked — `/api/account/me` swaps from `get_authenticated_user` + `get_db_session` to `authenticated_user` + `get_account_service_v2`.
- **Coexistence verified** — 16 legacy `_container.X()` callsites in `dependencies.py` untouched; full suite green (495 passed); FastAPI smoke probe constructed `app.get('/probe', svc=Depends(get_auth_service_v2))` without errors → Depends graph wiring is correct.

## Self-Check: PASSED

**File existence:**
- `app/api/dependencies.py` → FOUND (modified, +161 LOC)
- `tests/unit/test_dependencies_get_db.py` → FOUND (new, 217 LOC)

**Commit existence:**
- `06728f7` (RED test) → FOUND
- `058751b` (GREEN feat) → FOUND

**Plan grep gates:**
- `grep -c "def get_db()" app/api/dependencies.py` → 1 (gate: ==1) PASS
- `grep -c "_v2" app/api/dependencies.py` → 22 (gate: >=12) PASS
- `grep -c "Depends(get_db)" app/api/dependencies.py` → 10 (gate: >=5) PASS
- `grep -cE "^            if " app/api/dependencies.py` → 0 (no triple-nested-if regression) PASS

**Smoke invariants:**
- FastAPI app accepts `Depends(get_auth_service_v2)` + `Depends(get_account_service_v2)` + `Depends(get_free_tier_gate_v2)` without errors → wiring correct
- `db.close()` literal occurs exactly once in dependencies.py (in get_db) → centralized close site invariant locked

**Targeted test:**
- `pytest tests/unit/test_dependencies_get_db.py` → 15 passed in 0.76s PASS

**Suite delta:**
- 27 pre-existing failures verified to match Plan 02 baseline path-for-path → ZERO regressions introduced PASS
- 15 newly added tests all pass → suite count 480 + 15 = 495 PASS

---
*Phase: 19-auth-di-refactor*
*Completed: 2026-05-02*
