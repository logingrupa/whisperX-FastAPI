"""Repository interface for DeviceFingerprint entity (insert + read-only)."""

from __future__ import annotations

from typing import Protocol

from app.domain.entities.device_fingerprint import DeviceFingerprint


class IDeviceFingerprintRepository(Protocol):
    """Insert-once + read-only repository for ANTI-03 device fingerprints.

    Audit-trail semantics: ``add`` and ``get_recent_for_user`` only — no
    update or delete (deliberately omitted to preserve forensic value).
    """

    def add(self, fingerprint: DeviceFingerprint) -> int:
        """Insert a fingerprint row; return new id.

        Args:
            fingerprint: DeviceFingerprint entity to persist.

        Returns:
            int: Newly assigned primary-key id.

        Raises:
            DatabaseOperationError: If persistence fails.
        """
        ...

    def get_recent_for_user(
        self, user_id: int, limit: int = 50,
    ) -> list[DeviceFingerprint]:
        """Return most recent N fingerprints for a user (newest first).

        Args:
            user_id: Owning user's primary-key id.
            limit: Maximum number of rows to return (default 50).

        Returns:
            list[DeviceFingerprint]: Newest-first list capped at ``limit``.
        """
        ...
