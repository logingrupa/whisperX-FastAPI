"""Unit tests for `python -m app.cli create-admin` (Phase 12 / OPS-01).

Uses Typer's CliRunner to invoke the command in-process. Container is
patched so AuthService is a MagicMock — no real DB, no real Argon2.
getpass.getpass is patched to return scripted values (NOT a real prompt).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from app.cli import app
from app.core.exceptions import UserAlreadyExistsError, WeakPasswordError
from app.domain.entities.user import User


@pytest.fixture
def runner() -> CliRunner:
    # Click 8.2+ / Typer 0.20+: stderr and stdout are separated by default;
    # `mix_stderr` kwarg was removed. `result.stderr` + `result.stdout` work
    # independently.
    return CliRunner()


@pytest.fixture
def mock_auth_service() -> MagicMock:
    svc = MagicMock()
    svc.register.return_value = User(
        id=7,
        email="admin@example.com",
        password_hash="argon2-fake",
        plan_tier="pro",
    )
    return svc


@pytest.fixture
def patched_container(mock_auth_service: MagicMock):
    """Patch _get_container() so .auth_service() returns the mock."""
    container = MagicMock()
    container.auth_service.return_value = mock_auth_service
    with patch(
        "app.cli.commands.create_admin._get_container",
        return_value=container,
    ):
        yield container


def test_help_lists_create_admin(runner: CliRunner) -> None:
    result = runner.invoke(app, ["create-admin", "--help"])
    assert result.exit_code == 0
    # Final command MUST expose --email; stub has no options, so this fails RED.
    assert "--email" in result.stdout
    # Locked CONTEXT §141: password is NEVER a CLI flag.
    assert "--password" not in result.stdout


def test_password_mismatch_exits_one(
    runner: CliRunner,
    patched_container: MagicMock,
    mock_auth_service: MagicMock,
) -> None:
    with patch(
        "app.cli.commands.create_admin.getpass.getpass",
        side_effect=["pw-correct-12345", "pw-different-9999"],
    ):
        result = runner.invoke(app, ["create-admin", "--email", "a@b.c"])
    assert result.exit_code == 1
    combined = (result.stderr or "") + (result.stdout or "")
    assert "Passwords do not match" in combined
    mock_auth_service.register.assert_not_called()


def test_successful_create_admin(
    runner: CliRunner,
    patched_container: MagicMock,
    mock_auth_service: MagicMock,
) -> None:
    with patch(
        "app.cli.commands.create_admin.getpass.getpass",
        side_effect=["pw-correct-12345", "pw-correct-12345"],
    ):
        result = runner.invoke(
            app, ["create-admin", "--email", "admin@example.com"]
        )
    assert result.exit_code == 0
    assert "Admin user 7 created" in result.stdout
    mock_auth_service.register.assert_called_once_with(
        "admin@example.com", "pw-correct-12345", plan_tier="pro"
    )


def test_duplicate_email_exits_one(
    runner: CliRunner,
    patched_container: MagicMock,
    mock_auth_service: MagicMock,
) -> None:
    mock_auth_service.register.side_effect = UserAlreadyExistsError()
    with patch(
        "app.cli.commands.create_admin.getpass.getpass",
        side_effect=["pw-correct-12345", "pw-correct-12345"],
    ):
        result = runner.invoke(
            app, ["create-admin", "--email", "admin@example.com"]
        )
    assert result.exit_code == 1
    combined = (result.stderr or "") + (result.stdout or "")
    assert "already exists" in combined.lower()


def test_weak_password_exits_one(
    runner: CliRunner,
    patched_container: MagicMock,
    mock_auth_service: MagicMock,
) -> None:
    mock_auth_service.register.side_effect = WeakPasswordError("too short")
    with patch(
        "app.cli.commands.create_admin.getpass.getpass",
        side_effect=["pw-correct-12345", "pw-correct-12345"],
    ):
        result = runner.invoke(
            app, ["create-admin", "--email", "admin@example.com"]
        )
    assert result.exit_code == 1
    combined = (result.stderr or "") + (result.stdout or "")
    assert "too short" in combined or "weak" in combined.lower()
