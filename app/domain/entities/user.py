"""Domain entity for User — pure Python, framework-free."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class User:
    """Domain entity representing a user account.

    Mirrors the Phase-10 ORM ``users`` table. Pure Python — no SQLAlchemy
    or other framework imports. Business methods:

    - ``bump_token_version``: invalidate all existing JWTs (logout-all-devices,
      AUTH-06).
    - ``start_trial``: idempotently set ``trial_started_at`` on first API key
      creation.

    Attributes:
        id: Primary-key id; ``None`` until persisted.
        email: Unique login identifier.
        password_hash: Argon2id PHC-string hash of the user's password.
        plan_tier: Subscription tier (``free`` | ``trial`` | ``pro`` | ``team``).
        stripe_customer_id: Optional Stripe customer id (populated v1.3+).
        token_version: Bumped on logout-all-devices to invalidate JWTs.
        trial_started_at: Timestamp the trial counter started (first API key).
        created_at: Row creation timestamp (tz-aware UTC).
        updated_at: Row last-update timestamp (tz-aware UTC).
    """

    id: int | None  # None until persisted
    email: str
    password_hash: str
    plan_tier: str = "trial"
    stripe_customer_id: str | None = None
    token_version: int = 0
    trial_started_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def bump_token_version(self) -> None:
        """Invalidate all existing JWTs (logout-all-devices)."""
        self.token_version += 1
        self.updated_at = datetime.now(timezone.utc)

    def start_trial(self) -> None:
        """Set ``trial_started_at`` if not already set. Idempotent."""
        if self.trial_started_at is not None:
            return
        self.trial_started_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
