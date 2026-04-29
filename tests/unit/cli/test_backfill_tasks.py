"""Unit tests for `python -m app.cli backfill-tasks` (Phase 12 / OPS-02).

Uses Typer's CliRunner to invoke the command in-process. The SQLAlchemy
engine is mocked at the command-module's import site so no real DB is
touched: `engine.begin()` returns a context manager whose `__enter__`
yields a mock connection. The connection's `execute()` is scripted to
return distinct results per call (count_before, update, count_after).

Coverage:
  1. --help shows backfill-tasks subcommand + --admin-email + --dry-run + --yes
  2. Missing admin → exit 1 (delegated to _resolve_admin's typer.Exit)
  3. Zero orphans → exit 0 with "No orphan tasks" — UPDATE never executed
  4. --dry-run with N orphans → exit 0 "Would reassign N" — UPDATE never executed
  5. User declines y/N prompt → exit 0 "Aborted" — UPDATE never executed
  6. --yes with N orphans → exit 0 "Reassigned N" + post-update verify
  7. Post-update verify still shows orphans → exit 1 "verification failed"
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from app.cli import app
from app.domain.entities.user import User


@pytest.fixture
def runner() -> CliRunner:
    # Click 8.2+ / Typer 0.20+: stderr and stdout are separated by default;
    # `mix_stderr` kwarg was removed.
    return CliRunner()


@pytest.fixture
def admin_user() -> User:
    return User(
        id=7,
        email="admin@example.com",
        password_hash="argon2-fake",
        plan_tier="pro",
    )


def _build_engine_mock(
    orphan_count_before: int,
    orphan_count_after: int = 0,
    rowcount: int | None = None,
) -> MagicMock:
    """Build a SQLAlchemy engine mock with scripted execute() returns.

    First execute()  = SELECT COUNT(*) WHERE user_id IS NULL  → orphan_count_before
    Second execute() = UPDATE tasks SET user_id ...           → result.rowcount
    Third execute()  = SELECT COUNT(*) WHERE user_id IS NULL  → orphan_count_after

    Caller can override rowcount; defaults to orphan_count_before (the
    realistic case where every counted orphan was successfully updated).
    """
    engine = MagicMock()
    conn = MagicMock()
    engine.begin.return_value.__enter__.return_value = conn
    engine.begin.return_value.__exit__.return_value = False

    count_before_result = MagicMock()
    count_before_result.scalar_one.return_value = orphan_count_before
    update_result = MagicMock()
    update_result.rowcount = (
        rowcount if rowcount is not None else orphan_count_before
    )
    count_after_result = MagicMock()
    count_after_result.scalar_one.return_value = orphan_count_after

    conn.execute.side_effect = [count_before_result, update_result, count_after_result]
    return engine


@pytest.fixture
def patched_helpers(admin_user: User):
    """Patch _resolve_admin and _get_container at the command-module import site."""
    container = MagicMock()
    container.db_engine.return_value = MagicMock()  # default — overridden per test
    with (
        patch(
            "app.cli.commands.backfill_tasks._get_container",
            return_value=container,
        ),
        patch(
            "app.cli.commands.backfill_tasks._resolve_admin",
            return_value=admin_user,
        ) as resolve_mock,
    ):
        yield container, resolve_mock


def test_help_lists_backfill_tasks(runner: CliRunner) -> None:
    result = runner.invoke(app, ["backfill-tasks", "--help"])
    assert result.exit_code == 0
    # Typer renders "--admin-email" — assert lowercase substring of help text
    assert "admin-email" in result.stdout.lower()
    assert "--dry-run" in result.stdout
    assert "--yes" in result.stdout


def test_missing_admin_exits_one(runner: CliRunner) -> None:
    """`_resolve_admin` raises `typer.Exit(1)` when admin email is unknown."""
    with patch(
        "app.cli.commands.backfill_tasks._resolve_admin",
        side_effect=typer.Exit(code=1),
    ):
        result = runner.invoke(
            app,
            ["backfill-tasks", "--admin-email", "missing@example.com", "--yes"],
        )
    assert result.exit_code == 1


def test_zero_orphans_idempotent_exit_zero(
    runner: CliRunner, patched_helpers
) -> None:
    container, _ = patched_helpers
    container.db_engine.return_value = _build_engine_mock(
        orphan_count_before=0, orphan_count_after=0
    )
    result = runner.invoke(
        app,
        ["backfill-tasks", "--admin-email", "admin@example.com", "--yes"],
    )
    assert result.exit_code == 0
    assert "No orphan tasks" in result.stdout


def test_dry_run_does_not_update(runner: CliRunner, patched_helpers) -> None:
    container, _ = patched_helpers
    engine = _build_engine_mock(orphan_count_before=42, orphan_count_after=42)
    container.db_engine.return_value = engine
    result = runner.invoke(
        app,
        ["backfill-tasks", "--admin-email", "admin@example.com", "--dry-run"],
    )
    assert result.exit_code == 0
    assert "Would reassign 42" in result.stdout
    # Only the SELECT COUNT ran — UPDATE was skipped
    conn = engine.begin.return_value.__enter__.return_value
    assert conn.execute.call_count == 1


def test_user_declines_prompt_exits_zero(
    runner: CliRunner, patched_helpers
) -> None:
    container, _ = patched_helpers
    engine = _build_engine_mock(orphan_count_before=5, orphan_count_after=5)
    container.db_engine.return_value = engine
    # Stdin "n" declines the typer.confirm prompt
    result = runner.invoke(
        app,
        ["backfill-tasks", "--admin-email", "admin@example.com"],
        input="n\n",
    )
    assert result.exit_code == 0
    assert "Aborted" in result.stdout
    conn = engine.begin.return_value.__enter__.return_value
    assert conn.execute.call_count == 1  # only the count query ran


def test_yes_flag_runs_update_and_verifies(
    runner: CliRunner, patched_helpers
) -> None:
    container, _ = patched_helpers
    engine = _build_engine_mock(orphan_count_before=42, orphan_count_after=0)
    container.db_engine.return_value = engine
    result = runner.invoke(
        app,
        ["backfill-tasks", "--admin-email", "admin@example.com", "--yes"],
    )
    assert result.exit_code == 0
    assert "Reassigned 42 orphan tasks" in result.stdout
    conn = engine.begin.return_value.__enter__.return_value
    # All three executes ran: count, update, post-count
    assert conn.execute.call_count == 3


def test_post_update_verification_failure_exits_one(
    runner: CliRunner, patched_helpers
) -> None:
    """Bug simulation: UPDATE ran but post-count still shows 3 orphans → fail loud."""
    container, _ = patched_helpers
    engine = _build_engine_mock(orphan_count_before=10, orphan_count_after=3)
    container.db_engine.return_value = engine
    result = runner.invoke(
        app,
        ["backfill-tasks", "--admin-email", "admin@example.com", "--yes"],
    )
    assert result.exit_code == 1
    combined = result.stdout + (result.stderr or "")
    assert (
        "verification failed" in combined.lower()
        or "still" in combined.lower()
    )
