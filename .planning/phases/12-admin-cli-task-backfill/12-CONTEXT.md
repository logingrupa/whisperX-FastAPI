# Phase 12: Admin CLI + Task Backfill - Context

**Gathered:** 2026-04-29
**Status:** Ready for planning
**Mode:** Auto-generated (operator infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Operator can bootstrap an admin account AND reassign all orphan `tasks.user_id IS NULL` rows so the upcoming NOT-NULL FK constraint applies cleanly. This phase prepares the database for Phase 13's `tasks.user_id NOT NULL` migration.

In scope:
- CLI entry point: `python -m app.cli` — Typer-based command dispatcher with `--help`
- `python -m app.cli create-admin --email <email>` — prompts for password via `getpass.getpass()`, hashes via `app.services.auth.PasswordService`, inserts a `users` row with `plan_tier='pro'`
- `python -m app.cli backfill-tasks --admin-email <email>` — finds all `tasks.user_id IS NULL` rows, reassigns to the named admin user, verifies `COUNT(*) WHERE user_id IS NULL == 0`
- Alembic migration `0003_tasks_user_id_not_null.py` — `op.batch_alter_table("tasks")` to alter `user_id` to NOT NULL + add `idx_tasks_user_id` index. Pre-condition: backfill must have run.
- Unit tests for the CLI commands (mocked DB)
- Integration test: end-to-end flow against a tmp DB (create admin → insert orphan tasks → run backfill → run 0003 migration → verify constraint)

Out of scope (deferred):
- HTTP `/auth/register` endpoint — Phase 13
- Login flow — Phase 13
- Admin web UI — Phase 15+
- Stripe seeding — Phase 13

</domain>

<decisions>
## Implementation Decisions

### CLI Framework

- **Typer** (already common in FastAPI ecosystem; cleanly maps Python functions to subcommands)
- Add `typer` to pyproject.toml dependencies
- Layout: `app/cli/__init__.py` (Typer app), `app/cli/__main__.py` (entry for `python -m app.cli`), `app/cli/commands/create_admin.py`, `app/cli/commands/backfill_tasks.py`
- Each command is a function decorated with `@app.command()`; arguments parsed via Typer's `typer.Option`/`typer.Argument`
- Help: `python -m app.cli --help` lists subcommands; per-command help via `python -m app.cli <cmd> --help`

### create-admin Command

- **Inputs:** `--email <email>` (required); password via `getpass.getpass(prompt="Admin password: ")` — twice for confirmation; mismatch → exit 1 with stderr message
- **Validation:**
  - Email format via `email-validator` package (already a Pydantic Settings dep) or simple regex
  - Password min length: 12 chars (locked OWASP guideline; weaker passwords rejected with `WeakPasswordError`)
  - Reject if email already exists (`UserAlreadyExistsError` raised by `AuthService.register_user` — caught and reported with generic non-enumerating message)
- **Action:** Resolve `Container().auth_service()` and call `auth_service.register_user(email, password, plan_tier='pro')`
- **Output:** stdout `Admin user <id> created with email <email>` on success; non-zero exit on failure
- **Idempotency:** Re-running with same email → exit 1 with `Admin user already exists` (no overwrite)
- **Security:** `getpass` never echoes; password not stored anywhere; cleared from memory after Argon2 hash

### backfill-tasks Command

- **Input:** `--admin-email <email>` (required)
- **Pre-conditions:**
  - Admin user exists (else exit 1 with `Admin user not found: run create-admin first`)
  - Read-only confirmation: report `N tasks have user_id IS NULL — reassign to admin <email>? [y/N]` — `--yes`/`-y` skips prompt for scripted use
- **Action:** Single `UPDATE tasks SET user_id = :admin_id WHERE user_id IS NULL` transaction
- **Verification:** Re-query `SELECT COUNT(*) FROM tasks WHERE user_id IS NULL` — must return 0; exit 1 if nonzero
- **Output:** `Reassigned N orphan tasks to admin <email> (id=<id>)`
- **Idempotency:** If 0 orphans → exit 0 with `No orphan tasks to backfill`

### 0003_tasks_user_id_not_null Migration

- **Pre-condition (documented in migration docstring):** `python -m app.cli backfill-tasks` must have run; migration verifies `SELECT COUNT(*) FROM tasks WHERE user_id IS NULL == 0` and **fails fast** with a clear error message if non-zero (using `op.get_bind().execute(...)`)
- **Operations (in order):**
  1. Verify zero orphans (raise on failure)
  2. `op.batch_alter_table("tasks") as batch_op:`
     - `batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False)`
     - `batch_op.create_index("idx_tasks_user_id", ["user_id"])`
- **Downgrade:**
  1. `op.batch_alter_table("tasks") as batch_op:`
     - `batch_op.drop_index("idx_tasks_user_id")`
     - `batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=True)`

### Tests

- Unit tests in `tests/unit/cli/`:
  - `test_create_admin.py` — mocks `getpass`, mocks `AuthService.register_user`; verifies pw mismatch, success path, duplicate-email path
  - `test_backfill_tasks.py` — mocks repos; verifies orphan count handling, missing admin handling, dry-run
- Integration test in `tests/integration/test_cli_backfill_e2e.py` — uses tmp SQLite DB, real Alembic migrations, real services; exercises full flow:
  1. `alembic upgrade head` (0001 + 0002)
  2. Insert tasks rows with `user_id IS NULL` directly
  3. Invoke create-admin via Typer test runner (mock getpass)
  4. Invoke backfill-tasks
  5. `alembic upgrade head` again (now 0003 — was added by this phase)
  6. Verify schema: `pragma_table_info("tasks")` shows user_id NOT NULL; `idx_tasks_user_id` exists

### Code Quality (locked from user)

- **DRY** — share a `_resolve_admin(email: str) -> User` helper across both commands; both commands instantiate Container() the same way
- **SRP** — CLI commands do NOT contain auth/hash logic; delegate to `AuthService` (Phase 11). Migration does NOT contain hash logic.
- **/tiger-style** — fail loudly on missing admin / orphan rows / pw mismatch; module-load asserts in CLI entry point
- **No spaghetti** — guard clauses with early `raise typer.Exit(code=1)`; no nested-if-in-if (`grep -cE "^\s+if .*\bif\b" app/cli/**/*.py` returns 0)
- **Self-explanatory names** — `create_admin`, `backfill_tasks`, `_resolve_admin`, `--admin-email`

### Claude's Discretion

- Whether to use `rich.prompt.Confirm` (already standard with Typer) for the y/N — yes, recommended
- Exact stderr message wording for non-enumerating errors
- Whether to add a `--dry-run` flag to backfill-tasks — yes, useful for production runbook
- Whether to support env var overrides (e.g. `WHISPERX_ADMIN_EMAIL`) — no, keep CLI flags only for clarity

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets

- `app/core/container.py` — `Container().auth_service()` returns AuthService (Phase 11)
- `app/services/auth/auth_service.py` — `register_user(email, password, plan_tier)` already exists
- `app/services/auth/password_service.py` — Argon2 hashing
- `app/infrastructure/database/repositories/sqlalchemy_user_repository.py` — `add(user)`, `get_by_email(email)`
- `alembic/versions/0002_auth_schema.py` — Phase 10 added `tasks.user_id` nullable; Phase 12 makes it NOT NULL
- `app/core/exceptions.py` — `UserAlreadyExistsError`, `WeakPasswordError`, `InvalidCredentialsError`

### Established Patterns

- Snake_case modules, PascalCase classes
- `Protocol`-based repos (entities are framework-free)
- Typed exceptions inheriting from DomainError/ValidationError
- Alembic batch_alter_table for SQLite
- Logging via `app.core.logging.logger` — RedactingFilter scrubs sensitive fields

### Integration Points

- `pyproject.toml` — add `typer` (with `rich` extras)
- `app/cli/__init__.py` — new package
- `app/cli/__main__.py` — entry point: `from app.cli import app; app()`
- `app/services/auth/auth_service.py` — `register_user` already supports plan_tier="pro" if AuthSettings allows it (otherwise needs minor extension)
- `alembic/versions/0003_tasks_user_id_not_null.py` — new migration

</code_context>

<specifics>
## Specific Ideas

- The `0003` migration's pre-flight orphan check is the **safety net** — even if operator forgets to run backfill, the migration refuses to alter the column (avoids data loss / FK failure on production)
- `create-admin` should idempotently exit 1 if user already exists — operator may re-run to confirm bootstrap state
- Integration test must use Typer's `CliRunner` to invoke commands programmatically (no real subprocess)
- Locked: password is read via `getpass` ONLY — never as a CLI flag (passwords as flags leak into shell history and `ps aux`)

</specifics>

<deferred>
## Deferred Ideas

- Admin web UI / dashboard — Phase 15+
- `python -m app.cli list-users` and other admin queries — v1.3
- Email verification at admin creation — v1.3 (FUTURE-04)
- Bulk import of users from CSV — out of scope
- Migration runbook documentation — Phase 17 (OPS-03)

</deferred>
