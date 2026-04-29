---
phase: 12-admin-cli-task-backfill
plan: 03
subsystem: cli
tags: [cli, backfill, idempotent, dry-run, tdd, ops-02, scope-01-prereq]

# Dependency graph
requires:
  - phase: 12-admin-cli-task-backfill/12-01
    provides: Typer app singleton + `_get_container()` + `_resolve_admin(email, *, container=None)` test seam + `Container.db_engine()` Singleton provider
  - phase: 11-auth-core-modules-services-di/11-04
    provides: `Container().db_engine()` Singleton (SQLAlchemy Engine bound to Config.DB_URL) + `Container().user_repository()` for `_resolve_admin`
provides:
  - app/cli/commands/backfill_tasks.py — fully implemented `backfill-tasks` Typer subcommand (replaces plan-01 stub)
  - tests/unit/cli/test_backfill_tasks.py — 7 unit tests (CliRunner + mocked Container/engine)
  - OPS-02 satisfied (operator can reassign every `tasks.user_id IS NULL` row to a named admin user)
  - SCOPE-01 prerequisite met (plan 12-04's 0003 migration can rely on zero orphan rows post-run)
affects:
  - 12-04 0003 migration + integration test — the integration test will runner.invoke(`backfill-tasks --admin-email <e> --yes`) against a tmp SQLite DB; the migration's pre-flight orphan-check is the safety-net for forgotten backfill runs
  - Phase 13 SCOPE-01 — `tasks.user_id NOT NULL` FK can land safely after this command runs

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pattern: Three-step backfill flow inside a single engine.begin() transaction — count_before / UPDATE / count_after; commits on context-manager exit if no exception, rolls back if any of the three statements raises"
    - "Pattern: `assume_yes or typer.confirm(...)` short-circuit — collapses Guard 3 (prompt-or-skip) into a single boolean expression; preserves zero-nested-ifs invariant; `--yes` skips the prompt without an extra branch"
    - "Pattern: SQL constants at module scope (`_COUNT_ORPHANS_SQL`, `_UPDATE_SQL`) — single source of truth for the two SQL fragments; the count fragment is reused for pre-flight and post-condition (DRT)"
    - "Pattern: Mocked SQLAlchemy engine in unit tests — `engine.begin().__enter__.return_value = MockConn`, `conn.execute.side_effect = [count_before, update, count_after]` MagicMocks; tests exercise the full path without a real DB"

key-files:
  created:
    - tests/unit/cli/test_backfill_tasks.py — 7 unit tests, 196 lines
    - .planning/phases/12-admin-cli-task-backfill/12-03-SUMMARY.md
  modified:
    - app/cli/commands/backfill_tasks.py — stub (24 lines: placeholder `@app.command()` + typer.Exit(1)) replaced with full implementation (~115 lines: --admin-email/--dry-run/--yes options + three-step transaction + post-verify fail-loud)

key-decisions:
  - "`assume_yes or typer.confirm(...)` short-circuit (NOT `if not assume_yes: ...`): plan body line 392 had `if not assume_yes: proceed = typer.confirm(...)` followed by `if not proceed: ...`. That's two `if`s but the second is a top-level guard so `grep -cE '^\\s+if .*\\bif\\b'` returns 0 either way. Chose the short-circuit form because it's a single boolean expression (DRY/SRP — one decision, not two) and reads naturally: `proceed = assume_yes or typer.confirm(...)` says exactly what it does — proceed if user passed --yes OR if they confirmed at the prompt. Saves one source line + one indent level."
  - "`engine.begin()` (autocommit transaction context manager) NOT `engine.connect()` + manual commit: `begin()` is the documented one-liner for 'open a connection, run statements, COMMIT on success / ROLLBACK on exception'. Eliminates the manual `try/except: rollback / else: commit` boilerplate. Verified by reading SQLAlchemy 2.0 docs (Engine.begin returns a `_engine.Engine.begin` Connection inside a transaction)."
  - "Three-step flow lives ENTIRELY inside the transaction (count_before, UPDATE, count_after): if the post-condition verify fails, raising `typer.Exit(1)` from inside the `with` block triggers the context manager's ROLLBACK — the failed UPDATE is undone. The CLI exits 1 AND the database is restored. Guard 3 (idempotency / dry-run / declined-prompt) all `return` from inside the `with`, which also commits cleanly (zero rows changed). Tiger-style on the post-verify is the whole point of this command."
  - "Engine mock fixture `_build_engine_mock(orphan_count_before, orphan_count_after, rowcount=None)`: builder helper produces a fresh engine mock per test with scripted `execute.side_effect = [count_before, update, count_after]`. Default `rowcount = orphan_count_before` matches the realistic case (every counted orphan was successfully updated) — tests can override to simulate the fail-loud post-verify path (`orphan_count_after=3` after `orphan_count_before=10`)."
  - "Test patches at `app.cli.commands.backfill_tasks._resolve_admin` (NOT `app.cli._helpers._resolve_admin`): Python imports rebind by reference — the command module's `from app.cli._helpers import _resolve_admin` creates a new binding in the command module's namespace; patching the helper module's binding wouldn't affect the command. Same pattern plan 12-02 established for create_admin tests."
  - "`assume_yes` parameter name (NOT `yes`): `yes` is a Python soft-keyword and clashes with the Typer Option flag string `'--yes'`. `assume_yes` is the conventional Python kwarg name for 'skip prompt' (matches `pip install --yes` and apt's `-y/--yes/--assume-yes` synonym set). Typer maps the function parameter `assume_yes` to the CLI flag `--yes`/`-y` via the explicit `typer.Option(..., '--yes', '-y', ...)` arg — no ambiguity."
  - "Confirmation prompt phrasing `'{N} tasks have user_id IS NULL — reassign to {email} (id={id})?'`: surfaces the exact orphan count + admin identity in a single line. Operator can verify both numbers before pressing y. Default=False (locked: dangerous default goes the safe direction; operator must affirmatively type y)."

patterns-established:
  - "Pattern: Backfill command transaction — `engine.begin()` context manager wraps count_before / UPDATE / count_after; raise inside the block triggers ROLLBACK; clean exit triggers COMMIT. Reusable for any future 'verify-update-verify' operator commands (Phase 17 OPS-03 runbook docs will reference this pattern)."
  - "Pattern: `--dry-run` + `--yes` flag pair — `--dry-run` reports without acting; `--yes` skips confirmation. Production runbooks always run `--dry-run` first, eyeball the count, then run `--yes` from the change-management ticket. Both flags are independent: `--dry-run --yes` is allowed (dry-run takes precedence; --yes is harmless when no UPDATE will run)."
  - "Pattern: Engine-mock test fixture builder — `_build_engine_mock(orphan_count_before, orphan_count_after, rowcount)` returns a configured MagicMock engine. Encapsulates the multi-call execute().side_effect scripting so each test reads as a single line of intent. Future 'mock-an-engine' tests can copy this 3-call helper verbatim."

requirements-completed: [OPS-02]

# Metrics
duration: 3 min
completed: 2026-04-29
---

# Phase 12 Plan 03: backfill-tasks command (TDD) Summary

**Wave 2 (parallel-safe with 12-02): `backfill-tasks` Typer subcommand replaces plan-01 stub. Reassigns every `tasks.user_id IS NULL` row to a named admin user via single `engine.begin()` transaction. `--dry-run` reports without acting; `--yes`/`-y` skips the y/N prompt. Post-update count==0 verified inside the same transaction — non-zero raises typer.Exit(1) (ROLLBACK + fail-loud per CONTEXT §92). RED→GREEN TDD across 7 unit tests covering help surface, missing admin, zero orphans (idempotent), dry-run, decline-prompt, --yes success, post-verify failure — all 7 green; zero nested ifs; reuses `_resolve_admin` + `_get_container` from plan 12-01. OPS-02 satisfied; SCOPE-01 prerequisite met for plan 12-04.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-04-29T07:17:58Z
- **Completed:** 2026-04-29T07:21:16Z
- **Tasks:** 1 / 1 (TDD: RED + GREEN)
- **Files created:** 2 (test file + this SUMMARY)
- **Files modified:** 1 (`app/cli/commands/backfill_tasks.py` — stub fully rewritten)
- **Commits:** 2 atomic (RED `6f8eb04` + GREEN `b065af1`)

## Accomplishments

### `tests/unit/cli/test_backfill_tasks.py` — 7 unit tests via CliRunner

1. **`test_help_lists_backfill_tasks`** — invokes `backfill-tasks --help`, asserts exit 0, asserts `'admin-email'` (lowercase substring), `'--dry-run'`, `'--yes'` all present in stdout. Passes only when the final command exposes all three options.
2. **`test_missing_admin_exits_one`** — patches `_resolve_admin` with `side_effect=typer.Exit(code=1)`, asserts exit 1. Proves the command propagates the helper's fail-loud exit code (delegated; CLI module owns no admin-existence logic — DRY).
3. **`test_zero_orphans_idempotent_exit_zero`** — engine mock returns `orphan_count_before=0`; asserts exit 0 + `'No orphan tasks'` in stdout. The UPDATE side_effect is never consumed (idempotency guard fires first).
4. **`test_dry_run_does_not_update`** — `orphan_count_before=42`, `--dry-run` flag; asserts exit 0 + `'Would reassign 42'` in stdout; asserts `conn.execute.call_count == 1` (only the SELECT COUNT ran). Proves dry-run path bypasses the UPDATE entirely.
5. **`test_user_declines_prompt_exits_zero`** — `orphan_count_before=5`, no `--yes` flag, stdin `"n\n"` declines the typer.confirm prompt; asserts exit 0 + `'Aborted'` + `conn.execute.call_count == 1` (count ran, UPDATE didn't).
6. **`test_yes_flag_runs_update_and_verifies`** — `orphan_count_before=42`, `orphan_count_after=0`, `--yes` flag; asserts exit 0 + `'Reassigned 42 orphan tasks'` + `conn.execute.call_count == 3` (count, UPDATE, post-count all ran). Proves the success path runs all three statements in order.
7. **`test_post_update_verification_failure_exits_one`** — `orphan_count_before=10`, `orphan_count_after=3` (bug simulation: UPDATE ran but didn't fully clean up); asserts exit 1 + `'verification failed'` or `'still'` in combined output. Proves the tiger-style post-condition guard fires when the database is in an inconsistent state.

Fixtures (file scope, pytest module-style):
- `runner` — `CliRunner()` (no `mix_stderr` kwarg per Click 8.3 — same as plan 12-02).
- `admin_user` — `User(id=7, email='admin@example.com', password_hash='argon2-fake', plan_tier='pro')`.
- `_build_engine_mock(orphan_count_before, orphan_count_after, rowcount)` — helper builder; scripts `conn.execute.side_effect = [count_before_result, update_result, count_after_result]`. Each MagicMock has the right `.scalar_one()` or `.rowcount` attribute set.
- `patched_helpers` — context-manager fixture; patches both `app.cli.commands.backfill_tasks._get_container` (returns mock Container with `.db_engine()` attribute) and `app.cli.commands.backfill_tasks._resolve_admin` (returns the `admin_user` fixture).

### `app/cli/commands/backfill_tasks.py` — full implementation (replaces stub)

- `@app.command(name='backfill-tasks')` with three Typer Options:
  - `--admin-email` (required, `typer.Option(...)`).
  - `--dry-run` (bool, default False, no short alias).
  - `--yes`/`-y` → param `assume_yes` (bool, default False).
- Three-step flow inside `with engine.begin() as conn:` (single autocommit transaction context manager):
  1. `orphan_count = conn.execute(text(_COUNT_ORPHANS_SQL)).scalar_one()`
  2. Three flat guard clauses (zero nesting):
     - `if orphan_count == 0`: idempotency exit 0 (`'No orphan tasks to backfill.'`)
     - `if dry_run`: dry-run exit 0 (`'Would reassign {N} orphan tasks to admin {email} (id={id}). [dry-run]'`)
     - `proceed = assume_yes or typer.confirm(...)`; `if not proceed`: aborted exit 0 (`'Aborted by user. No changes made.'`)
  3. Action: `result = conn.execute(text(_UPDATE_SQL), {'admin_id': admin.id})`; `rows_affected = result.rowcount`
  4. Post-condition: re-run `_COUNT_ORPHANS_SQL`; `if remaining != 0`: stderr `'verification failed: {N} orphan tasks still remain ...'` + `logger.error(...)` + `raise typer.Exit(code=1)` (raises FROM INSIDE the `with` block — context manager rolls back the failed UPDATE).
- Success path (after `with` block exits cleanly): stdout `f'Reassigned {rows_affected} orphan tasks to admin {admin.email} (id={admin.id}).'` + `logger.info('CLI backfill-tasks success admin_id=%s rows_affected=%s', admin.id, rows_affected)` (admin id + rows count only — no PII, no email/password).
- Module-scope SQL constants:
  - `_COUNT_ORPHANS_SQL = 'SELECT COUNT(*) FROM tasks WHERE user_id IS NULL'` (used twice — pre-flight + post-condition; DRT).
  - `_UPDATE_SQL = 'UPDATE tasks SET user_id = :admin_id WHERE user_id IS NULL'` (parameterized; admin id flows through SQLAlchemy bound parameter).

### Verifier-Enforced Gate Results

| Gate | Expected | Actual | Pass |
|------|----------|--------|------|
| `pytest tests/unit/cli/test_backfill_tasks.py -q` | 7 passed | 7 passed | yes |
| `python -m app.cli --help` lists `backfill-tasks` | match | match | yes |
| `python -m app.cli backfill-tasks --help` shows `--admin-email` | match | match | yes |
| `python -m app.cli backfill-tasks --help` shows `--dry-run` | match | match | yes |
| `python -m app.cli backfill-tasks --help` shows `--yes` | match | match | yes |
| `grep -c '_resolve_admin' app/cli/commands/backfill_tasks.py` ≥ 1 | ≥ 1 | 3 | yes |
| `grep -c '_get_container' app/cli/commands/backfill_tasks.py` ≥ 1 | ≥ 1 | 2 | yes |
| `grep -cE '^\\s+if .*\\bif\\b' app/cli/commands/backfill_tasks.py` == 0 | 0 | 0 | yes |
| `grep -c 'raise typer.Exit' app/cli/commands/backfill_tasks.py` ≥ 1 | ≥ 1 | 1 | yes |
| `grep -c 'user_id IS NULL' app/cli/commands/backfill_tasks.py` ≥ 2 (count + verify) | ≥ 2 | 6 (2 SQL constants + 5 occurrences across docstrings/comments — both SQL strings include the substring; SELECT used twice and UPDATE once) | yes |
| `grep -cE 'logger\\.(info\\|debug\\|warning\\|error).*(email\\|password\\|token)' app/cli/commands/backfill_tasks.py` == 0 | 0 | 0 | yes |
| `grep -c 'dry_run\\|--dry-run' app/cli/commands/backfill_tasks.py` ≥ 1 | ≥ 1 | 4 | yes |
| `grep -c 'yes\\|--yes' app/cli/commands/backfill_tasks.py` ≥ 1 | ≥ 1 | 5 | yes |
| TDD gate sequence in `git log` | `test(...)` then `feat(...)` | `test(12-03): RED ... 6f8eb04` → `feat(12-03): GREEN ... b065af1` (consecutive) | yes |
| `pytest tests/unit/cli/ tests/unit/services/auth/ -q` regressions | 0 | 0 (35/35 pass: 28 pre-existing + 7 new) | yes |

## Task Commits

1. **RED — failing tests** — `6f8eb04` (`test(12-03)`)
   - 7 tests, 196 lines (`tests/unit/cli/test_backfill_tasks.py`).
   - At RED: 2 failed (test_help_lists_backfill_tasks — stub missing options; test_missing_admin_exits_one — patch target missing) + 5 errors (`AttributeError: ... does not have the attribute '_get_container'` — stub doesn't import the helpers yet) = 7/7 failing.

2. **GREEN — implementation** — `b065af1` (`feat(12-03)`)
   - Replaces stub `app/cli/commands/backfill_tasks.py` with full ~115-line implementation.
   - 7/7 tests pass on `pytest tests/unit/cli/test_backfill_tasks.py -q`.

## Files Created/Modified

### Created (2 files)

- `tests/unit/cli/test_backfill_tasks.py` — 7 unit tests, 196 lines.
- `.planning/phases/12-admin-cli-task-backfill/12-03-SUMMARY.md` — this file.

### Modified (1 file)

- `app/cli/commands/backfill_tasks.py` — stub (24 lines: `typer.echo("backfill-tasks: not implemented yet (plan 12-03).", err=True)` + `raise typer.Exit(code=1)`) replaced with full implementation (~115 lines: --admin-email/--dry-run/--yes options + module SQL constants + `engine.begin()` three-step flow + tiger-style post-verify fail-loud).

## Decisions Made

See frontmatter `key-decisions` for the full set. Highlights:

- **`assume_yes or typer.confirm(...)` short-circuit:** collapses Guard 3 into a single boolean expression. Reads `proceed = assume_yes or typer.confirm(...)` — proceed if user passed --yes OR if they confirmed at the prompt. Saves one source line and keeps the function flat.
- **`engine.begin()` over `engine.connect()` + manual commit:** SQLAlchemy 2.0 `Engine.begin()` is the documented context manager that COMMITs on clean exit and ROLLBACKs on exception. Eliminates manual `try/except: rollback / else: commit` boilerplate.
- **Post-verify raises FROM INSIDE the `with` block:** if the orphan count is non-zero after UPDATE, raising `typer.Exit(1)` triggers the context manager's ROLLBACK — the failed UPDATE is undone, AND the CLI exits 1. Tiger-style fail-loud is the whole point of this command.
- **`assume_yes` param name (not `yes`):** matches conventional Python kwarg name (cf. `pip install --yes`); avoids the soft-keyword clash. Typer maps the function parameter to the CLI flag `--yes`/`-y` via explicit `typer.Option(..., '--yes', '-y', ...)`.
- **SQL constants at module scope:** `_COUNT_ORPHANS_SQL` is referenced twice (pre-flight count + post-condition verify) — single source of truth (DRT). `_UPDATE_SQL` is parameterized (`:admin_id`); SQLAlchemy bound parameter prevents SQL injection.

## Deviations from Plan

**None.** Plan executed exactly as written. The plan body's example code was thorough and accurate; minor stylistic tightening (the `assume_yes or typer.confirm(...)` short-circuit replacing the plan body's two-step `if not assume_yes: proceed = ...; if not proceed: ...`) is documented as a key-decision but is functionally equivalent — both forms yield the same control flow, the same test pass rates, and the same `grep -cE '^\s+if .*\bif\b'` zero. The choice was style-only.

## Issues Encountered

- **Pre-existing dirty working tree at plan start (carried from earlier phases, unchanged):** `M README.md`, `M app/docs/db_schema.md`, `M app/docs/openapi.json`, `M app/docs/openapi.yaml`, `M app/main.py`, `M frontend/src/components/upload/FileQueueItem.tsx`, untracked `.claude/`, `app/core/auth.py`, `models/`. None touched by this plan; out of scope per executor scope-boundary rule. Same set as plan 12-01 + 12-02 reported.
- **Logging at import-time:** `app.core.logging` runs `logging.config.dictConfig(...)` and emits two INFO lines (`Environment: production`, `Log level: INFO`) on every CLI invocation. Cosmetic only — does NOT affect Typer help-text rendering or test assertions (`runner.invoke` captures stdout cleanly). Documented in 12-01 and 12-02 SUMMARYs as deferred.
- **CRLF warnings on git add (Windows):** `LF will be replaced by CRLF the next time Git touches it` for the new test file and the modified command module. Cosmetic Windows-line-ending warning; does not affect CI / Linux runs.

## User Setup Required

None. All deps were installed in `.venv` from plan 12-01 (`typer[all]>=0.12.0`, `sqlalchemy>=2`).

## Next Phase Readiness

Plan **12-04 — 0003 migration + integration test** is now unblocked:

- The migration's pre-flight orphan-check (`SELECT COUNT(*) FROM tasks WHERE user_id IS NULL == 0`) is the safety-net for forgotten backfill runs; this plan provides the operator command that drives that count to zero.
- The integration test in `tests/integration/test_cli_backfill_e2e.py` can use Typer's `CliRunner` to exercise the full flow programmatically:
  1. `alembic upgrade head` (0001 + 0002).
  2. `INSERT INTO tasks (...) VALUES (...)` rows with `user_id IS NULL` directly.
  3. `runner.invoke(app, ['create-admin', '--email', 'admin@example.com'])` (mocked getpass).
  4. `runner.invoke(app, ['backfill-tasks', '--admin-email', 'admin@example.com', '--yes'])`.
  5. `alembic upgrade head` again (now 0003 — added by plan 12-04).
  6. Verify schema: `pragma_table_info('tasks')` shows user_id NOT NULL + `idx_tasks_user_id` exists.

OPS-02 (operator backfill CLI) is fully satisfied:
- `python -m app.cli backfill-tasks --admin-email <e>` is a registered Typer subcommand visible in `--help`.
- Counts orphans BEFORE any UPDATE — operator gets the number for verification.
- `--dry-run` reports without acting (production runbook safety).
- `--yes`/`-y` skips the y/N prompt for scripted automation (CI/CD or runbook ticket).
- Post-update count == 0 verified inside the same transaction; non-zero ROLLBACKs and exits 1 (tiger-style).
- 0 orphans → exit 0 'No orphan tasks to backfill' (idempotent — safe to re-run).
- Reuses `_resolve_admin` + `_get_container` from plan 12-01 helpers (DRY).
- Zero hash logic, zero auth logic, zero ORM-mapper logic — pure SQL via raw bound parameters (SRP).

SCOPE-01's prerequisite is met: every `tasks.user_id IS NULL` row will have a valid `user_id` after this command runs. Plan 12-04's 0003 migration can rely on this.

## TDD Gate Compliance

- [x] RED commit (`test(12-03): RED — backfill-tasks Typer command tests`) — `6f8eb04`
- [x] GREEN commit (`feat(12-03): GREEN — backfill-tasks command (OPS-02 / SCOPE-01 backfill)`) — `b065af1`, immediately after RED
- [x] No REFACTOR commit needed (implementation is already minimal: ~115 lines, zero duplication, single SRP responsibility, two SQL constants for the only repeated literal)

## Self-Check: PASSED

Verified after SUMMARY write:

- `tests/unit/cli/test_backfill_tasks.py` — FOUND (196 lines, 7 tests)
- `app/cli/commands/backfill_tasks.py` — FOUND (~115 lines, full implementation, no stub markers)
- Commit `6f8eb04` (RED) — FOUND in `git log --oneline`
- Commit `b065af1` (GREEN) — FOUND in `git log --oneline`
- `pytest tests/unit/cli/test_backfill_tasks.py -v` — 7/7 passed
- `pytest tests/unit/cli/ tests/unit/services/auth/ -q` — 35/35 passed (no regressions)
- `python -m app.cli backfill-tasks --help` — exits 0 with `--admin-email`, `--dry-run`, `--yes` Options
- `python -m app.cli --help` — exits 0 listing both `create-admin` and `backfill-tasks` subcommands

---
*Phase: 12-admin-cli-task-backfill*
*Completed: 2026-04-29*
