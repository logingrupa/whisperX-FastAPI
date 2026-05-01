---
phase: 17-docs-migration-runbook-operator-guide
plan: 01
subsystem: docs
tags: [docs, migration, runbook, alembic, ops, sqlite]

requires:
  - phase: 10-schema-foundation
    provides: 0001_baseline + 0002_auth_schema migrations
  - phase: 12-admin-cli-task-backfill
    provides: create-admin + backfill-tasks CLI commands; 0003_tasks_user_id_not_null pre-flight guard
  - phase: 16-verification-cross-user-matrix-e2e
    provides: tests/integration/test_migration_smoke.py — executable proof-of-runbook (VERIFY-08)
provides:
  - Operator-followable v1.1 -> v1.2 migration runbook (OPS-03)
  - 9-section locked sequence operator can copy-paste end-to-end without consulting source code
  - Single source of truth for alembic step-ordering invariants (admin-before-backfill, backfill-before-upgrade-head)
affects: [17-02, 17-03]

tech-stack:
  added: []
  patterns:
    - "Section skeleton: Purpose -> Pre-flight check -> Command (fenced bash) -> Expected output -> Verify -> Failure mode (tiger-style boundary asserts)"
    - "Step ordering 1:1 mirror to executable smoke test (test_migration_smoke.py) — runbook drift detectable by re-running smoke test"
    - "DRY: alembic revision IDs listed in single chain table (Section 1); subsequent sections refer by name only"
    - "Rollback split into option A (alembic downgrade chain, reversible) vs option B (full restore from backup, unrecoverable mid-migration) — flat decision, no nested-if"

key-files:
  created:
    - docs/migration-v1.2.md
  modified: []

key-decisions:
  - "Section skeleton enforced: Purpose / Pre-flight / Command / Expected output / Verify / Failure mode — every numbered section follows the same shape so operator reads top-to-bottom without backtracking"
  - "Step ordering 1:1 mirrors tests/integration/test_migration_smoke.py 4-step sequence (stamp 0001 -> upgrade 0002 -> create-admin -> backfill -> upgrade head) — runbook drift detectable by re-running VERIFY-08"
  - "DRY: revision IDs listed once in Section 1 chain table; CLI commands appear verbatim in this file only — README and .env.example will link, not duplicate (enforced by 17-02 / 17-03 acceptance gates)"
  - "Windows / non-TTY note documented in Section 5 only (not duplicated to a separate top-level section) — getpass piping limitation is operator-actionable inline"
  - "Rollback option A vs option B is a flat 2-path decision; option B (restore from backup) explicitly preferred when v1.2 user data has already been written (downgrade 0002 -> 0001 drops auth tables, losing data)"

patterns-established:
  - "Tiger-style boundary asserts in docs: every shell command shows EXACT expected output line so operator compares without consulting source"
  - "Step ordering invariant table at top of overview section — fail-loud at each boundary documented declaratively before commands appear"
  - "Cross-link to executable test file (test_migration_smoke.py) as 'executable proof' so doc drift surfaces in CI"

requirements-completed: [OPS-03]

duration: 3min
completed: 2026-05-01
---

# Phase 17 Plan 01: Docs — v1.2 Migration Runbook Summary

**Operator-followable 9-section migration runbook (`docs/migration-v1.2.md`) mirroring `test_migration_smoke.py` 1:1, delivering OPS-03.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-05-01T16:27:02Z
- **Completed:** 2026-05-01T16:29:36Z
- **Tasks:** 1
- **Files modified:** 1 (created)

## Accomplishments

- `docs/migration-v1.2.md` created (409 lines) with nine top-level numbered sections in the locked order: Overview, Pre-flight: Backup Database, Stamp Baseline, Upgrade Auth Schema, Create Admin User, Backfill Tasks, Upgrade Head, Smoke Verify, Rollback.
- Step ordering verified 1:1 against `tests/integration/test_migration_smoke.py` 4-step sequence (stamp 0001 → upgrade 0002 → create-admin + backfill → upgrade head).
- Every executable step is a fenced bash block with exact expected-output snippet (tiger-style boundary).
- Rollback section documents `alembic downgrade -1` chain (option A) AND backup restore (option B) as flat decision.
- DRY enforced inside the file: revision IDs listed once (Section 1 chain table); CLI commands appear in their owning section only.

## Task Commits

1. **Task 1: Write docs/migration-v1.2.md** — `b9e9559` (docs)

**Plan metadata commit:** pending (final-commit step below).

## Files Created/Modified

- `docs/migration-v1.2.md` — 9-section v1.1 → v1.2 migration runbook; copy-pasteable bash blocks; expected output per command; rollback procedure; cross-links to `.env.example` (env vars) and `tests/integration/test_migration_smoke.py` (executable proof).

## Decisions Made

- **Locked section skeleton (Purpose / Command / Expected output / Verify / Failure mode):** every numbered section follows the same shape so operator reads top-to-bottom without backtracking — eliminates nested-if prose.
- **1:1 smoke-test mirror:** runbook step ordering is locked to `test_migration_smoke.py`'s `_run_alembic` invocation sequence — runbook drift is detectable by re-running VERIFY-08, not by code review.
- **DRY scope inside the file:** revision IDs listed once (Section 1 chain table); CLI commands appear verbatim only in the owning section. Sections 7 and 9 reference `backfill-tasks` by name in recovery prose but only Section 6 owns the canonical invocation.
- **Rollback path split:** option A (alembic downgrade chain) vs option B (full backup restore) — option B explicitly recommended when v1.2 user data exists (downgrade 0002 → 0001 drops auth tables, losing rows).
- **Windows getpass note kept inline in Section 5:** not promoted to a top-level section; operator-actionable note where they encounter the constraint.

## Deviations from Plan

None — plan executed exactly as written. The plan-prescribed nine-section heading list and section bodies were rendered verbatim with the following plan-permitted refinements at Claude's discretion (CONTEXT §35 — "Exact prose, table formatting, and intra-section ordering at Claude's discretion as long as the locked structure above holds"):

- Added a step-ordering-invariants table to Section 1 documenting fail-loud boundaries declaratively (admin-before-backfill, backfill-before-upgrade-head).
- Added Section 8 Check 5 (`PRAGMA foreign_keys` runtime check) noting the production engine listener vs ad-hoc `sqlite3` CLI difference — preserves Phase 10-04 invariant visibility for the operator.
- Section 9 explicitly flags `alembic downgrade base` as production-unsafe (drops `tasks` table itself) and routes the operator to option B for production data.

## Issues Encountered

None — single-task docs plan, no auth/runtime/build dependencies.

## User Setup Required

None — pure documentation, no external service configuration.

## Threat Flags

None — runbook documents existing migration surface (Phase 10-12 already shipped). No new network endpoints, auth paths, or trust-boundary changes introduced.

## Next Phase Readiness

- Plan 17-02 (`.env.example` v1.2 expansion) can now reference this runbook by section anchor for any env var that ties to a migration step.
- Plan 17-03 (README v1.2 auth section) will cross-link the "Migrating from v1.1" section directly to `docs/migration-v1.2.md`.
- Cross-file DRY guard: Plans 17-02 and 17-03 acceptance criteria must `grep -c` the verbatim CLI command bodies in `.env.example` / `README.md` and assert == 0 (commands live here only).

## Self-Check

- [x] `docs/migration-v1.2.md` exists (409 lines, ≥200 floor met).
- [x] All 9 locked headings present and `grep`-verified (`## 1. Overview` through `## 9. Rollback`).
- [x] All required CLI/alembic invocations present: `alembic stamp 0001_baseline`, `alembic upgrade 0002_auth_schema`, `alembic upgrade head`, `python -m app.cli create-admin`, `python -m app.cli backfill-tasks`, `alembic downgrade -1`, `cp records.db records.db.pre-v1.2.bak`.
- [x] 32 fenced bash blocks (well above ≥7 floor).
- [x] Sequence integrity (line-number monotonic): stamp(75) < u02(113) < ca(171) < bf(213) < uhead(257).
- [x] Commit `b9e9559` exists in git log.

## Self-Check: PASSED

---
*Phase: 17-docs-migration-runbook-operator-guide*
*Completed: 2026-05-01*
