# Phase 10: Alembic Baseline + Auth Schema - Pattern Map

**Mapped:** 2026-04-29
**Files analyzed:** 10 (5 NEW, 5 MODIFY)
**Analogs found:** 7 / 10 (3 have NO analog — Alembic-specific scaffolding)

## File Classification

| File | NEW/MOD | Role | Data Flow | Closest Analog | Match Quality |
|------|---------|------|-----------|----------------|---------------|
| `alembic.ini` | NEW | config | static-config | `pyproject.toml` (root config tone only) | no-analog |
| `alembic/env.py` | NEW | config | request-response (CLI hook) | `app/infrastructure/database/connection.py` | role-match (engine wiring) |
| `alembic/script.py.mako` | NEW | template | code-gen | — | no-analog (Alembic stock template) |
| `alembic/versions/0001_baseline.py` | NEW | migration | schema-mutation | — | no-analog (empty stamp) |
| `alembic/versions/0002_auth_schema.py` | NEW | migration | schema-mutation | `app/infrastructure/database/models.py` (column shapes) | role-match (column defs replicated as `sa.Column(...)`) |
| `app/infrastructure/database/models.py` | MOD | model | ORM-CRUD | `Task` class (same file, lines 17-99) | exact |
| `app/infrastructure/database/connection.py` | MOD | infrastructure | event-driven (engine listener) | self (lines 18-21 engine block) | exact (extend in place) |
| `app/main.py` | MOD | bootstrap | startup | self (line 48) | exact (single-line removal) |
| `pyproject.toml` | MOD | config | static-config | self (lines 29-51 deps array) | exact (append to deps) |
| `tests/integration/test_alembic_migration.py` | NEW | test | integration | `tests/integration/test_task_lifecycle.py` | role-match |

---

## Pattern Assignments

### `app/infrastructure/database/models.py` (model, ORM-CRUD) — MODIFY

**Analog:** `app/infrastructure/database/models.py::Task` (same file, lines 17-99) — exact

**Module docstring + imports** (lines 1-8):
```python
"""This module defines the database models for the application."""

from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
```

**Action:** Extend imports — add `Boolean, CheckConstraint, ForeignKey, Index, UniqueConstraint, text` from `sqlalchemy`; add `relationship` from `sqlalchemy.orm`. Keep import order: stdlib → third-party → app.

**Base class pattern** (lines 11-14):
```python
class Base(DeclarativeBase):
    """Base class for all database models."""

    pass
```

**Action:** Reuse existing `Base`. All 6 new models inherit from it. Do NOT redefine.

**Class-level docstring + tablename pattern** (lines 17-34):
```python
class Task(Base):
    """
    Table to store tasks information.

    Attributes:
    - id: Unique identifier for each task (Primary Key).
    - uuid: Universally unique identifier for each task.
    ...
    """

    __tablename__ = "tasks"
```

**Action:** Each new ORM class follows this Google-style docstring template listing Attributes. PascalCase class name → snake_case `__tablename__` (User→users, ApiKey→api_keys, Subscription→subscriptions, UsageEvent→usage_events, RateLimitBucket→rate_limit_buckets, DeviceFingerprint→device_fingerprints).

**Primary key column pattern** (lines 35-40):
```python
id: Mapped[int] = mapped_column(
    Integer,
    primary_key=True,
    autoincrement=True,
    comment="Unique identifier for each task (Primary Key)",
)
```

**Action:** Copy verbatim for every new model's `id` column. `comment="..."` mandatory per CONVENTIONS.md.

**UUID/string column with default factory** (lines 41-45):
```python
uuid: Mapped[str] = mapped_column(
    String,
    default=lambda: str(uuid4()),
    comment="Universally unique identifier for each task",
)
```

**Action:** Replicate factory-default pattern (`default=lambda: ...`) for `usage_events.idempotency_key` if Python-generated.

**Nullable string column** (lines 50-52):
```python
file_name: Mapped[str | None] = mapped_column(
    String, nullable=True, comment="Name of the file associated with the task"
)
```

**Action:** Use `Mapped[str | None]` PEP 604 union (NOT `Optional[str]`) for nullable. `nullable=True` explicit.

**created_at / updated_at pattern** (lines 81-91) — **CRITICAL CHANGE**:
```python
created_at: Mapped[datetime] = mapped_column(
    DateTime,                                              # ← change to DateTime(timezone=True)
    default=lambda: datetime.now(timezone.utc),
    comment="Date and time of creation",
)
updated_at: Mapped[datetime] = mapped_column(
    DateTime,                                              # ← change to DateTime(timezone=True)
    default=lambda: datetime.now(timezone.utc),
    onupdate=lambda: datetime.now(timezone.utc),
    comment="Date and time of last update",
)
```

**Action (DRY per CONTEXT decisions §65-71):** Extract module-level factory functions to eliminate repetition across 7 models:

```python
def _created_at_column() -> Mapped[datetime]:
    """Factory for created_at column with UTC default and tz-aware DateTime."""
    return mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="Date and time of creation (UTC)",
    )


def _updated_at_column() -> Mapped[datetime]:
    """Factory for updated_at column with UTC default + onupdate."""
    return mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="Date and time of last update (UTC)",
    )
```

**ForeignKey pattern** (no in-file analog — synthesize from SQLAlchemy 2.x style consistent with existing code):
```python
user_id: Mapped[int] = mapped_column(
    Integer,
    ForeignKey("users.id", ondelete="CASCADE", name="fk_<table>_user_id"),
    nullable=False,
    comment="Owning user (FK→users.id)",
)
```

**Action:** Named FK constraints (`fk_<table>_<col>` per CONTEXT decisions §76). `ondelete="CASCADE"` for owned rows; `ondelete="SET NULL"` for `tasks.user_id`.

**Table-level constraints pattern** (no in-file analog — synthesize):
```python
__table_args__ = (
    CheckConstraint(
        "plan_tier IN ('free','trial','pro','team')",
        name="ck_users_plan_tier",
    ),
    Index("idx_api_keys_prefix", "prefix"),
    UniqueConstraint("user_id", "cookie_hash", "ua_hash", "ip_subnet", "device_id",
                     name="uq_device_fingerprints_composite"),
)
```

**Action:** `CheckConstraint` for `Subscription.plan_tier` enum (raw CHECK chosen over `sa.Enum` per CONTEXT §77). `Index` for `api_keys.prefix`. Composite `UniqueConstraint` for `device_fingerprints`.

**Tiger-style invariants (CONTEXT §69):** Add at module bottom after all class defs:
```python
assert User.__tablename__ == "users", "tablename drift"
assert ApiKey.__tablename__ == "api_keys"
# ... etc for all 6 new models
```

**`tasks.user_id` addition (existing Task class):**
```python
user_id: Mapped[int | None] = mapped_column(
    Integer,
    ForeignKey("users.id", ondelete="SET NULL", name="fk_tasks_user_id"),
    nullable=True,
    comment="Owning user (nullable until Phase 12 backfill)",
)
```

---

### `app/infrastructure/database/connection.py` (infrastructure, event-driven) — MODIFY

**Analog:** self, lines 18-21 (engine block) — exact

**Existing engine pattern** (lines 18-21):
```python
DB_URL = Config.DB_URL
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
```

**Existing import block** (lines 1-13):
```python
"""This module provides database connection and session management."""

from collections.abc import Callable, Generator
from functools import wraps
from typing import Any

from dotenv import load_dotenv
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Config
```

**Action — add PRAGMA listener immediately after engine creation (before `SessionLocal`):**

Extend imports:
```python
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlite3 import Connection as SQLite3Connection

from app.core.logging import logger
```

Add listener (no nested ifs per CONTEXT §70 — early returns, flat):
```python
@event.listens_for(Engine, "connect")
def _enforce_sqlite_foreign_keys(
    dbapi_connection: Any, connection_record: Any
) -> None:
    """Enforce SQLite foreign-key constraints on every new connection.

    SQLite ships with FK enforcement OFF by default. We turn it ON for
    every connection the engine creates. Non-SQLite drivers are skipped.

    Args:
        dbapi_connection: Raw DB-API connection object.
        connection_record: SQLAlchemy connection pool record.
    """
    if not isinstance(dbapi_connection, SQLite3Connection):
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON")
    finally:
        cursor.close()
    logger.debug("PRAGMA foreign_keys=ON applied to new SQLite connection")
```

**Tiger-style fail-loud verification (CONTEXT §69)** — append after `SessionLocal`:
```python
with engine.connect() as _conn:
    _fk_on = _conn.exec_driver_sql("PRAGMA foreign_keys").scalar()
    assert _fk_on == 1, f"PRAGMA foreign_keys MUST be ON, got {_fk_on}"
```

---

### `alembic/env.py` (config, CLI-hook) — NEW

**Analog:** `app/infrastructure/database/connection.py` (engine + DB_URL wiring) — role-match

**Pattern to copy — DB_URL sourcing** (connection.py lines 13-20):
```python
from app.core.config import Config
DB_URL = Config.DB_URL
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
```

**Pattern to copy — metadata source** (connection.py lines 8-15 of `__init__.py`):
```python
from app.infrastructure.database.models import Base
# Base.metadata is the single source of truth
```

**env.py skeleton (synthesized, follows project conventions):**
```python
"""Alembic environment — wires migration runner to app config + ORM metadata."""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from app.core.config import Config
from app.infrastructure.database.models import Base

config = context.config

# Override sqlalchemy.url from app config — never duplicate the URL in alembic.ini.
config.set_main_option("sqlalchemy.url", Config.DB_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,  # SQLite-safe ALTER TABLE (CONTEXT §117)
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (live DB connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite-safe
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**Critical:** `render_as_batch=True` is mandatory — SQLite limited ALTER TABLE (CONTEXT §117).

---

### `alembic/versions/0001_baseline.py` (migration, schema-mutation) — NEW

**No close analog** — Alembic stock pattern. Empty migration; pre-existing `tasks` table is captured by stamp.

**Skeleton:**
```python
"""baseline — captures pre-existing tasks table.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-29

Existing operators run `alembic stamp 0001_baseline` against records.db
before running `alembic upgrade head`. No DDL emitted by this revision.
"""

from typing import Sequence, Union

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op — captures current tasks shape."""
    pass


def downgrade() -> None:
    """No-op — cannot un-baseline."""
    pass
```

---

### `alembic/versions/0002_auth_schema.py` (migration, schema-mutation) — NEW

**Analog:** `app/infrastructure/database/models.py` column shapes — role-match (replicate column defs as `sa.Column(...)` calls)

**Pattern — column type mapping (from models.py lines 35-91):**

| Models.py (`mapped_column`) | Migration (`sa.Column`) |
|------------------------------|--------------------------|
| `Integer, primary_key=True, autoincrement=True` | `sa.Integer, primary_key=True, autoincrement=True` |
| `String, nullable=True` | `sa.String, nullable=True` |
| `DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)` | `sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()` |
| `Float, nullable=True` | `sa.Float, nullable=True` |
| `JSON, nullable=True` | `sa.JSON, nullable=True` |

**Skeleton (flat ops, no nested ifs per CONTEXT §70):**
```python
"""auth_schema — adds users, api_keys, subscriptions, usage_events,
rate_limit_buckets, device_fingerprints; alters tasks to add user_id FK.

Revision ID: 0002_auth_schema
Revises: 0001_baseline
Create Date: 2026-04-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_auth_schema"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create auth/billing/rate-limit tables; add tasks.user_id FK."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("email", sa.String, nullable=False, unique=True),
        sa.Column("password_hash", sa.String, nullable=False),
        sa.Column("plan_tier", sa.String, nullable=False, server_default="trial"),
        sa.Column("stripe_customer_id", sa.String, nullable=True, unique=True),
        sa.Column("token_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "plan_tier IN ('free','trial','pro','team')",
            name="ck_users_plan_tier",
        ),
    )
    # ... api_keys, subscriptions, usage_events, rate_limit_buckets, device_fingerprints

    op.create_index("idx_api_keys_prefix", "api_keys", ["prefix"])

    # SQLite-safe ALTER for tasks.user_id (CONTEXT §117)
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(
            sa.Column("user_id", sa.Integer, nullable=True),
        )
        batch_op.create_foreign_key(
            "fk_tasks_user_id",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Reverse auth_schema: drop FK, drop tables."""
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_constraint("fk_tasks_user_id", type_="foreignkey")
        batch_op.drop_column("user_id")
    op.drop_index("idx_api_keys_prefix", table_name="api_keys")
    op.drop_table("device_fingerprints")
    op.drop_table("rate_limit_buckets")
    op.drop_table("usage_events")
    op.drop_table("subscriptions")
    op.drop_table("api_keys")
    op.drop_table("users")
```

**Critical:** All `tasks` ALTERs must use `op.batch_alter_table()` — SQLite limited ALTER TABLE.

---

### `app/main.py` (bootstrap, startup) — MODIFY

**Analog:** self, line 48 — exact

**Existing line to remove:**
```python
Base.metadata.create_all(bind=engine)
```

**Action:** Delete line 48. `Base` import (line 41 `from app.infrastructure.database import Base, engine`) stays — still used by line 79 `generate_db_schema(Base.metadata.tables.values())`.

---

### `pyproject.toml` (config, static) — MODIFY

**Analog:** self, lines 29-51 — exact

**Existing deps array** (lines 29-51) — append `alembic` alphabetically:
```python
dependencies = [
    "aiofiles>=25.1.0",
    "alembic>=1.13.0",          # ← ADD
    "apscheduler==3.10.4",
    ...
]
```

**Pinning style:** Mixed `==` (exact) and `>=` (lower-bound) already in repo. Use `>=1.13.0` (Alembic stable; `>=` matches `aiofiles`, `dependency-injector`, `puremagic`, `streaming-form-data`).

---

### `tests/integration/test_alembic_migration.py` (test, integration) — NEW

**Analog:** `tests/integration/test_task_lifecycle.py` lines 1-20 — role-match

**Imports + marker pattern (lines 1-17):**
```python
"""Integration tests for task lifecycle with real database."""

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.infrastructure.database.repositories.sqlalchemy_task_repository import (
    SQLAlchemyTaskRepository,
)
from tests.factories import TaskFactory


@pytest.mark.integration
class TestTaskLifecycle:
    """Integration tests for complete task lifecycle with real database."""
```

**Action — replicate structure:**
```python
"""Integration tests for Alembic baseline + auth_schema migration."""

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text


@pytest.mark.integration
class TestAlembicMigration:
    """Verify alembic upgrade head produces expected schema."""

    def test_upgrade_head_creates_all_tables(self, tmp_path: Path) -> None:
        """alembic upgrade head must create all 7 expected tables."""
        db_file = tmp_path / "alembic_test.db"
        db_url = f"sqlite:///{db_file}"
        # run: alembic -x db_url=... upgrade head
        # assert inspect(engine).get_table_names() ⊇ {users, api_keys, ...}

    def test_pragma_foreign_keys_on(self, tmp_path: Path) -> None:
        """PRAGMA foreign_keys must be ON after engine creation."""
        # use connection.py engine; assert exec_driver_sql("PRAGMA foreign_keys") == 1

    def test_baseline_stamp_on_existing_db(self, tmp_path: Path) -> None:
        """alembic stamp 0001_baseline must succeed on pre-existing tasks DB."""

    def test_check_constraint_rejects_invalid_plan_tier(self, tmp_path: Path) -> None:
        """users.plan_tier CHECK rejects values outside enum."""

    def test_idempotency_key_unique(self, tmp_path: Path) -> None:
        """usage_events.idempotency_key UNIQUE rejects duplicates."""
```

**Fixture pattern from `tests/fixtures/database.py` lines 13-24:**
```python
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    echo=False,
)
```
Reuse for in-memory tests where Alembic is not invoked; use `tmp_path` file DB when shelling out to `alembic` CLI.

---

## Shared Patterns

### DateTime Discipline (CONTEXT §59-63)
**Source:** synthesized factory functions in models.py
**Apply to:** All 6 new models + `tasks.created_at`/`updated_at` ALTER
```python
DateTime(timezone=True)
default=lambda: datetime.now(timezone.utc)
onupdate=lambda: datetime.now(timezone.utc)  # updated_at only
```
Existing `Task.created_at`/`updated_at` (models.py lines 81-91) currently use plain `DateTime` — migrate to `DateTime(timezone=True)` in `0002_auth_schema.py` via batch_alter_table.

### Column Comment Style (CONVENTIONS.md + Task model lines 35-99)
**Apply to:** Every column on every new model
```python
comment="<short imperative phrase, no trailing period inside Task model>"
```

### Naming
**Source:** STRUCTURE.md §165-186
- Tables: snake_case plural (`users`, `api_keys`)
- ORM classes: PascalCase singular (`User`, `ApiKey`)
- Columns: snake_case
- FK constraints: `fk_<table>_<column>`
- Indexes: `idx_<table>_<column>`
- Check constraints: `ck_<table>_<column>`
- Unique constraints: `uq_<table>_<column_or_name>`

### Logging
**Source:** `app/core/logging.py` lines 36-37
**Apply to:** `connection.py` PRAGMA listener
```python
from app.core.logging import logger
logger.debug("PRAGMA foreign_keys=ON applied to new SQLite connection")
```

### Tiger-Style Assertions (CONTEXT §69)
**Apply to:** `models.py` (tablename invariants), `connection.py` (PRAGMA verify)
```python
assert <Class>.__tablename__ == "<expected>", "tablename drift"
assert _fk_on == 1, f"PRAGMA foreign_keys MUST be ON, got {_fk_on}"
```

### Module Docstrings (CONVENTIONS.md §183)
**Apply to:** All NEW Python files
```python
"""<one-line module purpose>."""
```

### Test Marker (CONVENTIONS.md §201-206 + test_task_lifecycle.py line 16)
**Apply to:** `test_alembic_migration.py`
```python
@pytest.mark.integration
class TestAlembicMigration:
```

---

## No Analog Found

| File | Role | Reason | Fallback Source |
|------|------|--------|-----------------|
| `alembic.ini` | config | Alembic stock config; no prior migration tooling in repo | Alembic `init` template, override `sqlalchemy.url` placeholder via `env.py` |
| `alembic/script.py.mako` | template | Alembic stock revision template; no analog possible | Alembic `init` default template (do not customize) |
| `alembic/versions/0001_baseline.py` | migration | First migration in repo; nothing to copy from | RESEARCH.md §migration-strategy + Alembic docs |

**Planner instruction:** For these three files, generate from Alembic's `alembic init alembic` output, then override only `env.py` per the env.py pattern above. `alembic.ini` only needs:
- `script_location = alembic`
- `sqlalchemy.url =` (left empty — overridden by `env.py`)
- Default logger config block

---

## Metadata

**Analog search scope:** `app/infrastructure/database/`, `app/core/`, `app/main.py`, `tests/integration/`, `tests/fixtures/`, `pyproject.toml`
**Files scanned:** 11
**Key insight:** `Task` model (models.py:17-99) is the single highest-quality analog — its column patterns drive all 6 new models. `connection.py:18-21` engine block is the insertion point for the PRAGMA listener. `test_task_lifecycle.py:16-17` marker pattern drives migration test.
**Pattern extraction date:** 2026-04-29
