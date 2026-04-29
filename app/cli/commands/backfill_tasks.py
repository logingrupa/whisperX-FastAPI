"""Stub — populated in plan 12-03.

Registers a placeholder `backfill-tasks` command so the Typer registry has at
least one entry at the end of plan 12-01 (Typer 0.20+ refuses to render
`--help` for a Typer instance with zero registered commands —
RuntimeError: "Could not get a command for this Typer instance").

Plan 12-03 fully rewrites this module: real --admin-email Option +
UPDATE tasks SET user_id reassignment + idempotency lands then.
"""

from __future__ import annotations

import typer

from app.cli import app


@app.command(name="backfill-tasks")
def backfill_tasks() -> None:
    """[stub — populated in plan 12-03] Reassign orphan tasks to an admin."""
    typer.echo("backfill-tasks: not implemented yet (plan 12-03).", err=True)
    raise typer.Exit(code=1)
