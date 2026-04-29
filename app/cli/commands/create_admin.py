"""`python -m app.cli create-admin --email <email>` — bootstrap admin user.

Inputs:
  --email / -e <email>   Required. Admin email address.

Password is read via ``getpass.getpass()`` TWICE (entry + confirmation).
NEVER as a CLI flag — passwords as flags leak into shell history and
``ps aux`` output (CONTEXT §141, locked).

Action: delegates hashing + persistence to
``AuthService.register(email, pw, plan_tier='pro')``.
The CLI contains NO hash logic itself (SRP — CONTEXT §91).

Exit codes:
  0 — admin created
  1 — password mismatch / duplicate email / weak password / any
      ValidationError raised by AuthService

Idempotency: re-running with an already-registered email exits 1 (no
overwrite, no enumeration leak).
"""

from __future__ import annotations

import getpass

import typer

from app.cli import app
from app.cli._helpers import _get_container
from app.core.exceptions import UserAlreadyExistsError, ValidationError
from app.core.logging import logger


@app.command(name="create-admin")
def create_admin(
    email: str = typer.Option(
        ...,
        "--email",
        "-e",
        help="Admin email address.",
    ),
) -> None:
    """Create an admin user with ``plan_tier='pro'``.

    Prompts for the password twice via :func:`getpass.getpass`; never
    accepts the password as a CLI flag.
    """
    # Guard 1: password mismatch — fail before touching the service layer.
    password = getpass.getpass(prompt="Admin password: ")
    confirm = getpass.getpass(prompt="Confirm password: ")
    if password != confirm:
        typer.echo("Passwords do not match.", err=True)
        raise typer.Exit(code=1)

    # Guard 2: delegate to AuthService — handles duplicate + weak-password.
    container = _get_container()
    auth_service = container.auth_service()
    try:
        user = auth_service.register(email, password, plan_tier="pro")
    except UserAlreadyExistsError:
        typer.echo("Admin user already exists. No changes made.", err=True)
        logger.warning("CLI create-admin idempotent re-run id_hint=existing")
        raise typer.Exit(code=1)
    except ValidationError as exc:
        # Catches WeakPasswordError + any other ValidationError subclass.
        typer.echo(f"Password rejected: {exc.user_message}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Admin user {user.id} created with email {user.email}")
    logger.info("CLI create-admin success id=%s", user.id)
