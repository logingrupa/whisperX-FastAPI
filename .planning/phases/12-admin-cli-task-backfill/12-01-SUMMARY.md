---
phase: 12-admin-cli-task-backfill
plan: 01
subsystem: cli
tags: [cli, scaffold, typer, di, auth-service]

# Dependency graph
requires:
  - phase: 11-auth-core-modules-services-di/11-04
    provides: Container().auth_service() Factory + Container().user_repository() Factory + AuthService.register/login + UserAlreadyExistsError
  - phase: 11-auth-core-modules-services-di/11-03
    provides: SQLAlchemyUserRepository.get_by_email + User domain entity (with plan_tier field)
  - phase: 10-alembic-and-auth-schema/10-03
    provides: ck_users_plan_tier CHECK constraint accepting free/trial/pro/team
provides:
  - app/cli/__init__.py — Typer app singleton (name=whisperx-cli, no_args_is_help=True, rich_markup_mode="rich")
  - app/cli/__main__.py — `python -m app.cli` entry point
  - app/cli/_helpers.py — `_get_container() -> Container` + `_resolve_admin(email, *, container=None) -> User` (DRY shared helpers, tiger-style typer.Exit on miss)
  - app/cli/commands/{create_admin,backfill_tasks}.py — placeholder @app.command() stubs (plans 12-02 + 12-03 fully rewrite)
  - AuthService.register accepts keyword-only `plan_tier: str = "trial"` — allows admin bootstrap without bypassing service layer (SRP)
  - 1 new AuthService unit test (6 total in test_auth_service.py: 5 existing + 1 new)
  - typer[all]>=0.12.0 added to pyproject.toml runtime dependencies
affects:
  - 12-02 create-admin command — imports `from app.cli import app` to register `@app.command(name="create-admin")` and calls `auth_service.register(email, password, plan_tier="pro")`
  - 12-03 backfill-tasks command — imports `from app.cli import app` + `from app.cli._helpers import _resolve_admin, _get_container`
  - 12-04 0003 migration + integration test — invokes `python -m app.cli create-admin` and `python -m app.cli backfill-tasks` via Typer CliRunner

# Tech tracking
tech-stack:
  added:
    - "typer[all]>=0.12.0 (CLI framework — typer 0.20.0 already pinned in .venv; pyproject declared)"
  patterns:
    - "Typer app singleton lives in `app/cli/__init__.py`; subcommand modules use `from app.cli import app` + `@app.command()` decorator (side-effect registration via bottom-of-package imports in __init__.py)"
    - "DRY helper module `app/cli/_helpers.py` shared across all CLI commands — single source of truth for Container() lifecycle and admin email resolution"
    - "Tiger-style fail-loud admin lookup: `_resolve_admin` raises `typer.Exit(code=1)` with stderr message on miss; never returns None silently"
    - "AuthService.register with keyword-only `plan_tier` (backward-compatible — existing 5 callers pass-through to default 'trial')"
    - "CLI commands MUST register at least one @app.command() per Typer module — Typer 0.20+ raises 'RuntimeError: Could not get a command for this Typer instance' when --help is invoked on an empty registry"

key-files:
  created:
    - app/cli/__init__.py — Typer app singleton + side-effect subcommand imports
    - app/cli/__main__.py — `python -m app.cli` entry (`from app.cli import app; app()`)
    - app/cli/_helpers.py — `_get_container()` + `_resolve_admin(email, *, container=None)`
    - app/cli/commands/__init__.py — package marker
    - app/cli/commands/create_admin.py — placeholder @app.command() stub (plan 12-02 rewrites)
    - app/cli/commands/backfill_tasks.py — placeholder @app.command() stub (plan 12-03 rewrites)
    - .planning/phases/12-admin-cli-task-backfill/12-01-SUMMARY.md
  modified:
    - pyproject.toml — added `"typer[all]>=0.12.0"` to runtime dependencies (after pyjwt line)
    - app/services/auth/auth_service.py — `register()` adds keyword-only `plan_tier: str = "trial"` parameter; passes through to `User(plan_tier=plan_tier)`; logs `id=N plan_tier=X`
    - tests/unit/services/auth/test_auth_service.py — added `test_register_with_pro_plan_tier_persists_pro_user` (6th test)

key-decisions:
  - "Stub command modules register placeholder @app.command()s rather than being docstring-only (deviation Rule 3): plan body line 173 said 'contains only a docstring' but Typer 0.20+ refuses to render --help for an instance with zero registered commands ('RuntimeError: Could not get a command for this Typer instance'). Plans 12-02 and 12-03 fully rewrite these modules anyway, so the placeholder is throwaway. Documented in module docstrings."
  - "AuthService.register `plan_tier` is keyword-only (`*` separator before it): preserves backward compat — existing 5 callers `auth_service.register(email, pw)` keep working with no signature change. Plan 12-02 will pass `plan_tier='pro'` explicitly for admin bootstrap. Default 'trial' matches the schema CHECK constraint default."
  - "New unit test fixture names: kept `mock_user_repo` / `mock_password_service` / `mock_token_service` to match the existing test file's fixture names (plan body line 313 said 'use whatever the file already defines — do NOT rename them'). Plan body line 290-307 used `mock_user_repository` but the file defines `mock_user_repo` — followed the file as instructed."
  - "Logging: `User registered id=%s plan_tier=%s` — plan_tier is non-PII metadata (free/trial/pro/team), safe to log per AUTH-09 grep gate (no email/password/secret in log lines)."
  - "_resolve_admin signature `(email: str, *, container: Container | None = None)`: keyword-only `container` is the test seam (plan 12-02 + 12-03 + 12-04 integration test inject a mock Container). Default to `_get_container()` when omitted — keeps real-world callers tidy."
  - "_resolve_admin emits `email_hint=<redacted>` (not the raw email) on the warning log line to keep the RedactingFilter contract from Phase 11 — even though the typer.echo to stderr does include the email (operator visibility on CLI is acceptable; logs go to disk)."

patterns-established:
  - "Pattern: CLI package layout — `app/cli/{__init__.py, __main__.py, _helpers.py, commands/{__init__.py, *.py}}`. __init__.py owns the Typer app; __main__.py is one-liner entry; _helpers.py is the DRY surface; commands/ holds @app.command()-decorated subcommand modules."
  - "Pattern: Side-effect subcommand registration — bottom-of-`__init__.py` imports of `app.cli.commands.{create_admin, backfill_tasks}` modules. Each command module pulls `from app.cli import app` and calls `@app.command(name=...)`. Decorator side-effect populates the registry."
  - "Pattern: Service-level keyword-only extension — when adding a new optional service parameter, place it after `*` separator so positional-style call sites stay green. Documented in AuthService.register docstring."

requirements-completed: [OPS-01, OPS-02]

# Metrics
duration: 6 min
completed: 2026-04-29
---

# Phase 12 Plan 01: Typer CLI scaffold + DRY helpers + AuthService.register plan_tier kwarg Summary

**Wave 1 foundation: `app/cli/` package with Typer singleton and DRY `_resolve_admin`/`_get_container` helpers, `AuthService.register(plan_tier=)` keyword-only kwarg, typer dep declared. `python -m app.cli --help` exits 0 listing both placeholder subcommands; 6/6 AuthService unit tests green; zero nested-ifs across `app/cli/`.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-04-29T06:58:04Z
- **Completed:** 2026-04-29T07:04:32Z
- **Tasks:** 1 / 1
- **Files created:** 7 (6 source files + this SUMMARY)
- **Files modified:** 2 (pyproject.toml + app/services/auth/auth_service.py + tests/unit/services/auth/test_auth_service.py — counted as 3 source modifies)
- **Commits:** 1 (atomic feat commit `df1e402`)

## Accomplishments

### `app/cli/` package created (5 source files + 1 stub package marker)

- `app/cli/__init__.py` — Typer singleton with locked config:
  - `name="whisperx-cli"` (verifier asserts via `app.info.name`)
  - `help="WhisperX admin CLI — bootstrap admin users and run database backfills."` (verifier greps `"WhisperX admin CLI"` in `--help` stdout)
  - `add_completion=False` (no shell completion clutter)
  - `no_args_is_help=True` (bare `python -m app.cli` shows help, not error)
  - `rich_markup_mode="rich"` (CONTEXT D-01 Claude's Discretion: rich help screens enabled)
  - Bottom-of-file side-effect imports (`E402, F401`) of `app.cli.commands.{create_admin, backfill_tasks}` → registry populated
- `app/cli/__main__.py` — 4-line entry (`from app.cli import app; if __name__ == "__main__": app()`)
- `app/cli/_helpers.py`:
  - `_get_container() -> Container` — fresh Container per CLI invocation (short-lived process; one-per-invocation lifecycle is the simplest correct model)
  - `_resolve_admin(email: str, *, container: Container | None = None) -> User` — repository lookup + tiger-style typer.Exit(1) on miss (CONTEXT §92)
- `app/cli/commands/__init__.py` — package marker (docstring only)
- `app/cli/commands/create_admin.py` — placeholder `@app.command(name="create-admin")` stub (plan 12-02 rewrites)
- `app/cli/commands/backfill_tasks.py` — placeholder `@app.command(name="backfill-tasks")` stub (plan 12-03 rewrites)

### `pyproject.toml` updated

- Added `"typer[all]>=0.12.0"` to `[project] dependencies` after the `pyjwt>=2.8.0` line — typer 0.20.0 was already installed in `.venv` (verified via `pip show typer`); declaring it in pyproject ensures fresh installs / Docker image builds / CI envs pull it in.

### `app/services/auth/auth_service.py` extended

- `register()` signature changed from `(email, plain_password)` to `(email, plain_password, *, plan_tier='trial')`:
  - Keyword-only `plan_tier` after `*` separator → all 5 existing callers in unit tests + 11-04 service code keep working unchanged.
  - `User(id=None, email=email, password_hash=hashed, plan_tier=plan_tier)` — propagates the tier into the domain entity.
  - Logging upgraded to `User registered id=%s plan_tier=%s` — plan_tier is non-PII metadata (one of free/trial/pro/team), safe to log per AUTH-09 grep gates.
- Docstring extended with full Args / Raises spec.

### `tests/unit/services/auth/test_auth_service.py` extended

- 1 new test `test_register_with_pro_plan_tier_persists_pro_user`:
  - Asserts `user.plan_tier == "pro"` on the returned User.
  - Asserts the User passed to `mock_user_repo.add(...)` carries `plan_tier='pro'` (not the default 'trial') — proves the kwarg flows all the way to the repository call.
- Used existing fixture names (`mock_user_repo`, `mock_password_service`, `mock_token_service`) per plan body line 313 ("if the fixture names differ, use whatever the file already defines — do NOT rename them"). Plan body line 290-307 example used `mock_user_repository` but the existing file defines `mock_user_repo`.
- Test count: 5 existing → 6 total. All 6 pass on `pytest tests/unit/services/auth/test_auth_service.py -q`.

## Task Commits

1. **Task 1: Add typer dep + scaffold app/cli/ package + shared helpers** — `df1e402` (`feat(12-01)`)

## Files Created/Modified

### Created (6 source files)

- `app/cli/__init__.py` — Typer app singleton + side-effect subcommand imports
- `app/cli/__main__.py` — `python -m app.cli` entry
- `app/cli/_helpers.py` — `_get_container()` + `_resolve_admin(email, *, container=None)`
- `app/cli/commands/__init__.py` — package marker
- `app/cli/commands/create_admin.py` — stub @app.command (plan 12-02 rewrites)
- `app/cli/commands/backfill_tasks.py` — stub @app.command (plan 12-03 rewrites)

### Modified (3 source files)

- `pyproject.toml` — `+ "typer[all]>=0.12.0"` line added under `[project] dependencies`
- `app/services/auth/auth_service.py` — `register()` signature `+ *, plan_tier: str = "trial"`; User construction passes plan_tier; log format adds `plan_tier=%s`
- `tests/unit/services/auth/test_auth_service.py` — `+ test_register_with_pro_plan_tier_persists_pro_user`

## Decisions Made

- **Placeholder @app.command() stubs over docstring-only stubs:** Plan body line 173 said the stubs should contain only a docstring. Typer 0.20+ raises `RuntimeError: Could not get a command for this Typer instance` when `--help` is invoked on a Typer instance with zero registered commands. Since the plan's must-have truth #1 explicitly requires `python -m app.cli --help` to exit 0, the docstring-only stub would have failed that gate. The stubs now register placeholder `@app.command()`s that print "not implemented yet (plan 12-02/03)" and exit 1. Plans 12-02 and 12-03 will fully rewrite these modules anyway, so this is throwaway.
- **Test fixture names match existing file:** Plan body line 290-307 example used `mock_user_repository`, `mock_password_service`, `mock_token_service` — but the existing test file defines `mock_user_repo` (without `_repository` suffix). Plan body line 313 explicitly said "use whatever the file already defines — do NOT rename them". Followed the file.
- **`plan_tier` is keyword-only:** `register(email, plain_password, *, plan_tier="trial")` — keeps positional-style call sites in 11-04 unit tests + future routes green; admin bootstrap path can pass `plan_tier="pro"` explicitly.
- **`_resolve_admin` test seam:** added `*, container: Container | None = None` parameter so plans 12-02/03/04 can inject a mock Container. Default to `_get_container()` when omitted — production CLI calls stay tidy.
- **Logging hygiene:** `_resolve_admin` warning log uses `email_hint=<redacted>` rather than the raw email (RedactingFilter contract from Phase 11). The user-facing typer.echo to stderr does include the email — operator visibility on a TTY is fine; the persisted log line stays clean.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Stub command modules need a registered @app.command() for Typer --help to render**

- **Found during:** Task 1 verification (running `python -m app.cli --help`)
- **Issue:** Plan body line 173 instructed `app/cli/commands/{create_admin,backfill_tasks}.py` to contain only a docstring. With both modules being docstring-only and `app/cli/__init__.py` doing side-effect imports of them, the Typer app instance ends up with zero registered commands. Typer 0.20+ raises `RuntimeError: Could not get a command for this Typer instance` on `--help` invocation in this state. This breaks the plan's locked must-have truth #1 ("`python -m app.cli --help` prints a Typer help screen exit 0") and acceptance criterion ("`python -m app.cli --help` exit 0 and stdout contains the substring 'WhisperX admin CLI'").
- **Fix:** Each stub command module now registers a placeholder `@app.command(name="...")` that prints `"<cmd>: not implemented yet (plan 12-XX)."` to stderr and `raise typer.Exit(code=1)`. Module docstring documents the placeholder rationale and points at the plan that will fully rewrite the module. Plans 12-02 + 12-03 will replace the stub function bodies with real `getpass`/`AuthService.register`/repository wiring; the `from app.cli import app` import + `@app.command(name=...)` decorator pattern is exactly what those plans need anyway.
- **Files modified:** `app/cli/commands/create_admin.py`, `app/cli/commands/backfill_tasks.py` (both went from 1-line docstring to ~22 lines with placeholder command). Both still in scope for plan 12-01's `<files_modified>` frontmatter list.
- **Verification:** `python -m app.cli --help` now exits 0 and prints both subcommands in the Commands table. Plan acceptance criterion satisfied.
- **Committed in:** `df1e402` (Task 1 commit, single atomic).

---

**Total deviations:** 1 auto-fixed (Rule 3 - Blocking)
**Impact on plan:** Necessary for the plan's own locked must-have truth #1 and acceptance criterion. The placeholder bodies are throwaway — plans 12-02 and 12-03 explicitly rewrite these modules. Zero scope creep; the alternative (leaving --help broken at end of plan 12-01) would have failed the plan itself.

## Issues Encountered

- **Pre-existing dirty working tree at plan start:** `M README.md`, `M app/docs/db_schema.md`, `M app/docs/openapi.json`, `M app/docs/openapi.yaml`, `M app/main.py`, `M frontend/src/components/upload/FileQueueItem.tsx`, `M .planning/STATE.md`, untracked `.claude/`, `app/core/auth.py`, `models/`. None touched by this plan; all carried forward from earlier phases. Out of scope per the executor scope-boundary rule.
- **Pre-existing pytest failures** (3 in `tests/unit/services/test_audio_processing_service.py`; 3 collection errors in `tests/unit/{domain/entities,infrastructure/database/{mappers,repositories}}/test_*.py` due to missing `factory_boy` dev dep). Both documented in 11-01 + 11-04 SUMMARYs as out-of-scope. This plan introduces zero new failures.
- **Typer logging during import:** `app/cli/_helpers.py` imports `app.core.logging.logger`, which executes `logging.config.dictConfig(...)` at import time and emits two INFO log lines (`Environment: production`, `Log level: INFO`) on every CLI invocation. Acceptable for now — Phase 12 is operator-facing infra and the noise is tolerable. Future plan can add a `--quiet` flag if desired (deferred — out of scope).

## Verifier-Enforced Gate Results

| Gate | Expected | Actual | Pass |
|------|----------|--------|------|
| `pip show typer` | exit 0 (dep installed) | typer 0.20.0 found in .venv | yes |
| `python -m app.cli --help` exit 0 + contains "WhisperX admin CLI" | exit 0 + match | exit 0 + match | yes |
| `grep -c "^    \"typer" pyproject.toml` | >= 1 | 1 | yes |
| `python -c "from app.cli._helpers import _resolve_admin, _get_container"` | exit 0 | exit 0 | yes |
| `python -c "...AuthService.register.parameters['plan_tier'].kind == KEYWORD_ONLY ...default == 'trial'"` | exit 0 | exit 0 | yes |
| `pytest tests/unit/services/auth/test_auth_service.py -q` | 6 passed | 6 passed | yes |
| `grep -cE "^\s+if .*\bif\b" app/cli/__init__.py app/cli/__main__.py app/cli/_helpers.py` | 0 | 0 (each file 0) | yes |
| `grep -c "from app.core.container import Container" app/cli/_helpers.py` | 1 | 1 | yes |
| `grep -c "raise typer.Exit" app/cli/_helpers.py` | >= 1 | 1 | yes |
| `pytest tests/unit -q` regressions vs baseline | 0 new | 0 new (3 audio_processing failures + 3 factory_boy collection errors are pre-existing per 11-04 SUMMARY) | yes |

## User Setup Required

None — typer is already installed in the project `.venv`. Future fresh installs (CI, Docker, new contributor) will pull it in via the new `pyproject.toml` declaration.

## Next Phase Readiness

Wave 2 (plans 12-02 + 12-03) can now proceed in parallel:

- **12-02 create-admin command:** `from app.cli import app` + `from app.cli._helpers import _resolve_admin, _get_container` work today. The stub `create_admin.py` will be fully rewritten — getpass twice for confirm, email-validator validation, length >=12 check, `auth_service.register(email, password, plan_tier="pro")`, success stdout / failure stderr. The `plan_tier='pro'` kwarg path is now backed by a passing unit test.
- **12-03 backfill-tasks command:** same imports work. The stub `backfill_tasks.py` will be fully rewritten — `--admin-email` Option, `--yes`/`-y` skip-prompt flag, `--dry-run` flag (CONTEXT D-03), `_resolve_admin(email)` lookup, single `UPDATE tasks SET user_id` transaction, post-write count verification.
- **12-04 integration test + 0003 migration:** can use Typer's `CliRunner` to invoke `python -m app.cli create-admin` and `python -m app.cli backfill-tasks` programmatically. The `_get_container()` factory is the natural test seam (inject a Container bound to the tmp SQLite DB).

No blockers. Phase 12 Wave 1 foundation is complete.

## Self-Check: PASSED

Verified after SUMMARY write:

- `app/cli/__init__.py` — FOUND
- `app/cli/__main__.py` — FOUND
- `app/cli/_helpers.py` — FOUND
- `app/cli/commands/__init__.py` — FOUND
- `app/cli/commands/create_admin.py` — FOUND
- `app/cli/commands/backfill_tasks.py` — FOUND
- `app/services/auth/auth_service.py` (modified) — FOUND with new `plan_tier` keyword-only param
- `tests/unit/services/auth/test_auth_service.py` (modified) — FOUND with 6th test
- `pyproject.toml` (modified) — FOUND with `typer[all]>=0.12.0` line
- Commit `df1e402` (Task 1 atomic feat) — FOUND in `git log`

---
*Phase: 12-admin-cli-task-backfill*
*Completed: 2026-04-29*
