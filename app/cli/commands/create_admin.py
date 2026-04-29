"""Stub — populated in plan 12-02.

Registers a placeholder `create-admin` command so the Typer registry has at
least one entry at the end of plan 12-01 (Typer 0.20+ refuses to render
`--help` for a Typer instance with zero registered commands —
RuntimeError: "Could not get a command for this Typer instance").

Plan 12-02 fully rewrites this module: real Option/getpass/AuthService.register
flow lands then.
"""

from __future__ import annotations

import typer

from app.cli import app


@app.command(name="create-admin")
def create_admin() -> None:
    """[stub — populated in plan 12-02] Create an admin user."""
    typer.echo("create-admin: not implemented yet (plan 12-02).", err=True)
    raise typer.Exit(code=1)
