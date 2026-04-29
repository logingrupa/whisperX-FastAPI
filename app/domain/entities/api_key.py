"""Domain entity for ApiKey — pure Python, framework-free."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ApiKey:
    """Domain entity for a user's API key (``whsk_*``).

    Stores ONLY the 8-char prefix and the SHA-256 hex hash; the raw plaintext
    is shown to the user once at creation time and never persisted.

    Attributes:
        id: Primary-key id; ``None`` until persisted.
        user_id: Owning user FK.
        name: User-supplied label.
        prefix: 8-char prefix (indexed via ``idx_api_keys_prefix`` from Phase 10).
        hash: SHA-256 hex digest (64 chars) of the full plaintext.
        scopes: Comma-separated scope list (default ``transcribe``).
        created_at: Row creation timestamp (tz-aware UTC).
        last_used_at: Most-recent presentation timestamp (tz-aware UTC).
        revoked_at: Soft-delete timestamp; ``None`` means active.
    """

    id: int | None
    user_id: int
    name: str
    prefix: str
    hash: str
    scopes: str = "transcribe"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None

    def is_active(self) -> bool:
        """A key is active iff it has not been soft-deleted."""
        return self.revoked_at is None

    def mark_used(self, when: datetime) -> None:
        """Update ``last_used_at``; persisted via repo on subsequent commit."""
        self.last_used_at = when

    def revoke(self) -> None:
        """Soft-delete (set ``revoked_at`` to now). Idempotent."""
        if self.revoked_at is not None:
            return
        self.revoked_at = datetime.now(timezone.utc)
