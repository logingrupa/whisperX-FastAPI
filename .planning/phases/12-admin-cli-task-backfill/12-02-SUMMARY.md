---
phase: 12-admin-cli-task-backfill
plan: 02
subsystem: cli
tags: [cli, create-admin, getpass, argon2, tdd, ops-01]

# Dependency graph
requires:
  - phase: 12-admin-cli-task-backfill/12-01
    provides: Typer app singleton + `_get_container` helper + `AuthService.register(*, plan_tier='trial')` keyword-only kwarg
  - phase: 11-auth-core-modules-services-di/11-04
    provides: Container().auth_service() Factory + UserAlreadyExistsError + WeakPasswordError + ValidationError base
provides:
  - app/cli/commands/create_admin.py — fully implemented `create-admin` Typer subcommand (replaces plan-01 stub)
  - tests/unit/cli/__init__.py — test package marker
  - tests/unit/cli/test_create_admin.py — 5 unit tests (CliRunner + mocked getpass + mocked Container)
  - OPS-01 satisfied end-to-end (CLI bootstrap path for first admin user)
affects:
  - 12-03 backfill-tasks command — can now rely on `_resolve_admin` finding the admin row this command creates
  - 12-04 integration test — can `runner.invoke(app, ['create-admin', '--email', ...])` against tmp SQLite

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pattern: getpass-only password input (entry + confirm); never a Typer Option/Argument — verifier grep gate `password.*=.*typer\\.` returns 0"
    - "Pattern: ValidationError base catch in CLI handlers — single `except ValidationError` covers WeakPasswordError + future ValidationError subclasses without changing the command (open/closed)"
    - "Pattern: `_get_container` patched at module-import-site (`app.cli.commands.create_admin._get_container`), not at the helper module — preserves the test seam introduced in plan 12-01"
    - "Click 8.2+ / Typer 0.20+: `CliRunner(mix_stderr=False)` kwarg removed — stderr/stdout are separated by default; `result.stderr` and `result.stdout` work independently"

key-files:
  created:
    - tests/unit/cli/__init__.py — package marker (1-line docstring)
    - tests/unit/cli/test_create_admin.py — 5 unit tests, 130 lines
    - .planning/phases/12-admin-cli-task-backfill/12-02-SUMMARY.md
  modified:
    - app/cli/commands/create_admin.py — stub (`# Stub — populated in plan 12-02`) replaced with full ~70-line implementation

key-decisions:
  - "ValidationError base used in `except` clause (not WeakPasswordError directly): `WeakPasswordError` is a `ValidationError` subclass per app/core/exceptions.py:694. Catching the base lets future `ValidationError` subclasses (e.g. EmailFormatError, InvalidEmailDomainError) flow through the same exit-1-with-user-message path without changing this command. Plan body line 339 example caught WeakPasswordError; the broader catch is more SRP-correct (the CLI's job is 'translate any registration ValidationError into a CLI exit-1', not 'handle one specific subclass')."
  - "RED help-test asserts `'--email' in result.stdout`, not `'create-admin' in result.stdout`: Plan body line 207 had `'create-admin' in stdout or 'Email' in stdout` — but the plan-01 stub already registers `@app.command(name='create-admin')`, so `'create-admin' in stdout` was true at RED time, which means the stub passed the test trivially. Tightened the assertion to `'--email' in stdout` so RED genuinely fails on the stub (which has no options) and GREEN genuinely passes (stub adds `--email` Typer Option). RED was confirmed: 1 failed (`AssertionError: assert '--email' in ...`) + 4 errors (`AttributeError: ... does not have the attribute '_get_container'`) = 5/5 failing."
  - "`CliRunner()` not `CliRunner(mix_stderr=False)`: Click 8.3.0 (installed) raised `TypeError: CliRunner.__init__() got an unexpected keyword argument 'mix_stderr'`. The plan body line 178 used the older 8.1 kwarg. In Click 8.2+ stderr is separated by default; `result.stderr` and `result.stdout` are independent attributes. Documented inline in the runner fixture."
  - "Catch is for `UserAlreadyExistsError` THEN `ValidationError`: Order matters — `UserAlreadyExistsError` IS-A `ValidationError`, so the more-specific catch must come first. The duplicate-email path emits a non-enumerating message (`Admin user already exists. No changes made.`); the generic ValidationError path emits `Password rejected: <user_message>`. Without the ordering, duplicate-email would leak as 'Password rejected: An account with this email already exists.' — a Pydantic-style message in the wrong context."
  - "`raise typer.Exit(code=1)` from inside `except` blocks (not `return`): typer.Exit is itself an exception that Typer's runtime intercepts to set the process exit code. Using `raise typer.Exit(code=1)` from within an `except` block does NOT chain (Typer suppresses `__context__` for its own exit-control exceptions); the user-visible result is exit 1 with the typer.echo text on stderr, no traceback leaked."
  - "`logger.warning('CLI create-admin idempotent re-run id_hint=existing')` on the duplicate-email path: matches the same `<redacted>` discipline plan 12-01 set in `_resolve_admin` — the user-facing typer.echo to stderr DOES include the email (operator visibility on the TTY is fine), but the persisted log line does not (RedactingFilter contract)."

patterns-established:
  - "Pattern: TDD RED-then-GREEN with grep-gated quality assertions inline in the plan body — `grep -c \"getpass.getpass\"` ≥2, `grep -cE \"password.*=.*typer\\.\"` ==0, `grep -cE \"^\\s+if .*\\bif\\b\"` ==0, `grep -cE \"logger\\.(info|debug|warning|error).*password\"` ==0. Verifier reruns these gates."
  - "Pattern: CliRunner test fixture for Typer subcommands — `runner.invoke(app, ['<subcommand>', '--<flag>', '<val>'])` with `unittest.mock.patch` at the import-site for any helper the command imports. Patches at `app.cli.commands.<module>.<symbol>` (the import binding), NOT at `app.cli._helpers.<symbol>` (the source binding) — Python imports rebind by reference."

requirements-completed: [OPS-01]

# Metrics
duration: 5 min
completed: 2026-04-29
---

# Phase 12 Plan 02: create-admin command (TDD) Summary

**Wave 2 (parallel-safe with 12-03): `create-admin` Typer subcommand replaces plan-01 stub. Password read via `getpass.getpass()` twice (NEVER as a flag); delegates to `AuthService.register(email, pw, plan_tier='pro')`. Idempotent on re-run. RED→GREEN TDD across 5 unit tests covering help surface, password mismatch, success path, duplicate-email, weak-password — all 5 green; zero nested ifs; password never logged. OPS-01 satisfied.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-29T07:08:39Z
- **Completed:** 2026-04-29T07:13:35Z
- **Tasks:** 1 / 1 (TDD: RED + GREEN)
- **Files created:** 3 (test marker + test file + this SUMMARY)
- **Files modified:** 1 (`app/cli/commands/create_admin.py` — stub fully rewritten)
- **Commits:** 2 atomic (RED `f6c600e` + GREEN `62774a3`)

## Accomplishments

### `tests/unit/cli/test_create_admin.py` — 5 unit tests via CliRunner

1. **`test_help_lists_create_admin`** — invokes `create-admin --help`, asserts exit 0, asserts `--email` IS present in stdout, asserts `--password` is NOT present (locked CONTEXT §141 enforcement). Passes only when the final command exposes `--email` Option.
2. **`test_password_mismatch_exits_one`** — getpass returns `['pw-correct-12345', 'pw-different-9999']` (mismatch), asserts exit 1, asserts stderr contains `'Passwords do not match'`, asserts `mock_auth_service.register.assert_not_called()`.
3. **`test_successful_create_admin`** — getpass returns same value twice, AuthService.register returns `User(id=7, ...)`, asserts exit 0, stdout contains `'Admin user 7 created'`, `register` called once with `('admin@example.com', 'pw-correct-12345', plan_tier='pro')`.
4. **`test_duplicate_email_exits_one`** — `register.side_effect = UserAlreadyExistsError()`, asserts exit 1, stderr/stdout (case-insensitive) contains `'already exists'`.
5. **`test_weak_password_exits_one`** — `register.side_effect = WeakPasswordError('too short')`, asserts exit 1, stderr/stdout contains `'too short'`.

Fixtures (file scope, pytest module-style):
- `runner` — `CliRunner()` (no `mix_stderr` kwarg — Click 8.3 dropped it).
- `mock_auth_service` — `MagicMock` with `register.return_value = User(id=7, ...)`.
- `patched_container` — context-manager fixture that patches `app.cli.commands.create_admin._get_container` to return a Mock Container whose `auth_service()` returns `mock_auth_service`.

### `app/cli/commands/create_admin.py` — full implementation (replaces stub)

- `@app.command(name='create-admin')` with single Typer Option: `--email`/`-e` (required, no default).
- Password input: two `getpass.getpass()` calls (`'Admin password: '` + `'Confirm password: '`) — NEVER echoed, NEVER a flag.
- Mismatch path: `typer.echo('Passwords do not match.', err=True)` + `raise typer.Exit(code=1)` BEFORE touching Container/AuthService — fail-fast, no service-layer side effects.
- Container resolution via `_get_container()` (DRY — plan-01 helper, not direct `Container()` instantiation).
- Service call: `auth_service.register(email, password, plan_tier='pro')` — admin always gets pro tier per OPS-01.
- Two `except` blocks (specific-first):
  - `except UserAlreadyExistsError`: idempotent exit-1 with `'Admin user already exists. No changes made.'` + `logger.warning('CLI create-admin idempotent re-run id_hint=existing')` (no email in log).
  - `except ValidationError`: catches `WeakPasswordError` + any other future `ValidationError` subclass; emits `f'Password rejected: {exc.user_message}'` to stderr.
- Success path: stdout `f'Admin user {user.id} created with email {user.email}'` + `logger.info('CLI create-admin success id=%s', user.id)` (id only, never email/password).

### Verifier-Enforced Gate Results

| Gate | Expected | Actual | Pass |
|------|----------|--------|------|
| `pytest tests/unit/cli/test_create_admin.py -q` | 5 passed | 5 passed | yes |
| `python -m app.cli --help` lists `create-admin` | match | match (Commands table shows `create-admin` + `backfill-tasks`) | yes |
| `python -m app.cli create-admin --help` shows `--email` | match | match (`* --email -e TEXT  Admin email address. [required]`) | yes |
| `python -m app.cli create-admin --help` does NOT show `--password` | absent | absent | yes |
| `grep -c "getpass.getpass" app/cli/commands/create_admin.py` ≥ 2 | ≥ 2 | 4 (1 import + 2 calls + 1 docstring reference) | yes |
| `grep -cE "password.*=.*typer\\." app/cli/commands/create_admin.py` == 0 | 0 | 0 | yes |
| `grep -cE "^\\s+if .*\\bif\\b" app/cli/commands/create_admin.py` == 0 | 0 | 0 | yes |
| `grep -cE "logger\\.(info|debug|warning|error).*password" app/cli/commands/create_admin.py` == 0 | 0 | 0 | yes |
| `grep -c "auth_service.register" app/cli/commands/create_admin.py` ≥ 1 | ≥ 1 | 1 | yes |
| `grep -c 'plan_tier="pro"' app/cli/commands/create_admin.py` == 1 | 1 | 1 | yes |
| TDD gate sequence in `git log` | `test(...)` then `feat(...)` | `test(12-02): RED ... f6c600e` → `feat(12-02): GREEN ... 62774a3` | yes |
| `pytest tests/unit/cli/ tests/unit/services/auth/ -q` regressions | 0 | 0 (28/28 pass) | yes |

## Task Commits

1. **RED — failing tests** — `f6c600e` (`test(12-02)`)
   - 5 tests, 130 lines (`tests/unit/cli/test_create_admin.py`)
   - Test package marker (`tests/unit/cli/__init__.py`)
   - At RED: 1 failed (`--email` missing in stub) + 4 errors (`_get_container` not yet imported in stub) = 5/5 failing as required by TDD.
2. **GREEN — implementation** — `62774a3` (`feat(12-02)`)
   - Replaces stub `app/cli/commands/create_admin.py` with full ~70-line implementation.
   - 5/5 tests pass on `pytest tests/unit/cli/test_create_admin.py -q`.

## Files Created/Modified

### Created (3 files)

- `tests/unit/cli/__init__.py` — package marker (1-line docstring).
- `tests/unit/cli/test_create_admin.py` — 5 unit tests, 130 lines.
- `.planning/phases/12-admin-cli-task-backfill/12-02-SUMMARY.md` — this file.

### Modified (1 file)

- `app/cli/commands/create_admin.py` — stub (24 lines: `typer.echo("create-admin: not implemented yet (plan 12-02).")` + `raise typer.Exit(code=1)`) replaced with full implementation (72 lines: getpass twice + AuthService.register + UserAlreadyExistsError/ValidationError handling).

## Decisions Made

See frontmatter `key-decisions` for the full set. Highlights:

- **Catch `ValidationError` base, not `WeakPasswordError` directly:** open/closed — future ValidationError subclasses (EmailFormatError, etc.) flow through the same exit-1 path without code changes.
- **Specific-first except ordering:** `UserAlreadyExistsError` IS-A `ValidationError`, so the duplicate-email catch precedes the generic one — otherwise duplicate-email would render with the wrong message.
- **Tightened RED help-test assertion:** `'--email' in stdout` (not `'create-admin' in stdout`) — the plan-01 stub registered `@app.command(name='create-admin')`, so the original test would have passed at RED time.
- **`CliRunner()` without `mix_stderr`:** Click 8.3.0 dropped the kwarg; stderr is separated by default in 8.2+.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] `CliRunner(mix_stderr=False)` raised `TypeError` on Click 8.3.0**

- **Found during:** RED phase, first pytest run.
- **Issue:** Plan body line 178 used `CliRunner(mix_stderr=False)`. Click 8.3.0 (installed; verified via `python -c "import click; click.__version__"` → `8.3.0`) removed this kwarg. In Click 8.2+, `result.stderr` and `result.stdout` are independent by default; `mix_stderr` is no longer a parameter.
- **Fix:** `CliRunner()` (no kwargs) with inline comment documenting the version constraint. Tests still independently access `result.stderr` and `result.stdout` as required.
- **Files modified:** `tests/unit/cli/test_create_admin.py` (1-line fixture change).
- **Verification:** All 5 tests pass at GREEN.
- **Committed in:** `f6c600e` (RED commit) — fix landed before any test was run, so the fix is part of RED, not a separate Rule-3 commit.

**2. [Rule 1 — Test Tightening] RED help-test would have passed trivially against the plan-01 stub**

- **Found during:** RED phase, first full pytest run (`test_help_lists_create_admin` PASSED at RED).
- **Issue:** Plan body line 207 had `assert "create-admin" in result.stdout or "Email" in result.stdout`. The plan-01 stub already registered `@app.command(name="create-admin")`, so `--help` output included `'Usage: whisperx-cli create-admin [OPTIONS]'`, which makes `'create-admin' in stdout` trivially true. The test passed at RED, violating the TDD requirement that all tests fail before GREEN.
- **Fix:** Tightened assertion to `assert "--email" in result.stdout` — the stub had no options, so `--email` is genuinely absent at RED, which makes the test fail as required. The negative invariant `assert "--password" not in result.stdout` is unchanged (already correct for both stub and final).
- **Files modified:** `tests/unit/cli/test_create_admin.py` line 56.
- **Verification:** RED rerun: 1 failed + 4 errors = 5/5 failing. GREEN: all 5 pass.
- **Committed in:** `f6c600e` (RED commit) — fix landed before the RED commit was created, so it's part of the RED test suite as committed.

---

**Total deviations:** 2 auto-fixed (Rule 3 — Blocking dependency-version drift; Rule 1 — Test tightening).
**Impact on plan:** Both fixes preserve plan intent. Rule 3 is a downstream-version issue (Click 8.3 dropped a kwarg the plan body relied on); Rule 1 is a TDD-discipline correction (the stub from plan 12-01 unintentionally let one of the RED tests pass — the assertion needed to be specific to the final-state behavior, not to a substring that's already in the stub). Zero scope creep; both fixes landed in the RED commit, not as separate auto-fix commits.

## Issues Encountered

- **Pre-existing dirty working tree at plan start (carried from earlier phases):** `M README.md`, `M app/docs/db_schema.md`, `M app/docs/openapi.json`, `M app/docs/openapi.yaml`, `M app/main.py`, `M frontend/src/components/upload/FileQueueItem.tsx`, untracked `.claude/`, `app/core/auth.py`, `models/`. None touched by this plan; all out of scope per executor scope-boundary rule.
- **Logging at import-time:** `app.core.logging` runs `logging.config.dictConfig(...)` and emits two INFO lines (`Environment: production`, `Log level: INFO`) on every CLI invocation, including `python -m app.cli create-admin --help`. Cosmetic only — does NOT affect Typer help-text rendering or test assertions (`runner.invoke` captures stdout only). Documented in 12-01 SUMMARY as deferred (out-of-scope `--quiet` flag).
- **CRLF warnings on git add (Windows):** `LF will be replaced by CRLF the next time Git touches it` for the new test files. Cosmetic Windows-line-ending warning; does not affect CI / Linux runs.

## User Setup Required

None. All deps were already installed in `.venv` from plan 12-01 (`typer[all]>=0.12.0`).

## Next Phase Readiness

Wave 2 plan **12-03 backfill-tasks** is now unblocked (was already parallel-safe with 12-02; this plan's completion confirms the `_resolve_admin` helper has a real admin row to find when invoked end-to-end in plan 12-04 integration test).

Wave 3 plan **12-04 integration test + 0003 migration** can now use `runner.invoke(app, ['create-admin', '--email', 'admin@example.com'])` programmatically against a tmp SQLite DB — the patched-`_get_container` test seam established here is the same pattern the integration test will use to inject a Container bound to the integration DB.

OPS-01 (admin bootstrap CLI) is fully satisfied:
- `python -m app.cli create-admin --email <e>` is a registered Typer subcommand visible in `--help`.
- Password is read ONLY via `getpass.getpass()` (twice for confirmation) — never as a flag, never from argv, never echoed.
- Successful run creates a `users` row with `plan_tier='pro'` and an Argon2id PHC hash (delegated to AuthService.register; the CLI contains no hash logic).
- Re-running with an existing email exits 1 with a non-enumerating message (idempotent).
- Password is never logged at any level.

## TDD Gate Compliance

- [x] RED commit (`test(12-02): RED — create-admin Typer command tests`) — `f6c600e`
- [x] GREEN commit (`feat(12-02): GREEN — create-admin command (OPS-01)`) — `62774a3`, immediately after RED
- [x] No REFACTOR commit needed (implementation is already minimal: 72 lines, zero duplication, single SRP responsibility)

## Self-Check: PASSED

Verified after SUMMARY write:

- `tests/unit/cli/__init__.py` — FOUND
- `tests/unit/cli/test_create_admin.py` — FOUND (130 lines, 5 tests)
- `app/cli/commands/create_admin.py` — FOUND (72 lines, full implementation, no stub markers)
- Commit `f6c600e` (RED) — FOUND in `git log --oneline`
- Commit `62774a3` (GREEN) — FOUND in `git log --oneline`
- `pytest tests/unit/cli/test_create_admin.py -v` — 5/5 passed
- `pytest tests/unit/cli/ tests/unit/services/auth/ -q` — 28/28 passed (no regressions)
- `python -m app.cli create-admin --help` — exits 0 with `--email` Option, no `--password` flag

---
*Phase: 12-admin-cli-task-backfill*
*Completed: 2026-04-29*
