"""Repository interface for ApiKey entity."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.domain.entities.api_key import ApiKey


class IApiKeyRepository(Protocol):
    """Repository interface for ApiKey entity.

    Implementations swap backends without affecting business logic.
    All write methods raise ``DatabaseOperationError`` on persistence failure.
    """

    def add(self, api_key: ApiKey) -> int:
        """Add an ``api_key`` row; return its new id.

        Args:
            api_key: The ApiKey entity to persist.

        Returns:
            int: Newly assigned primary-key id.

        Raises:
            DatabaseOperationError: If persistence fails.
        """
        ...

    def get_by_id(self, identifier: int) -> ApiKey | None:
        """Get an ``api_key`` by id.

        Args:
            identifier: Primary-key id.

        Returns:
            ApiKey | None: ApiKey entity if found, ``None`` otherwise.
        """
        ...

    def get_by_prefix(self, prefix: str) -> list[ApiKey]:
        """Indexed lookup of ACTIVE keys (``revoked_at IS NULL``) matching prefix.

        Uses ``idx_api_keys_prefix`` from Phase 10 (KEY-08 — no full-table scan).

        Args:
            prefix: 8-char prefix string.

        Returns:
            list[ApiKey]: All active keys whose ``prefix`` column equals ``prefix``.
        """
        ...

    def get_by_user(self, user_id: int) -> list[ApiKey]:
        """Return all keys (active and revoked) belonging to a user.

        Args:
            user_id: Owning user's primary-key id.

        Returns:
            list[ApiKey]: All ApiKey entities for that user.
        """
        ...

    def mark_used(self, identifier: int, when: datetime) -> None:
        """Update ``last_used_at`` on a single ``api_key`` row.

        Args:
            identifier: Primary-key id of the key.
            when: Timestamp to record.

        Raises:
            DatabaseOperationError: If the key is not found or update fails.
        """
        ...

    def revoke(self, identifier: int) -> None:
        """Soft-delete (set ``revoked_at = now``). Idempotent.

        Args:
            identifier: Primary-key id of the key.

        Raises:
            DatabaseOperationError: If the key is not found or update fails.
        """
        ...
