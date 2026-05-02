"""Shared helpers for CLI commands — Container-free service builders.

Both `create-admin` (plan 02) and `backfill-tasks` (plan 03) call these.
Phase 19 Plan 13 deleted the legacy `app.core.container.Container`; CLI
commands now build the services they need directly from `SessionLocal`
+ the lru-cached singletons in `app.core.services`.

The DRY contract from CONTEXT §90 is preserved: `_resolve_admin(email)`
remains the single user-lookup helper; `_get_container()` is preserved as
a thin factory that returns a Container-shaped object exposing
`.auth_service()`, `.user_repository()`, and `.db_engine()` — the three
attributes the CLI commands consume. This keeps the existing patches in
`tests/unit/cli/test_create_admin.py` + `test_backfill_tasks.py` working
1:1 (they `patch("app.cli.commands.X._get_container", return_value=mock)`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import typer

from app.core import services as core_services
from app.core.logging import logger
from app.domain.entities.user import User
from app.domain.repositories.user_repository import IUserRepository
from app.infrastructure.database.connection import SessionLocal, engine
from app.infrastructure.database.repositories.sqlalchemy_user_repository import (
    SQLAlchemyUserRepository,
)
from app.services.auth import AuthService


@dataclass
class _CliContainer:
    """Container-shaped object exposing the three attributes CLI uses.

    Built on top of `SessionLocal` + `app.core.services` lru-cached
    singletons; replaces `app.core.container.Container`. Each method
    returns a freshly-constructed instance per call (matches the legacy
    Factory provider lifecycle expected by the commands and their tests).
    """

    auth_service: Callable[[], AuthService]
    user_repository: Callable[[], IUserRepository]
    db_engine: Callable[[], object]


def _build_auth_service() -> AuthService:
    """Construct an AuthService bound to a fresh CLI-scoped DB session.

    CLI processes are short-lived and single-threaded; binding the
    session to the service for the whole invocation matches the legacy
    Container.auth_service() lifecycle (the per-command session lives
    until the process exits — no pool exhaustion concern at this scale).
    """
    session = SessionLocal()
    return AuthService(
        user_repository=SQLAlchemyUserRepository(session),
        password_service=core_services.get_password_service(),
        token_service=core_services.get_token_service(),
    )


def _build_user_repository() -> IUserRepository:
    """Construct a SQLAlchemyUserRepository bound to a CLI-scoped DB session."""
    return SQLAlchemyUserRepository(SessionLocal())


def _get_container() -> _CliContainer:
    """Build a fresh Container-shaped facade for CLI use.

    CLI commands are short-lived processes; one facade per invocation is
    the simplest correct lifecycle. The returned object keeps the
    `.auth_service()`, `.user_repository()`, `.db_engine()` shape the
    commands and unit-test patches rely on (DRY — single seam).
    """
    return _CliContainer(
        auth_service=_build_auth_service,
        user_repository=_build_user_repository,
        db_engine=lambda: engine,
    )


def _resolve_admin(
    email: str, *, container: _CliContainer | None = None
) -> User:
    """Look up a user by email; fail loudly with typer.Exit(1) if missing.

    Tiger-style fail-fast (CONTEXT §92): missing admin → clear stderr message
    + exit 1, never silent fallback to a different user.

    Args:
        email: Admin email to resolve. Caller is responsible for whatever
            minimal format validation is appropriate (Typer + the
            command-level option validator handle this).
        container: Optional injected facade (test seam). Defaults to a
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
