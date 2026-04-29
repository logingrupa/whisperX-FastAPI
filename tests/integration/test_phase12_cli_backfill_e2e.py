"""End-to-end integration test for Phase 12 CLI + 0003 migration.

Exercises the operator runbook against a tmp SQLite DB:

  1. fresh DB at tmp_path/test.db
  2. alembic upgrade 0002_auth_schema  -> tasks.user_id NULLABLE
  3. INSERT 3 task rows directly with user_id IS NULL (orphans)
  4. python -m app.cli create-admin --email admin@e2e.test
     (password fed via stdin — getpass falls back to stdin readline when no TTY)
  5. python -m app.cli backfill-tasks --admin-email admin@e2e.test --yes
  6. alembic upgrade head  -> applies 0003 (NOT NULL + idx_tasks_user_id)
  7. Assert: PRAGMA table_info(tasks) shows user_id NOT NULL
  8. Assert: idx_tasks_user_id exists in sqlite_master
  9. Assert: trying to INSERT a new task with user_id NULL raises IntegrityError
 10. Negative test: in a SECOND tmp DB, attempt 0003 with orphans present
     and assert the migration aborts with non-zero exit + stderr mentions
     orphan count / backfill-tasks.

Windows-specific note on getpass:
On POSIX `getpass.getpass` falls back to stdin readline when no TTY is
attached. On Windows it always reads from `msvcrt.getwch()` (the
keyboard), which makes piping a password via subprocess.run(input=...)
hang. To exercise create-admin end-to-end without touching production
code, the test invokes the child Python via a tiny `-c` preamble that
monkey-patches ``getpass.getpass`` to read from stdin BEFORE importing
``app.cli``. The subprocess still launches a fresh Python process,
still inherits ``DB_URL`` env, still exits via ``raise typer.Exit`` —
the only thing patched is the password-input function in the child
process. Production source (``app/cli/commands/create_admin.py``) is
unchanged.

Locked rule (CONTEXT §141): password is read via getpass ONLY in
production. The patch lives in test code only — never in app/.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

REPO_ROOT = Path(__file__).resolve().parents[2]

# Test-only preamble: patches getpass.getpass to read from sys.stdin so
# subprocess.run(input='pw\\npw\\n') feeds it. Imports app.cli AFTER the
# patch so create_admin's `import getpass` binding picks up the patched
# function. Calls Typer app() to run the registered subcommand. argv
# is injected from the subprocess CLI args.
_CLI_PREAMBLE = (
    "import sys, getpass; "
    "getpass.getpass = lambda prompt='Password: ', stream=None: "
    "sys.stdin.readline().rstrip('\\n'); "
    "from app.cli import app; "
    "app()"
)


def _run_alembic(
    args: list[str], db_url: str, *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Invoke alembic CLI with DB_URL pointed at the tmp DB."""
    env = os.environ.copy()
    env["DB_URL"] = db_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        check=check,
        capture_output=True,
        text=True,
    )


def _run_cli(
    args: list[str],
    db_url: str,
    *,
    stdin_input: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Invoke the Typer ``app`` in a child Python with patched getpass.

    Launches a fresh Python subprocess (so DB_URL env propagates to the
    SQLAlchemy engine module-load), prepends ``_CLI_PREAMBLE`` to patch
    ``getpass.getpass`` BEFORE ``app.cli`` is imported, then forwards the
    remaining args via ``sys.argv``. The subprocess invocation pattern
    matches ``python -m app.cli <args>`` semantically (same Typer entry,
    same Container lifecycle), the only delta is the in-child getpass
    binding — required because Windows getpass cannot be piped.
    """
    env = os.environ.copy()
    env["DB_URL"] = db_url
    return subprocess.run(
        [sys.executable, "-c", _CLI_PREAMBLE, *args],
        cwd=REPO_ROOT,
        env=env,
        check=check,
        capture_output=True,
        text=True,
        input=stdin_input,
    )


def _make_engine(db_path: Path):
    """Create a SQLAlchemy engine over a file-backed SQLite DB."""
    return create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )


def _seed_orphan_tasks(db_path: Path, count: int) -> None:
    """INSERT N rows into tasks with user_id IS NULL (orphans)."""
    engine = _make_engine(db_path)
    with engine.begin() as conn:
        for i in range(count):
            conn.execute(
                text(
                    "INSERT INTO tasks (uuid, status, file_name, "
                    "created_at, updated_at) VALUES "
                    "(:uuid, 'pending', :fn, :ts, :ts)"
                ),
                {
                    "uuid": f"orphan-{i}",
                    "fn": f"orphan-{i}.wav",
                    "ts": "2026-04-29 00:00:00+00:00",
                },
            )
    engine.dispose()


@pytest.mark.integration
def test_phase12_full_flow_create_admin_backfill_then_0003(
    tmp_path: Path,
) -> None:
    """Greenfield -> 0001+0002 -> seed orphans -> create-admin -> backfill -> 0003 -> assert NOT NULL."""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path}"

    # Step 1+2: fresh DB, upgrade to 0002.
    _run_alembic(["upgrade", "0002_auth_schema"], db_url)

    # Step 3: seed 3 orphan tasks.
    _seed_orphan_tasks(db_path, count=3)

    # Step 4: bootstrap admin via CLI subprocess with password on stdin.
    create_result = _run_cli(
        ["create-admin", "--email", "admin@e2e.test"],
        db_url,
        stdin_input="strong-pw-12345\nstrong-pw-12345\n",
    )
    assert create_result.returncode == 0, (
        f"create-admin failed: stdout={create_result.stdout!r} "
        f"stderr={create_result.stderr!r}"
    )
    assert "Admin user" in create_result.stdout
    assert "created" in create_result.stdout

    # Step 5: backfill orphans.
    backfill_result = _run_cli(
        [
            "backfill-tasks",
            "--admin-email", "admin@e2e.test",
            "--yes",
        ],
        db_url,
    )
    assert backfill_result.returncode == 0, (
        f"backfill-tasks failed: stdout={backfill_result.stdout!r} "
        f"stderr={backfill_result.stderr!r}"
    )
    assert "Reassigned 3" in backfill_result.stdout

    # Step 6: now apply 0003.
    upgrade_result = _run_alembic(["upgrade", "head"], db_url)
    assert upgrade_result.returncode == 0, (
        f"alembic upgrade head failed: stdout={upgrade_result.stdout!r} "
        f"stderr={upgrade_result.stderr!r}"
    )

    # Step 7: PRAGMA table_info shows tasks.user_id NOT NULL.
    engine = _make_engine(db_path)
    try:
        with engine.connect() as conn:
            cols = conn.execute(text("PRAGMA table_info(tasks)")).fetchall()
            user_id_col = next((row for row in cols if row[1] == "user_id"), None)
            assert user_id_col is not None, "tasks.user_id column missing after 0003"
            # PRAGMA table_info row: (cid, name, type, notnull, dflt_value, pk)
            assert user_id_col[3] == 1, (
                f"tasks.user_id should be NOT NULL after 0003, "
                f"got notnull={user_id_col[3]}"
            )

            # Step 8: idx_tasks_user_id exists.
            idx_rows = conn.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='index' AND tbl_name='tasks'"
                )
            ).fetchall()
            idx_names = {row[0] for row in idx_rows}
            assert "idx_tasks_user_id" in idx_names, (
                f"idx_tasks_user_id missing; found: {idx_names}"
            )

        # Step 9: NEW orphan insert is rejected by NOT NULL constraint.
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO tasks (uuid, status, file_name, user_id, "
                        "created_at, updated_at) VALUES "
                        "('after', 'pending', 'after.wav', NULL, "
                        "'2026-04-29 00:00:00+00:00', "
                        "'2026-04-29 00:00:00+00:00')"
                    )
                )
    finally:
        engine.dispose()


@pytest.mark.integration
def test_phase12_migration_refuses_to_run_with_orphans(
    tmp_path: Path,
) -> None:
    """0003 pre-flight: refuses to alter the column if any orphan rows remain."""
    db_path = tmp_path / "skip_backfill.db"
    db_url = f"sqlite:///{db_path}"

    # 0001 + 0002 (tasks + tasks.user_id NULLABLE).
    _run_alembic(["upgrade", "0002_auth_schema"], db_url)

    # Seed orphans, but skip the backfill step entirely.
    _seed_orphan_tasks(db_path, count=2)

    # Attempt 0003 — must fail loudly.
    result = _run_alembic(["upgrade", "head"], db_url, check=False)
    assert result.returncode != 0, (
        "0003 should refuse to run with orphans present. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = (result.stdout or "") + (result.stderr or "")
    assert (
        "user_id IS NULL" in combined
        or "orphan" in combined.lower()
        or "backfill-tasks" in combined
    ), (
        "Migration error message should mention orphans / backfill-tasks. "
        f"Got: {combined!r}"
    )
