"""Integration tests for Alembic baseline + auth_schema migration (Phase 10).

Covers Phase 10 success criteria:
  - Greenfield: alembic upgrade head from empty DB creates all 7 expected tables
  - Brownfield: stamp 0001_baseline then upgrade head preserves tasks rows + adds new tables
  - PRAGMA foreign_keys = ON enforced on every connection
  - tasks.user_id added with named FK fk_tasks_user_id
  - ck_users_plan_tier rejects invalid plan_tier values
  - uq_usage_events_idempotency_key rejects duplicate idempotency keys
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_TABLES = {
    "alembic_version",
    "tasks",
    "users",
    "api_keys",
    "subscriptions",
    "usage_events",
    "rate_limit_buckets",
    "device_fingerprints",
}


def _run_alembic(args: list[str], db_url: str) -> subprocess.CompletedProcess[str]:
    """Invoke the alembic CLI with DB_URL pointed at the tmp DB.

    Args:
        args: Alembic subcommand args (e.g. ["upgrade", "head"]).
        db_url: SQLAlchemy URL string for the target DB.

    Returns:
        The completed process; raises CalledProcessError on non-zero exit.
    """
    env = os.environ.copy()
    env["DB_URL"] = db_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def _make_engine(db_path: Path):
    """Create a SQLAlchemy engine over a file-backed SQLite DB."""
    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )


def _build_tasks_table(db_path: Path) -> None:
    """Seed a tmp SQLite DB with the legacy tasks-only shape (pre-Phase-10).

    Does NOT insert into alembic_version. Tests requiring a brownfield stamp
    must call _run_alembic(["stamp", "0001_baseline"], db_url) explicitly.
    """
    engine = _make_engine(db_path)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE tasks ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  uuid TEXT, status TEXT, result TEXT, file_name TEXT,"
            "  url TEXT, callback_url TEXT, audio_duration REAL,"
            "  language TEXT, task_type TEXT, task_params TEXT,"
            "  duration REAL, start_time TEXT, end_time TEXT,"
            "  error TEXT,"
            "  created_at DATETIME NOT NULL,"
            "  updated_at DATETIME NOT NULL,"
            "  progress_percentage INTEGER DEFAULT 0,"
            "  progress_stage TEXT"
            ")"
        )
    engine.dispose()


@pytest.mark.integration
class TestAlembicMigration:
    """Integration tests for Phase 10 Alembic migrations."""

    def test_pragma_foreign_keys_on_every_connection(self) -> None:
        """SCHEMA-05: PRAGMA foreign_keys returns 1 on every new connection."""
        from app.infrastructure.database.connection import engine

        for _ in range(3):
            with engine.connect() as conn:
                fk = conn.exec_driver_sql("PRAGMA foreign_keys").scalar()
                assert fk == 1, f"PRAGMA foreign_keys must be ON, got {fk}"

    def test_greenfield_upgrade_head_creates_all_expected_tables(
        self, tmp_path: Path
    ) -> None:
        """Greenfield: empty DB to alembic upgrade head creates exactly the 8 expected tables.

        0001_baseline.upgrade() creates tasks; 0002_auth_schema.upgrade() creates
        6 new tables and alters tasks. alembic_version is created by alembic itself.
        """
        db_path = tmp_path / "alembic_greenfield.db"
        db_url = f"sqlite:///{db_path}"
        _run_alembic(["upgrade", "head"], db_url)

        engine = _make_engine(db_path)
        tables = set(inspect(engine).get_table_names())
        engine.dispose()

        assert tables == EXPECTED_TABLES, (
            f"greenfield upgrade table-set mismatch:\n"
            f"  expected: {sorted(EXPECTED_TABLES)}\n"
            f"  got:      {sorted(tables)}\n"
            f"  missing:  {sorted(EXPECTED_TABLES - tables)}\n"
            f"  extra:    {sorted(tables - EXPECTED_TABLES)}"
        )

    def test_brownfield_stamp_then_upgrade_adds_new_tables(
        self, tmp_path: Path
    ) -> None:
        """Brownfield: legacy records.db to stamp 0001 to upgrade head adds 6 new tables.

        Simulates an existing pre-Phase-10 records.db. _build_tasks_table creates
        only the tasks table (no alembic_version). stamp 0001_baseline marks the
        chain at 0001 without re-running its create_table. upgrade head then runs
        only 0002, adding the 6 new tables and altering tasks.
        """
        db_path = tmp_path / "alembic_brownfield.db"
        _build_tasks_table(db_path)
        db_url = f"sqlite:///{db_path}"
        _run_alembic(["stamp", "0001_baseline"], db_url)
        _run_alembic(["upgrade", "head"], db_url)

        engine = _make_engine(db_path)
        tables = set(inspect(engine).get_table_names())
        engine.dispose()

        assert tables == EXPECTED_TABLES, (
            f"brownfield upgrade table-set mismatch: "
            f"missing={sorted(EXPECTED_TABLES - tables)} "
            f"extra={sorted(tables - EXPECTED_TABLES)}"
        )

    def test_brownfield_stamp_preserves_existing_tasks_rows(
        self, tmp_path: Path
    ) -> None:
        """SCHEMA-01/02: stamp 0001_baseline does not modify existing tasks rows."""
        db_path = tmp_path / "alembic_preserve.db"
        _build_tasks_table(db_path)

        engine = _make_engine(db_path)
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO tasks "
                "(uuid, status, task_type, created_at, updated_at) "
                "VALUES "
                "('u1', 'pending', 'transcribe', "
                "'2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        engine.dispose()

        db_url = f"sqlite:///{db_path}"
        _run_alembic(["stamp", "0001_baseline"], db_url)

        verify_engine = _make_engine(db_path)
        with verify_engine.connect() as conn:
            row_count = conn.exec_driver_sql(
                "SELECT COUNT(*) FROM tasks"
            ).scalar()
            version = conn.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar()
        verify_engine.dispose()

        assert row_count == 1, f"task row preserved across stamp; got {row_count}"
        assert version == "0001_baseline", f"version_num={version}"

    def test_upgrade_adds_tasks_user_id_with_named_fk(
        self, tmp_path: Path
    ) -> None:
        """SCHEMA-04: tasks.user_id column exists with named FK fk_tasks_user_id."""
        db_path = tmp_path / "alembic_user_id.db"
        _build_tasks_table(db_path)
        db_url = f"sqlite:///{db_path}"
        _run_alembic(["stamp", "0001_baseline"], db_url)
        _run_alembic(["upgrade", "head"], db_url)

        engine = _make_engine(db_path)
        inspector = inspect(engine)
        cols = {c["name"] for c in inspector.get_columns("tasks")}
        assert "user_id" in cols, f"tasks.user_id missing; got {cols}"

        fks = inspector.get_foreign_keys("tasks")
        named = [fk for fk in fks if fk.get("name") == "fk_tasks_user_id"]
        assert named, f"fk_tasks_user_id missing on tasks; got {fks}"
        engine.dispose()

    def test_check_constraint_rejects_invalid_plan_tier(
        self, tmp_path: Path
    ) -> None:
        """SCHEMA-07: users.plan_tier CHECK rejects values outside enum."""
        db_path = tmp_path / "alembic_check.db"
        db_url = f"sqlite:///{db_path}"
        _run_alembic(["upgrade", "head"], db_url)

        engine = _make_engine(db_path)
        with engine.begin() as conn:
            # CHECK enforcement is always on for SQLite.
            with pytest.raises(IntegrityError, match="CHECK"):
                conn.exec_driver_sql(
                    "INSERT INTO users "
                    "(email, password_hash, plan_tier, token_version, "
                    "created_at, updated_at) "
                    "VALUES "
                    "('a@b.c', 'hash', 'invalid_tier', 0, "
                    "'2026-01-01 00:00:00+00:00', '2026-01-01 00:00:00+00:00')"
                )
        engine.dispose()

    def test_unique_constraint_rejects_duplicate_idempotency_key(
        self, tmp_path: Path
    ) -> None:
        """SCHEMA-08: usage_events.idempotency_key UNIQUE rejects duplicates."""
        db_path = tmp_path / "alembic_unique.db"
        db_url = f"sqlite:///{db_path}"
        _run_alembic(["upgrade", "head"], db_url)

        engine = _make_engine(db_path)
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO users "
                "(email, password_hash, plan_tier, token_version, "
                "created_at, updated_at) "
                "VALUES "
                "('a@b.c', 'hash', 'trial', 0, "
                "'2026-01-01 00:00:00+00:00', '2026-01-01 00:00:00+00:00')"
            )
            conn.exec_driver_sql(
                "INSERT INTO usage_events "
                "(user_id, idempotency_key, created_at) "
                "VALUES (1, 'k1', '2026-01-01 00:00:00+00:00')"
            )
            with pytest.raises(IntegrityError, match="UNIQUE"):
                conn.exec_driver_sql(
                    "INSERT INTO usage_events "
                    "(user_id, idempotency_key, created_at) "
                    "VALUES (1, 'k1', '2026-01-01 00:00:00+00:00')"
                )
        engine.dispose()
