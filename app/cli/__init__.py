"""WhisperX admin CLI — entry point for `python -m app.cli`."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="whisperx-cli",
    help="WhisperX admin CLI — bootstrap admin users and run database backfills.",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# Subcommands registered by side-effect import (plans 02, 03).
# Keep these imports at the bottom AFTER `app` is defined so the decorators
# in those modules find the singleton.
from app.cli.commands import create_admin as _create_admin  # noqa: E402, F401
from app.cli.commands import backfill_tasks as _backfill_tasks  # noqa: E402, F401

__all__ = ["app"]
