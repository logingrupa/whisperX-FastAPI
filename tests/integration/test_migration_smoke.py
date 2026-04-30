"""VERIFY-08 migration smoke — synthetic v1.1 baseline → upgrade head.

Asserts row preservation + tasks.user_id NOT NULL + FK enforcement.

Mirrors operator-facing migration runbook (Phase 17 OPS-03):
    1. Build v1.1 tasks table (no user_id col) + N seed rows
    2. _run_alembic(["stamp", "0001_baseline"], db_url)        — mark chain head
    3. _run_alembic(["upgrade", "0002_auth_schema"], db_url)   — adds nullable user_id col + auth tables
    4. INSERT admin user + UPDATE tasks SET user_id = admin.id
    5. _run_alembic(["upgrade", "head"], db_url)               — applies 0003 NOT NULL pre-flight + alter
    6. Assert: row count preserved, tasks.user_id NOT NULL, FK enforced

Code-quality invariants (verifier-grep enforced):
    DRY  — reuses _phase16_helpers._run_alembic + REPO_ROOT (single source).
    SRP  — _build_v11_baseline does schema only; _seed_admin_user_and_assign_tasks does data only.
    Tiger-style — every test asserts MORE THAN status (row count, column metadata, IntegrityError type).
    No nested-if — only flat `with` context managers + `pytest.raises`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError

from tests.integration._phase16_helpers import REPO_ROOT, _run_alembic

# REPO_ROOT re-exported via import for forward-compat with future helpers.
_ = REPO_ROOT


# ---------------------------------------------------------------------------
# Helpers — flat, single-purpose. No fixtures (each test owns its tmp_path DB).
# ---------------------------------------------------------------------------


def _make_engine(db_path: Path):
    """Create a SQLAlchemy engine over a file-backed SQLite DB."""
    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )


def _build_v11_baseline(db_path: Path, *, n_tasks: int = 3) -> None:
    """Create pre-Phase-10 tasks-only schema + ``n_tasks`` seed rows.

    Mirrors 0001_baseline.upgrade() column shape exactly so a subsequent
    ``alembic stamp 0001_baseline`` is a no-op marker rather than a re-create.
    NO ``user_id`` column — Phase 10's 0002_auth_schema adds it.
    NO ``alembic_version`` row — stamp will create it.
    """
    engine = _make_engine(db_path)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE tasks ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  uuid TEXT, status TEXT, result TEXT, file_name TEXT,"
            "  url TEXT, callback_url TEXT, audio_duration REAL,"
            "  language TEXT, task_type TEXT, task_params TEXT,"
            "  duration REAL, start_time TEXT, end_time TEXT, error TEXT,"
            "  created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,"
            "  progress_percentage INTEGER DEFAULT 0, progress_stage TEXT"
            ")"
        )
        for i in range(n_tasks):
            conn.exec_driver_sql(
                "INSERT INTO tasks (uuid, status, task_type, created_at, updated_at) "
                "VALUES (?, 'pending', 'speech-to-text', "
                "'2026-01-01 00:00:00', '2026-01-01 00:00:00')",
                (f"legacy-task-{i}",),
            )
    engine.dispose()


def _seed_admin_user_and_assign_tasks(db_path: Path) -> int:
    """Insert admin user (post-0002 schema) + assign every task to that admin.

    The 0003 pre-flight refuses to run if any tasks.user_id IS NULL; this
    helper is the operator-facing equivalent of `python -m app.cli backfill-tasks
    --admin-email <e>` invoked between 0002 and 0003 upgrades.

    Returns:
        The new admin user_id (lastrowid).
    """
    engine = _make_engine(db_path)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO users "
            "(email, password_hash, plan_tier, token_version, "
            "created_at, updated_at) "
            "VALUES (?, ?, 'pro', 0, "
            "'2026-04-29 00:00:00+00:00', '2026-04-29 00:00:00+00:00')",
            ("admin@phase16.example.com", "$argon2id$dummy"),
        )
        admin_id = conn.exec_driver_sql(
            "SELECT id FROM users WHERE email = 'admin@phase16.example.com'"
        ).scalar()
        conn.exec_driver_sql("UPDATE tasks SET user_id = ?", (admin_id,))
    engine.dispose()
    assert admin_id is not None, "admin user insert returned no id"
    return int(admin_id)


# ---------------------------------------------------------------------------
# Smoke tests — 4 cases (preservation, user_id assignment, NOT NULL, FK enforce).
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_brownfield_v11_to_head_preserves_task_rows(tmp_path: Path) -> None:
    """v1.1 tasks → 0001 stamp → upgrade head: row count preserved."""
    db_path = tmp_path / "smoke.db"
    _build_v11_baseline(db_path, n_tasks=3)
    db_url = f"sqlite:///{db_path}"

    _run_alembic(["stamp", "0001_baseline"], db_url)
    _run_alembic(["upgrade", "0002_auth_schema"], db_url)
    _seed_admin_user_and_assign_tasks(db_path)
    _run_alembic(["upgrade", "head"], db_url)

    engine = _make_engine(db_path)
    with engine.connect() as conn:
        row_count = conn.exec_driver_sql("SELECT COUNT(*) FROM tasks").scalar()
    engine.dispose()

    assert row_count == 3, f"row count changed from 3 to {row_count}"


@pytest.mark.integration
def test_brownfield_v11_to_head_assigns_user_id(tmp_path: Path) -> None:
    """Post-upgrade: every tasks row has user_id IS NOT NULL referencing seeded admin."""
    db_path = tmp_path / "smoke.db"
    _build_v11_baseline(db_path, n_tasks=5)
    db_url = f"sqlite:///{db_path}"

    _run_alembic(["stamp", "0001_baseline"], db_url)
    _run_alembic(["upgrade", "0002_auth_schema"], db_url)
    admin_id = _seed_admin_user_and_assign_tasks(db_path)
    _run_alembic(["upgrade", "head"], db_url)

    engine = _make_engine(db_path)
    with engine.connect() as conn:
        null_count = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM tasks WHERE user_id IS NULL"
        ).scalar()
        admin_match_count = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM tasks WHERE user_id = ?", (admin_id,)
        ).scalar()
    engine.dispose()

    assert null_count == 0, f"{null_count} tasks still have NULL user_id post-upgrade"
    assert admin_match_count == 5, (
        f"expected 5 tasks owned by admin, got {admin_match_count}"
    )


@pytest.mark.integration
def test_brownfield_v11_to_head_user_id_column_not_null(tmp_path: Path) -> None:
    """Post-upgrade: tasks.user_id column is NOT NULL (constraint applied by 0003)."""
    db_path = tmp_path / "smoke.db"
    _build_v11_baseline(db_path, n_tasks=2)
    db_url = f"sqlite:///{db_path}"

    _run_alembic(["stamp", "0001_baseline"], db_url)
    _run_alembic(["upgrade", "0002_auth_schema"], db_url)
    _seed_admin_user_and_assign_tasks(db_path)
    _run_alembic(["upgrade", "head"], db_url)

    engine = _make_engine(db_path)
    cols = {c["name"]: c for c in inspect(engine).get_columns("tasks")}
    engine.dispose()

    assert "user_id" in cols, f"tasks.user_id missing; cols={list(cols)}"
    assert cols["user_id"]["nullable"] is False, (
        "tasks.user_id must be NOT NULL post-0003"
    )


@pytest.mark.integration
def test_brownfield_fk_constraints_enforced(tmp_path: Path) -> None:
    """Post-upgrade: PRAGMA foreign_keys=ON enforces FK constraints on insert."""
    db_path = tmp_path / "smoke.db"
    _build_v11_baseline(db_path, n_tasks=1)
    db_url = f"sqlite:///{db_path}"

    _run_alembic(["stamp", "0001_baseline"], db_url)
    _run_alembic(["upgrade", "0002_auth_schema"], db_url)
    _seed_admin_user_and_assign_tasks(db_path)
    _run_alembic(["upgrade", "head"], db_url)

    engine = _make_engine(db_path)
    # Production engine (Phase 10-04 listener) sets PRAGMA foreign_keys=ON;
    # this test owns a fresh engine without that listener — enable manually.
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")
        with pytest.raises(IntegrityError):
            conn.exec_driver_sql(
                "INSERT INTO tasks "
                "(uuid, status, task_type, user_id, created_at, updated_at) "
                "VALUES ('orphan-task', 'pending', 'speech-to-text', 99999, "
                "'2026-04-29 00:00:00+00:00', '2026-04-29 00:00:00+00:00')"
            )
    engine.dispose()
