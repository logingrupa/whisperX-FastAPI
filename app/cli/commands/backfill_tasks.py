"""`python -m app.cli backfill-tasks --admin-email <email>` — reassign orphan tasks.

Operates on the ``tasks`` table: every row where ``user_id IS NULL`` is
reassigned to the named admin user. Required step before the
``0003_tasks_user_id_not_null`` migration (plan 12-04) can apply the
NOT NULL constraint without data loss.

Inputs:
  --admin-email <email>   Required. Email of an existing admin user.
  --dry-run               Report what would change; do not run UPDATE.
  --yes / -y              Skip the y/N confirmation prompt.

Pre-conditions:
  - Admin user exists (else exit 1 — ``_resolve_admin`` enforces).

Post-conditions:
  - ``SELECT COUNT(*) FROM tasks WHERE user_id IS NULL`` returns 0,
    verified by re-querying after the UPDATE. Non-zero → exit 1
    (fail loud — CONTEXT §92, tiger-style).

Idempotency:
  - 0 orphans → exit 0 ("No orphan tasks to backfill") — safe to re-run.
"""

from __future__ import annotations

import typer
from sqlalchemy import text

from app.cli import app
from app.cli._helpers import _get_container, _resolve_admin
from app.core.logging import logger

_COUNT_ORPHANS_SQL = "SELECT COUNT(*) FROM tasks WHERE user_id IS NULL"
_UPDATE_SQL = "UPDATE tasks SET user_id = :admin_id WHERE user_id IS NULL"


@app.command(name="backfill-tasks")
def backfill_tasks(
    admin_email: str = typer.Option(
        ...,
        "--admin-email",
        help="Email of an existing admin user (created via `create-admin`).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Report orphan count and exit without running UPDATE.",
    ),
    assume_yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip the y/N confirmation prompt (for scripted runbooks).",
    ),
) -> None:
    """Reassign every ``tasks.user_id IS NULL`` row to the named admin user."""
    container = _get_container()
    admin = _resolve_admin(admin_email, container=container)
    engine = container.db_engine()

    with engine.begin() as conn:
        orphan_count = conn.execute(text(_COUNT_ORPHANS_SQL)).scalar_one()

        # Guard 1: nothing to do — exit cleanly (idempotency).
        if orphan_count == 0:
            typer.echo("No orphan tasks to backfill.")
            return

        # Guard 2: dry-run — report and exit before touching data.
        if dry_run:
            typer.echo(
                f"Would reassign {orphan_count} orphan tasks to "
                f"admin {admin.email} (id={admin.id}). [dry-run]"
            )
            return

        # Guard 3: prompt unless --yes is set.
        proceed = assume_yes or typer.confirm(
            f"{orphan_count} tasks have user_id IS NULL — reassign to "
            f"{admin.email} (id={admin.id})?",
            default=False,
        )
        if not proceed:
            typer.echo("Aborted by user. No changes made.")
            return

        # Action: UPDATE in a single transaction (engine.begin() COMMITs on exit).
        result = conn.execute(text(_UPDATE_SQL), {"admin_id": admin.id})
        rows_affected = result.rowcount

        # Post-condition: verify zero orphans remain (tiger-style fail-loud).
        remaining = conn.execute(text(_COUNT_ORPHANS_SQL)).scalar_one()
        if remaining != 0:
            typer.echo(
                f"verification failed: {remaining} orphan tasks still remain "
                f"after UPDATE (rows_affected={rows_affected}). "
                f"Database is in an inconsistent state — investigate.",
                err=True,
            )
            logger.error(
                "backfill-tasks post-condition fail remaining=%s rows_affected=%s",
                remaining,
                rows_affected,
            )
            raise typer.Exit(code=1)

    typer.echo(
        f"Reassigned {rows_affected} orphan tasks to admin "
        f"{admin.email} (id={admin.id})."
    )
    logger.info(
        "CLI backfill-tasks success admin_id=%s rows_affected=%s",
        admin.id,
        rows_affected,
    )
