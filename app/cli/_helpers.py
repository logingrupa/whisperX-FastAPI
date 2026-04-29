"""Shared helpers for CLI commands — Container factory + admin email resolver.

Both `create-admin` (plan 02) and `backfill-tasks` (plan 03) call these.
Keeping them here satisfies the locked DRY rule (CONTEXT §90):
"share a `_resolve_admin(email: str) -> User` helper across both commands;
both commands instantiate Container() the same way".
"""

from __future__ import annotations

import typer

from app.core.container import Container
from app.core.logging import logger
from app.domain.entities.user import User


def _get_container() -> Container:
    """Build a fresh Container for CLI use.

    CLI commands are short-lived processes; one Container per invocation
    is the simplest correct lifecycle.
    """
    return Container()


def _resolve_admin(email: str, *, container: Container | None = None) -> User:
    """Look up a user by email; fail loudly with typer.Exit(1) if missing.

    Tiger-style fail-fast (CONTEXT §92): missing admin → clear stderr message
    + exit 1, never silent fallback to a different user.

    Args:
        email: Admin email to resolve. Caller is responsible for whatever
            minimal format validation is appropriate (Typer + the
            command-level option validator handle this).
        container: Optional injected Container (test seam). Defaults to a
            fresh `_get_container()` if None.

    Returns:
        User: The domain User entity for the requested email.

    Raises:
        typer.Exit(code=1): If no user matches the email.
    """
    container = container or _get_container()
    user_repository = container.user_repository()
    user = user_repository.get_by_email(email)
    if user is None:
        typer.echo(
            f"Admin user not found: {email} — run `create-admin` first.",
            err=True,
        )
        logger.warning("CLI _resolve_admin miss email_hint=<redacted>")
        raise typer.Exit(code=1)
    return user
