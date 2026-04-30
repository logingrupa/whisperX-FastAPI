---
phase: 16-verification-cross-user-matrix-e2e
plan: 06
subsystem: testing
tags: [verification, alembic, migration, brownfield, fk-enforcement, sqlite, integration-test]

requires:
  - phase: 10-database-foundation
    provides: alembic baseline + 0002_auth_schema + 0003 NOT NULL pre-flight
  - phase: 16-01-helpers
    provides: _phase16_helpers._run_alembic + REPO_ROOT (DRY single source)

provides:
  - VERIFY-08 alembic brownfield migration smoke (4 cases)
  - synthetic v1.1 baseline schema mirror (no user_id col)
  - admin-seed + UPDATE pattern between 0002 and head upgrades (mirrors backfill-tasks CLI runbook)
  - FK enforcement test via deliberate orphan INSERT raising IntegrityError

affects:
  - 17-ops-runbooks (OPS-03 migration runbook references this test as executable proof)
  - 16-VERIFICATION (final phase verifier — VERIFY-08 closed)

tech-stack:
  added: []
  patterns:
    - "Subprocess alembic invocation via [sys.executable, -m, alembic] (Plan 10-04 venv-portable lesson)"
    - "Per-test fresh engine on tmp_path SQLite — avoids global engine listener contamination"
    - "Manual PRAGMA foreign_keys=ON inside fresh engine for FK enforcement assertions"

key-files:
  created:
    - tests/integration/test_migration_smoke.py
  modified: []

key-decisions:
  - "Used password_hash (real schema column name) not hashed_password (plan typo) — plan vs schema drift"
  - "plan_tier='pro' (valid CHECK constraint enum value: free/trial/pro/team)"
  - "Each test owns its tmp_path DB — pytest test isolation > DRY fixture (4-step sequence is locally readable)"
  - "Manual PRAGMA foreign_keys=ON in FK-enforce test (production listener absent on fresh engine)"

patterns-established:
  - "Brownfield migration smoke 4-step: build legacy → stamp 0001 → upgrade 0002 → seed admin → upgrade head"
  - "Multi-axis assertion: row count + column metadata + IntegrityError type (tiger-style fail-loud)"

requirements-completed: [VERIFY-08]

duration: 5min
completed: 2026-04-30
---

# Phase 16 Plan 06: VERIFY-08 Migration Smoke Summary

**Synthetic v1.1 baseline → alembic stamp 0001 → upgrade 0002 → seed admin → upgrade head: 4 brownfield migration smoke tests asserting row preservation, tasks.user_id NOT NULL constraint application, and FK enforcement via deliberate orphan INSERT.**

## Performance

- **Duration:** ~5 min (start 2026-04-30T12:44:07Z, end ~12:49Z)
- **Tasks:** 2 (helpers + 4 test cases — written together as same-file plan)
- **Files modified:** 1 (created)
- **Test runtime:** 43s (4 alembic subprocess upgrades × ~10s each)

## Accomplishments

- VERIFY-08 closed: brownfield v1.1 → head migration proven row-preserving + 0003 NOT NULL constraint applied + FK enforcement live
- 4 tests green covering distinct invariants (row count, user_id assignment, NOT NULL column metadata, FK IntegrityError)
- Operator-facing migration runbook (Phase 17 OPS-03) gains executable proof-of-runbook artifact
- Single-file DRY: reuses `_phase16_helpers._run_alembic` (Plan 10-04 venv-portable subprocess pattern) — no copy-paste

## Task Commits

1. **Task 1+2 combined: helpers + 4 smoke cases** — `0b58078` (test)
   - Plan split helpers (Task 1) and tests (Task 2) into separate tasks but they live in same file; committed atomically per plan instruction "Commit atomically"

**Plan metadata:** TBD (final commit after STATE/ROADMAP update)

## Files Created/Modified

- `tests/integration/test_migration_smoke.py` (206 lines) — 3 helpers (`_make_engine`, `_build_v11_baseline`, `_seed_admin_user_and_assign_tasks`) + 4 `@pytest.mark.integration` tests

## Decisions Made

1. **Schema column name `password_hash` not `hashed_password`** — plan PROMPT used `hashed_password`, but `alembic/versions/0002_auth_schema.py` line 42 + `app/infrastructure/database/models.py:177` both name it `password_hash`. Tracked as Rule 1 deviation (plan/code drift bug); fixed before write.
2. **`plan_tier='pro'`** — chosen from valid CHECK enum (`free|trial|pro|team`); arbitrary but realistic for an admin user.
3. **Fresh engine + manual `PRAGMA foreign_keys = ON` inside FK-enforcement test** — Phase 10-04 SQLAlchemy global engine listener sets PRAGMA on the production engine; this test owns a fresh `create_engine(...)` without that listener, so FK pragma must be enabled inline. Comment in test explicitly notes this.
4. **Did NOT extract `_prepare_migrated_db` helper** — plan offered optional refactor if file >200 lines. Final file is 206 lines but each test reads top-to-bottom in 6 lines (4-step setup + assert). Tiger-style: locally readable beats DRY here. Plan author authorized executor judgment.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan column name `hashed_password` corrected to `password_hash`**
- **Found during:** Task 1 (write `_seed_admin_user_and_assign_tasks` helper)
- **Issue:** Plan action block specified INSERT into `users (email, hashed_password, ...)` — actual schema (per `0002_auth_schema.py` line 42 + `models.py` User.password_hash) uses `password_hash`. INSERT with wrong column name would fail.
- **Fix:** Used `password_hash` in INSERT statement.
- **Files modified:** tests/integration/test_migration_smoke.py
- **Verification:** All 4 tests pass — INSERT succeeds, admin user seeded, tasks UPDATE attaches user_id.
- **Committed in:** 0b58078

**2. [Rule 1 - Bug] Plan acceptance grep pattern `::test_` does not match pytest 9 collect output**
- **Found during:** Post-Task-2 acceptance verification
- **Issue:** Plan acceptance criterion `pytest --co | grep -c "::test_" == 4` returned 0 — pytest 9 uses `<Function test_...>` format, not `::test_...`.
- **Fix:** Verified semantically with `grep -c "<Function test_"` → 4 (matches plan intent of "4 tests collected"). Did NOT modify the test file.
- **Files modified:** None (verifier-pattern drift, not test bug).
- **Verification:** `pytest tests/integration/test_migration_smoke.py -x -q` exits 0 with `4 passed` — semantic acceptance met.
- **Committed in:** N/A (verifier note only).

---

**Total deviations:** 2 auto-fixed (1 plan/code schema drift, 1 verifier pattern obsolete)
**Impact on plan:** Zero scope change. Schema fix was correctness-critical (plan would have produced a non-functional INSERT). Pattern note documents pytest 9 collection format for future plans.

## Issues Encountered

- `uv` not on `PATH` in this shell session — used `.venv/Scripts/python.exe -m pytest` directly. Equivalent invocation, no behavioural difference; documented for future executors.

## Verification Results

**Plan-level `<verification>` block:**
- `uv run pytest tests/integration/test_migration_smoke.py -v` → equivalent run yields **4 passed in 43s** ✓
- VERIFY-08 closed ✓
- Phase 17 OPS-03 docs can reference this test ✓

**Plan-level `<success_criteria>`:**
- 4 cases pass ✓
- Synthetic v1.1 baseline schema mirrors pre-Phase-10 tasks table exactly ✓ (matches 0001_baseline.upgrade column shape)
- 4-step migration sequence executes ✓
- 0003 NOT NULL pre-flight passes ✓ (admin user assigned before upgrade head)
- FK enforcement verified via deliberate orphan INSERT ✓ (`IntegrityError` raised)
- `_run_alembic` subprocess pattern matches Plan 10-04 lesson ✓ (DRY import from `_phase16_helpers`)
- Tiger-style: row count, column metadata, IntegrityError all asserted ✓
- No nested-if ✓ (verifier grep == 0)

**Acceptance criteria results:**
| Criterion | Expected | Got | Pass |
|---|---|---|---|
| Task 1: 3 helpers defined | == 3 | 3 | ✓ |
| Task 1: 1 _phase16_helpers import | == 1 | 1 | ✓ |
| Task 1: _run_alembic occurrences | >= 1 | 17 | ✓ |
| Task 2: tests collected | == 4 | 4 (via Function pattern) | ✓ |
| Task 2: pytest exit 0 | 0 | 0 | ✓ |
| Task 2: _run_alembic occurrences | >= 8 | 17 | ✓ |
| Task 2: PRAGMA foreign_keys | >= 1 | 3 | ✓ |
| Task 2: IntegrityError | >= 1 | 3 | ✓ |
| Task 2: nested-if (8-space if) | == 0 | 0 | ✓ |

## Next Phase Readiness

- Phase 16 Wave 1 progress: 5 of 5 plans (16-02..16-06) complete pending verification gate.
- VERIFY-01..04, 06, 07, 08 all have green tests on disk.
- Phase 17 (Ops Runbooks) can reference `tests/integration/test_migration_smoke.py` as the executable proof of OPS-03.
- No blockers.

## Self-Check: PASSED

- [x] tests/integration/test_migration_smoke.py exists on disk (206 lines)
- [x] Commit 0b58078 in `git log --oneline --all` (visible)
- [x] All 4 tests pass (43s runtime)
- [x] All plan-level success_criteria met
- [x] All task acceptance_criteria met (semantic match for pytest 9 collect format)

---
*Phase: 16-verification-cross-user-matrix-e2e*
*Completed: 2026-04-30*
