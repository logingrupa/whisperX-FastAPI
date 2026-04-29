# Phase 10: Alembic Baseline + Auth Schema - Context

**Gathered:** 2026-04-29
**Status:** Ready for planning
**Mode:** Auto-generated (infrastructure phase — discuss skipped)

<domain>
## Phase Boundary

Schema foundation. Alembic owns migrations, auth/billing/rate-limit tables exist, `tasks.user_id` exists nullable. **Zero observable behavior change** — backend boots and serves traffic identically before and after this phase.

In scope:
- Introduce Alembic; remove `Base.metadata.create_all()` from `app/main.py:48`
- Baseline migration capturing the current `tasks` table verbatim
- Schema migration adding: `users`, `api_keys`, `subscriptions`, `usage_events`, `rate_limit_buckets`, `device_fingerprints`
- `tasks.user_id INTEGER NULL` with named FK constraint to `users.id`
- SQLite `PRAGMA foreign_keys = ON` enforced on every connection (SQLAlchemy event listener)
- Every datetime column declares `DateTime(timezone=True)`
- `Subscription.plan_tier` enum CHECK constraint
- `usage_events.idempotency_key` UNIQUE NOT NULL

Out of scope (explicit deferrals):
- Backfilling `tasks.user_id` (Phase 12)
- NOT NULL constraint on `tasks.user_id` (Phase 12, after backfill)
- Any HTTP route, middleware, or service touching the new tables (Phase 11+)
- Repository implementations for the new entities (Phase 11+)

</domain>

<decisions>
## Implementation Decisions

### Schema (locked from STATE.md / REQUIREMENTS.md)

- **users**: `id INTEGER PK`, `email TEXT UNIQUE NOT NULL`, `password_hash TEXT NOT NULL`, `plan_tier TEXT CHECK(plan_tier IN ('free','trial','pro','team')) DEFAULT 'trial'`, `stripe_customer_id TEXT UNIQUE NULL`, `token_version INTEGER NOT NULL DEFAULT 0`, `trial_started_at DateTime(tz=True) NULL`, `created_at DateTime(tz=True) NOT NULL`, `updated_at DateTime(tz=True) NOT NULL`
- **api_keys**: `id INTEGER PK`, `user_id INTEGER FK→users.id ON DELETE CASCADE NOT NULL`, `name TEXT NOT NULL`, `prefix CHAR(8) NOT NULL`, `hash CHAR(64) NOT NULL` (sha256 hex), `scopes TEXT DEFAULT 'transcribe'`, `created_at DateTime(tz=True) NOT NULL`, `last_used_at DateTime(tz=True) NULL`, `revoked_at DateTime(tz=True) NULL` — soft delete; index `idx_api_keys_prefix` on `(prefix)` for O(log n) lookup
- **subscriptions**: `id INTEGER PK`, `user_id INTEGER FK→users.id ON DELETE CASCADE NOT NULL`, `stripe_subscription_id TEXT UNIQUE NULL`, `plan TEXT NULL`, `status TEXT NULL`, `current_period_start DateTime(tz=True) NULL`, `current_period_end DateTime(tz=True) NULL`, `cancelled_at DateTime(tz=True) NULL`, `created_at`, `updated_at`
- **usage_events**: `id INTEGER PK`, `user_id INTEGER FK→users.id ON DELETE CASCADE NOT NULL`, `task_id INTEGER FK→tasks.id NULL`, `gpu_seconds REAL NULL`, `file_seconds REAL NULL`, `model TEXT NULL`, `idempotency_key TEXT UNIQUE NOT NULL`, `created_at DateTime(tz=True) NOT NULL`
- **rate_limit_buckets**: `id INTEGER PK`, `bucket_key TEXT UNIQUE NOT NULL` (e.g. `user:42:hour`, `ip:10.0.0.0/24:register:hour`), `tokens INTEGER NOT NULL`, `last_refill DateTime(tz=True) NOT NULL`
- **device_fingerprints**: `id INTEGER PK`, `user_id INTEGER FK→users.id ON DELETE CASCADE NOT NULL`, `cookie_hash CHAR(64) NOT NULL`, `ua_hash CHAR(64) NOT NULL`, `ip_subnet TEXT NOT NULL`, `device_id TEXT NOT NULL`, `created_at DateTime(tz=True) NOT NULL`; unique `(user_id, cookie_hash, ua_hash, ip_subnet, device_id)`
- **tasks.user_id**: `INTEGER NULL FK→users.id ON DELETE SET NULL` with named constraint `fk_tasks_user_id` — nullable in this phase, NOT NULL after Phase 12 backfill

### Migration Strategy

- Tooling: `alembic` (already standard with SQLAlchemy ecosystem; not yet in pyproject)
- Layout: `alembic/` at repo root; `alembic/versions/` for revisions
- Two revisions in this phase:
  - `0001_baseline.py` — empty `upgrade()` that just stamps; captures pre-existing `tasks` shape
  - `0002_auth_schema.py` — adds the six new tables, alters `tasks` to add nullable `user_id` FK
- Operator runbook: backup `records.db` → `alembic stamp 0001_baseline` → `alembic upgrade head`
- Drop `Base.metadata.create_all(bind=engine)` from `app/main.py` (success criterion 3)

### Connection Hygiene

- SQLAlchemy `event.listens_for(Engine, "connect")` listener that runs `cursor.execute("PRAGMA foreign_keys = ON")` on every new connection
- Listener lives in `app/infrastructure/database/connection.py` next to `engine`
- Verified by: `with engine.connect() as conn: assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1`

### DateTime Discipline

- Every new column uses `DateTime(timezone=True)` — explicit
- Default value: `default=lambda: datetime.now(timezone.utc)` for `created_at`, `onupdate=...` for `updated_at`
- Existing `tasks.created_at`/`updated_at` migrated to `DateTime(timezone=True)` in `0002_auth_schema` (in-place ALTER)

### Code Quality (locked from user)

- DRY — shared schema helpers (e.g. `created_at_column()`, `updated_at_column()` factory functions in models.py) reused across all six new tables
- SRP — one module per ORM model file is overkill for this size; keep all six new models in `app/infrastructure/database/models.py` but split into clearly-labeled `# region <Table>` blocks; if file exceeds ~400 lines, split per table
- /tiger-style — assert invariants at module load (e.g. `assert User.__tablename__ == "users"`); no silent defaults; fail loudly on `PRAGMA foreign_keys = OFF`
- No spaghetti — early returns in connection listener; no nested `if`s in migration ops; flat `op.create_table(...)` calls
- Self-explanatory names — `users`, `api_keys`, `idempotency_key`, `token_version`, `bucket_key` — no abbreviations

### Claude's Discretion

- Exact column-comment text on new tables — match existing `comment="..."` style from `tasks` model
- Internal naming of FK constraints (`fk_<table>_<col>` pattern, but Alembic's defaults are acceptable)
- Whether to use `sa.Enum` Python class or raw `CHECK` constraint for `plan_tier` — pick raw `CHECK` to match the success-criterion phrasing and avoid Alembic enum-rename pain on SQLite
- Whether to introduce `app/db/` directory or extend `app/infrastructure/database/` — keep within `app/infrastructure/database/`; introduce `app/infrastructure/database/migrations/` only if Alembic conventions force it (they don't — `alembic/` at repo root is conventional)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets

- `app/infrastructure/database/models.py` — `Base` (DeclarativeBase) and `Task` model — extend here for new ORM models
- `app/infrastructure/database/connection.py` — `engine`, `SessionLocal`, `get_db_session()` — extend with `PRAGMA` listener; engine creation already passes `connect_args={"check_same_thread": False}`
- `app/core/config.py` — `Config.DB_URL` — Alembic's `env.py` pulls connection URL from here for consistency
- `app/main.py:48` — `Base.metadata.create_all(bind=engine)` — to be removed
- `app/main.py:79` — `generate_db_schema(Base.metadata.tables.values())` — should still work after migration since `Base.metadata` reflects all models

### Established Patterns

- Snake_case tables, PascalCase ORM classes (e.g. `Task` → `tasks`)
- Pydantic Settings for config (env-var driven via `__` delimiter)
- Domain ↔ ORM mappers in `app/infrastructure/database/mappers/`
- `Mapped[T]` + `mapped_column(...)` SQLAlchemy 2.x style with `comment=...` on every column
- `dependency-injector` Container in `app/core/container.py` for DI

### Integration Points

- `app/main.py` — drop `create_all()` line (criterion 3)
- `pyproject.toml` — add `alembic` to dependencies
- `alembic.ini` — at repo root
- `alembic/env.py` — wire to `Config.DB_URL` and `Base.metadata`
- `app/infrastructure/database/__init__.py` — re-exports `Base`, `engine` (used by `app/main.py`); will need to re-export new models

</code_context>

<specifics>
## Specific Ideas

- Two-revision split (baseline → auth_schema) is required so existing `records.db` can be `alembic stamp 0001_baseline`'d without touching data, then `alembic upgrade head` adds new tables idempotently
- `alembic stamp head` is the documented operator step in the migration runbook (Phase 17 OPS-03)
- `PRAGMA foreign_keys` listener must be active **before any session opens** — register at `connection.py` import time
- Migration ops must be SQLite-safe: use `op.batch_alter_table()` for `tasks` ALTER (SQLite's limited ALTER TABLE)

</specifics>

<deferred>
## Deferred Ideas

- Repository implementations for new entities → Phase 11
- Repository-level scope filtering (`set_user_scope`) → Phase 13
- Backfill `tasks.user_id` and apply NOT NULL → Phase 12
- Operator runbook documentation → Phase 17

</deferred>
