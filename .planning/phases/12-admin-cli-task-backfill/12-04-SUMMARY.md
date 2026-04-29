---
phase: 12-admin-cli-task-backfill
plan: 04
subsystem: alembic
tags: [alembic, migration, scope-01, integration-test, e2e, phase-close]

# Dependency graph
requires:
  - phase: 12-admin-cli-task-backfill/12-02
    provides: create-admin Typer subcommand (OPS-01) — bootstraps admin user with plan_tier='pro'
  - phase: 12-admin-cli-task-backfill/12-03
    provides: backfill-tasks Typer subcommand (OPS-02) — reassigns tasks.user_id IS NULL rows to admin
  - phase: 10-alembic-and-auth-schema/10-03
    provides: 0002_auth_schema migration — adds tasks.user_id NULLABLE INTEGER + fk_tasks_user_id FK
provides:
  - alembic/versions/0003_tasks_user_id_not_null.py — migration: tasks.user_id NOT NULL + idx_tasks_user_id, with pre-flight orphan guard
  - tests/integration/test_phase12_cli_backfill_e2e.py — e2e integration test exercising the full Phase 12 contract
  - SCOPE-01 satisfied: tasks.user_id is NOT NULL after backfill migration; existing rows assigned to bootstrap admin user
  - Phase 12 closure — Phase 13 (Atomic Backend Cutover) can build SCOPE-02/03/04 on a verified-clean foundation
affects:
  - Phase 13 SCOPE-02/03/04: per-user task scoping can rely on tasks.user_id NOT NULL invariant
  - Phase 16 VERIFY-* migration smoke test: 0003 chain proven against tmp DB; production rollout (records.db) follows the same path

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pattern: Pre-flight orphan-row guard inside upgrade() — `op.get_bind().execute(sa.text(SQL)).scalar_one()` checks invariant; raises RuntimeError with operator-actionable message if violated. Tiger-style fail-loud (CONTEXT §138). Migration refuses to run rather than fail mid-batch with FK / NOT NULL violation."
    - "Pattern: Module-scope `_COUNT_ORPHANS_SQL` constant — single source of truth for the orphan-count fragment; reused by 0003 pre-flight and (if extended) by future analogous migrations. DRT (CONTEXT §65)."
    - "Pattern: `op.batch_alter_table('tasks')` for SQLite-safe NOT NULL tightening + index creation — same idiom 0002 used; preserves existing FK fk_tasks_user_id without redeclaration."
    - "Pattern: Test-only `-c` preamble for Windows-getpass workaround — child process Python is invoked with `python -c \"<patch>; from app.cli import app; app()\" <args>`. Patches `getpass.getpass` to read from stdin BEFORE app.cli imports — Windows msvcrt.getwch() bypass. Production source untouched."
    - "Pattern: subprocess.run env-var injection for SQLAlchemy engine binding — DB_URL env propagates to child Python's app.infrastructure.database.connection module-load (engine binds at import). Same pattern test_alembic_migration.py established in Phase 10."

key-files:
  created:
    - alembic/versions/0003_tasks_user_id_not_null.py — 75 lines; pre-flight guard + batch_alter_table NOT NULL + idx_tasks_user_id; downgrade reverses both
    - tests/integration/test_phase12_cli_backfill_e2e.py — 255 lines; 2 integration tests (happy path + negative pre-flight)
    - .planning/phases/12-admin-cli-task-backfill/12-04-SUMMARY.md
  modified: []

key-decisions:
  - "Test-only Windows-getpass workaround via `-c` preamble (NOT modifying create_admin.py): Plan body line 287-298 expected POSIX `getpass.getpass` fallback to stdin readline when no TTY is attached. Linux/Mac honor this; Windows `getpass.getpass` reads via `msvcrt.getwch()` directly from the keyboard buffer, ignoring stdin pipes. The test feeds password via subprocess.run(input=...) which a piped Windows getpass never sees. Fix: invoke child Python with `python -c \"<patch>; from app.cli import app; app()\" <args>` — patch monkeypatches getpass.getpass to read from sys.stdin BEFORE app.cli imports. Production CLI source (app/cli/commands/create_admin.py) is untouched. Locked rule (CONTEXT §141): password is read via getpass ONLY in production. Patch lives in test code only."
  - "subprocess invocation pattern preserved (NOT in-process Typer CliRunner): Plan must-have truth #5 mentioned 'Typer CliRunner' but plan body uses subprocess.run([sys.executable, '-m', 'app.cli', ...]). Subprocess is REQUIRED for this test because `app.infrastructure.database.connection` reads DB_URL at module-load — once imported in the pytest process, the engine is bound to records.db. A fresh Python subprocess re-imports against the tmp DB. CliRunner cannot switch DBs in-process. The test runs subprocess (matches test_alembic_migration.py style + plan body) AND uses the `-c` preamble to enable getpass piping (see preceding decision)."
  - "engine.dispose() cleanup wrapped in try/finally for the happy path: Step 9 (assert IntegrityError on NULL insert) closes connection on assertion failure. Without dispose() the SQLite file would stay open, leaking the file handle and blocking pytest tmp_path cleanup on Windows (file-locking semantics differ from Linux). try/finally ensures the engine is always disposed."
  - "Negative test asserts at least one of {`'user_id IS NULL' in combined`, `'orphan' in combined.lower()`, `'backfill-tasks' in combined`}: error message can vary in surface form (alembic wraps RuntimeError in its own traceback formatting). Three substrings cover all observable forms — the migration's RuntimeError text contains both 'user_id IS NULL' and 'backfill-tasks' literally; alembic re-emits the message in stderr."
  - "Pre-flight count uses `bind.execute(sa.text(_COUNT_ORPHANS_SQL)).scalar_one()` (NOT `.scalar()`): scalar_one() raises if zero rows are returned (defensive — a malformed COUNT query would silently return None with .scalar()). For a well-formed COUNT(*), scalar_one() always succeeds and returns the integer."
  - "Migration `if orphan_count > 0: raise` — flat guard clause, zero nesting, single decision point. Verifier grep `grep -cE '^\\s+if .*\\bif\\b'` returns 0."

patterns-established:
  - "Pattern: e2e migration test = subprocess alembic + subprocess CLI + tmp SQLite. Reusable for future migration plans that depend on a CLI-driven precondition (e.g. data backfills, schema preconditions)."
  - "Pattern: pre-flight invariant guard at the top of upgrade() — read-only SELECT first, raise on violation, only then run schema mutations. Future migrations with similar safety nets (FK-bearing column tightening, unique-constraint addition with potential dupes) follow this template."

requirements-completed: [SCOPE-01]

# Metrics
duration: 90 min
completed: 2026-04-29
---

# Phase 12 Plan 04: 0003 Migration + e2e Integration Test Summary

**Wave 3 closure: `0003_tasks_user_id_not_null` Alembic migration tightens `tasks.user_id` to NOT NULL + adds `idx_tasks_user_id`, gated by a pre-flight orphan-row guard that refuses to run if the operator skipped `backfill-tasks`. Two integration tests exercise the full Phase 12 contract: happy path (fresh DB → 0001+0002 → seed 3 orphans → create-admin → backfill → 0003 → assert NOT NULL + index + new NULL insert raises IntegrityError) and negative path (skip backfill → 0003 fails fast with stderr mentioning orphans/backfill-tasks). 2/2 e2e tests green; 7/7 phase 10 alembic regression tests still green; 35/35 phase 11+12 unit tests still green. SCOPE-01 satisfied; Phase 12 milestone closed.**

## Performance

- **Duration:** ~90 min
- **Started:** 2026-04-29T07:25:19Z
- **Completed:** 2026-04-29T08:55:56Z
- **Tasks:** 2 / 2
- **Files created:** 3 (migration + e2e test + this SUMMARY)
- **Files modified:** 0
- **Commits:** 2 atomic (Task 1 `509b2ab` migration + Task 2 `970a54f` e2e test)

Note on duration: ~90 min reflects Windows-getpass debugging overhead. The plan body assumed POSIX `getpass.getpass` stdin fallback; Windows `msvcrt.getwch()` reads keyboard directly, requiring a test-only `-c` preamble workaround. Once diagnosed, the fix landed atomically in the existing Task 2 commit. See "Deviations from Plan" below.

## Accomplishments

### `alembic/versions/0003_tasks_user_id_not_null.py` (Task 1)

- Module shape mirrors 0002_auth_schema.py:
  - `revision: str = "0003_tasks_user_id_not_null"`
  - `down_revision: Union[str, None] = "0002_auth_schema"`
  - Module-scope `_COUNT_ORPHANS_SQL = "SELECT COUNT(*) FROM tasks WHERE user_id IS NULL"` constant (DRT — referenced by upgrade pre-flight; available to future migrations).
- `upgrade()`:
  1. Pre-flight: `bind.execute(sa.text(_COUNT_ORPHANS_SQL)).scalar_one()` — count orphan rows.
  2. Flat guard: `if orphan_count > 0: raise RuntimeError(f"Refusing to apply ... {orphan_count} tasks have user_id IS NULL. Run \`python -m app.cli backfill-tasks --admin-email <e>\` first.")`.
  3. `with op.batch_alter_table("tasks") as batch_op:` — `alter_column("user_id", existing_type=sa.Integer(), nullable=False)` + `create_index("idx_tasks_user_id", ["user_id"])`.
- `downgrade()`:
  - `with op.batch_alter_table("tasks") as batch_op:` — `drop_index("idx_tasks_user_id")` + `alter_column("user_id", existing_type=sa.Integer(), nullable=True)`.
- `python -m alembic history` reports the chain: `0003_tasks_user_id_not_null (head) → 0002_auth_schema → 0001_baseline → <base>`.

### `tests/integration/test_phase12_cli_backfill_e2e.py` (Task 2)

Two `@pytest.mark.integration` tests:

1. **`test_phase12_full_flow_create_admin_backfill_then_0003`** (greenfield happy path):
   - `_run_alembic(["upgrade", "0002_auth_schema"], db_url)` lands at 0002.
   - `_seed_orphan_tasks(db_path, count=3)` inserts 3 rows with `user_id IS NULL`.
   - `_run_cli(["create-admin", "--email", "admin@e2e.test"], stdin_input="strong-pw-12345\\nstrong-pw-12345\\n")` — exit 0 + stdout contains `"Admin user"` + `"created"`.
   - `_run_cli(["backfill-tasks", "--admin-email", "admin@e2e.test", "--yes"])` — exit 0 + stdout contains `"Reassigned 3"`.
   - `_run_alembic(["upgrade", "head"], db_url)` — exit 0 (applies 0003).
   - PRAGMA `table_info(tasks)` — assert `user_id` row's `notnull == 1`.
   - sqlite_master query — assert `idx_tasks_user_id` is in the indexes set for tasks.
   - `INSERT ... user_id NULL ...` — assert `IntegrityError` raised by SQLite NOT NULL constraint.
2. **`test_phase12_migration_refuses_to_run_with_orphans`** (negative path / pre-flight guard):
   - `_run_alembic(["upgrade", "0002_auth_schema"], db_url)` lands at 0002.
   - `_seed_orphan_tasks(db_path, count=2)` — 2 orphans, but skip backfill.
   - `_run_alembic(["upgrade", "head"], db_url, check=False)` — assert `returncode != 0`.
   - assert stderr/stdout combined mentions one of `"user_id IS NULL"` / `"orphan"` / `"backfill-tasks"`.

Helpers:
- `_run_alembic(args, db_url, *, check=True)` — `subprocess.run([sys.executable, "-m", "alembic", *args], env={**os.environ, "DB_URL": db_url}, check=check, capture_output=True, text=True)`.
- `_run_cli(args, db_url, *, stdin_input=None, check=True)` — `subprocess.run([sys.executable, "-c", _CLI_PREAMBLE, *args], ...)`. The `_CLI_PREAMBLE` is a tiny Python snippet that monkey-patches `getpass.getpass` to read from `sys.stdin` BEFORE importing `app.cli`. Required because Windows `getpass.getpass` reads via `msvcrt.getwch()` (keyboard) and ignores piped stdin — the plan body assumed POSIX stdin fallback semantics.
- `_make_engine(db_path)` — `create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})` (mirrors test_alembic_migration.py).
- `_seed_orphan_tasks(db_path, count)` — INSERT N orphan tasks via raw `text()` SQL inside `engine.begin()`.

### Verifier-Enforced Gate Results

| Gate | Expected | Actual | Pass |
|------|----------|--------|------|
| `python -c "...assert m.revision and m.down_revision and callable(m.upgrade) and callable(m.downgrade)"` | exit 0 | `module_ok` | yes |
| `grep -c "down_revision = \"0002_auth_schema\"" 0003_*.py` | == 1 | 1 | yes |
| `grep -c "RuntimeError" 0003_*.py` | >= 1 | 3 | yes |
| `grep -c "idx_tasks_user_id" 0003_*.py` | >= 2 | 5 | yes |
| `grep -c "user_id IS NULL" 0003_*.py` | >= 1 | 4 | yes |
| `grep -c "nullable=False" 0003_*.py` | >= 1 | 1 | yes |
| `grep -c "nullable=True" 0003_*.py` | >= 1 | 1 | yes |
| `grep -cE "^\\s+if .*\\bif\\b" 0003_*.py` | == 0 | 0 | yes |
| `python -m alembic history --verbose \| grep 0003` | match | `Rev: 0003_tasks_user_id_not_null (head) Parent: 0002_auth_schema` | yes |
| `pytest tests/integration/test_phase12_cli_backfill_e2e.py -v -m integration` | 2 passed | 2 passed (33.37s) | yes |
| `grep -c "@pytest.mark.integration" test_phase12_*.py` | == 2 | 2 | yes |
| `grep -c "alembic" test_phase12_*.py` | >= 2 | 10 | yes |
| `grep -c "create-admin" test_phase12_*.py` | >= 1 | 5 | yes |
| `grep -c "backfill-tasks" test_phase12_*.py` | >= 1 | 6 | yes |
| `grep -c "PRAGMA table_info" test_phase12_*.py` | >= 1 | 4 | yes |
| `grep -c "idx_tasks_user_id" test_phase12_*.py` | >= 1 | 5 | yes |
| `pytest tests/integration/test_alembic_migration.py -v -m integration` | 7 passed | 7 passed (regression check) | yes |
| `pytest tests/unit/cli tests/unit/services/auth -q` | 35 passed | 35 passed (regression check) | yes |

## Alembic History Output (verifier-grade evidence)

```
0002_auth_schema -> 0003_tasks_user_id_not_null (head), tasks_user_id_not_null — tighten tasks.user_id to NOT NULL + add idx_tasks_user_id.
0001_baseline -> 0002_auth_schema, auth_schema — adds 6 new tables and tasks.user_id FK; migrates tasks tz-aware datetimes.
<base> -> 0001_baseline, baseline — creates the tasks table matching the current ORM shape.
```

Chain `0003 → 0002 → 0001 → base` confirmed.

## Task Commits

1. **Task 1: 0003 migration** — `509b2ab` (`feat(12-04)`)
   - File created: `alembic/versions/0003_tasks_user_id_not_null.py` (75 lines).
   - Pre-flight orphan guard (RuntimeError) + batch_alter_table NOT NULL + idx_tasks_user_id; downgrade reverses both.
2. **Task 2: e2e integration test** — `970a54f` (`test(12-04)`)
   - File created: `tests/integration/test_phase12_cli_backfill_e2e.py` (255 lines).
   - 2 tests covering happy path + pre-flight guard fail-loud.
   - Includes test-only `-c` preamble Windows-getpass workaround documented in module docstring + key-decisions.

## Files Created/Modified

### Created (3 files)

- `alembic/versions/0003_tasks_user_id_not_null.py` — 75 lines.
- `tests/integration/test_phase12_cli_backfill_e2e.py` — 255 lines.
- `.planning/phases/12-admin-cli-task-backfill/12-04-SUMMARY.md` — this file.

### Modified (0 files)

No existing files modified. Plan executed without touching any production source — production code is untouched, the test-only getpass preamble lives entirely in the integration test file.

## Decisions Made

See frontmatter `key-decisions` for the full set. Highlights:

- **Test-only Windows-getpass workaround via `-c` preamble (Rule 3 — Blocking):** Production source untouched; the patch monkey-patches `getpass.getpass` in the child Python BEFORE `app.cli` imports. Plan body assumed POSIX stdin fallback; Windows `msvcrt.getwch()` reads keyboard directly, breaking the original subprocess + input=... pattern.
- **subprocess pattern preserved (NOT in-process CliRunner):** the SQLAlchemy engine binds to DB_URL at module-load. Once imported in pytest, it's bound to records.db. CliRunner cannot re-bind. Subprocess re-imports the engine cleanly against the tmp DB. Same pattern as Phase 10's `test_alembic_migration.py`.
- **engine.dispose() in try/finally:** required on Windows for tmp_path cleanup; without it pytest's tmp_path cleanup races against SQLite file-handle release.
- **scalar_one() not scalar():** defensive — raises on zero-row return, ensuring a malformed COUNT(*) doesn't silently flow None into the comparison.
- **`if orphan_count > 0: raise` flat guard:** zero nesting; verifier grep `^\s+if .*\bif\b` returns 0.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Windows `getpass.getpass` cannot be piped via subprocess.run(input=...)**

- **Found during:** Task 2, first pytest run of `test_phase12_full_flow_create_admin_backfill_then_0003`. Test hung after `subprocess.run(input="strong-pw-12345\\n...")` — the create-admin child process never returned.
- **Issue:** Plan body lines 287-298 explicitly anticipate POSIX behavior: "subprocess.run with input='pw\\npw\\n' satisfies this. NOTE — production operators run in a TTY; this stdin fallback is acceptable ONLY for automated tests." The note describes Linux/Mac semantics where `getpass.getpass` checks `sys.stdin.isatty()` and falls back to `fallback_getpass(prompt, stream)` (which `sys.stdin.readline()` reads). On Windows, `getpass.getpass` (in CPython 3.13's `Lib/getpass.py`) is `win_getpass`: it checks `if sys.stdin is not sys.__stdin__: return fallback_getpass(...)` — but in a child subprocess the stdin IS `sys.__stdin__`, so it goes directly to `msvcrt.getwch()` reading the keyboard buffer. The piped stdin bytes are never read; the call blocks on a keyboard event that never arrives.
- **Fix:** Test-only `-c` preamble. The `_run_cli` helper invokes the child Python as `python -c "<preamble>; from app.cli import app; app()" <args>` instead of `python -m app.cli <args>`. The preamble is a one-line snippet:
  ```python
  import sys, getpass
  getpass.getpass = lambda prompt='Password: ', stream=None: sys.stdin.readline().rstrip('\n')
  from app.cli import app
  app()
  ```
  The preamble runs BEFORE `app.cli` is imported, so `app.cli.commands.create_admin`'s `import getpass` binding picks up the patched function. The subprocess inherits DB_URL (engine binds correctly), Typer dispatches the same subcommand, the child process exits via `raise typer.Exit(...)` — the only delta vs. `python -m app.cli` is the in-child getpass binding. Production code (`app/cli/commands/create_admin.py`) is unchanged. Locked rule (CONTEXT §141) preserved: password is read via `getpass` ONLY in production.
- **Files modified:** `tests/integration/test_phase12_cli_backfill_e2e.py` only — `_CLI_PREAMBLE` constant + `_run_cli` invocation. Manual probe confirmed the workaround:
  ```
  $ (printf "strong-pw-12345\nstrong-pw-12345\n") | DB_URL=sqlite:////tmp/test.db python -c "<preamble>" create-admin --email admin@e2e.test
  Admin user 1 created with email admin@e2e.test
  EXIT=0
  ```
- **Verification:** Both e2e tests pass (33.37s) — `test_phase12_full_flow_create_admin_backfill_then_0003 PASSED [50%]` + `test_phase12_migration_refuses_to_run_with_orphans PASSED [100%]`. No regressions in phase 10 alembic tests (7/7 still pass) or phase 11+12 unit tests (35/35 still pass).
- **Committed in:** `970a54f` (Task 2 commit) — fix landed atomically with the test it enables.

---

**Total deviations:** 1 auto-fixed (Rule 3 — Blocking platform-specific behavior).
**Impact on plan:** Necessary for the plan's own integration tests to pass on Windows (development OS). The plan body's POSIX assumption was correct for Linux/Mac CI; Windows requires the preamble workaround. Production source is untouched, locked CLI rules preserved, plan acceptance criteria met. Zero scope creep.

## Issues Encountered

- **Pre-existing dirty working tree at plan start (carried from earlier phases, unchanged):** `M README.md`, `M app/docs/db_schema.md`, `M app/docs/openapi.json`, `M app/docs/openapi.yaml`, `M app/main.py`, `M frontend/src/components/upload/FileQueueItem.tsx`, untracked `.claude/`, `app/core/auth.py`, `models/`. None touched by this plan; out of scope per executor scope-boundary rule. Same set as plans 12-01/02/03 reported.
- **Logging at import-time:** `app.core.logging` runs `logging.config.dictConfig(...)` and emits two INFO lines (`Environment: production`, `Log level: INFO`) on every CLI invocation, including the integration test subprocess invocations. Cosmetic only — does NOT affect Typer help-text rendering or test assertions (test asserts on substrings, not exact-match). Documented in 12-01/02/03 SUMMARYs as deferred.
- **CRLF warnings on git add (Windows):** `LF will be replaced by CRLF the next time Git touches it` for both new files. Cosmetic Windows-line-ending warning; does not affect CI / Linux runs.

## User Setup Required

None — typer, alembic, sqlalchemy were all already installed in `.venv` from earlier phases.

## Phase 12 Milestone Closure

This plan closes Phase 12. SCOPE-01 ("`tasks.user_id` is NOT NULL after backfill migration; existing rows assigned to the bootstrap admin user") is satisfied:

- `tasks.user_id` is NOT NULL after `0003_tasks_user_id_not_null` upgrade — verified by `PRAGMA table_info(tasks)` row 3 (`notnull == 1`).
- Pre-flight guard refuses to apply 0003 with orphans present — verified by negative integration test.
- All Phase 12 must-have truths met:
  1. `0003_tasks_user_id_not_null` exists with `down_revision = "0002_auth_schema"` ✓
  2. `upgrade()` performs pre-flight `SELECT COUNT(*) FROM tasks WHERE user_id IS NULL` and raises RuntimeError if > 0 ✓
  3. `upgrade()` uses `op.batch_alter_table('tasks')` for NOT NULL + creates `idx_tasks_user_id` ✓
  4. `downgrade()` drops index and reverts user_id to nullable ✓
  5. e2e integration test (happy path) passes ✓
  6. e2e integration test (negative pre-flight) passes ✓

Phase 13 (Atomic Backend Cutover) can now build SCOPE-02 (per-user task scoping), SCOPE-03 (account data delete), SCOPE-04 (cross-user invisibility) on a verified-clean foundation: every task row has a non-null user_id pointing at a real user, and the schema enforces this invariant going forward.

## TDD Gate Compliance

This plan is `type: execute` (not `type: tdd`); TDD gate enforcement does not apply. Tests are integration-level e2e gates, not unit-test RED/GREEN cycles.

## Self-Check: PASSED

Verified after SUMMARY write:

- `alembic/versions/0003_tasks_user_id_not_null.py` — FOUND
- `tests/integration/test_phase12_cli_backfill_e2e.py` — FOUND
- Commit `509b2ab` (Task 1) — FOUND in `git log --oneline`
- Commit `970a54f` (Task 2) — FOUND in `git log --oneline`
- `pytest tests/integration/test_phase12_cli_backfill_e2e.py -v -m integration` — 2/2 passed (33.37s)
- `pytest tests/integration/test_alembic_migration.py -v -m integration` — 7/7 passed (regression: no Phase 10 break)
- `pytest tests/unit/cli tests/unit/services/auth -q` — 35/35 passed (regression: no Phase 11+12 unit break)
- `python -m alembic history` — chain `0003 → 0002 → 0001 → base` confirmed

---
*Phase: 12-admin-cli-task-backfill*
*Plan: 04 (final, Wave 3)*
*Completed: 2026-04-29 — closes Phase 12 — SCOPE-01 satisfied*
