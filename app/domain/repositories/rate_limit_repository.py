"""Repository interface for RateLimitBucket entity."""

from __future__ import annotations

from typing import Any, Protocol

from app.domain.entities.rate_limit_bucket import RateLimitBucket


class IRateLimitRepository(Protocol):
    """Repository interface for RateLimitBucket — backed by SQLite token bucket."""

    def get_by_key(self, bucket_key: str) -> RateLimitBucket | None:
        """Get a bucket by its unique key.

        Args:
            bucket_key: Unique bucket identifier.

        Returns:
            RateLimitBucket | None: Bucket if found, ``None`` if not yet created.
        """
        ...

    def upsert_atomic(self, bucket_key: str, new_state: dict[str, Any]) -> None:
        """Read-modify-write a bucket atomically (``BEGIN IMMEDIATE``).

        Caller computed ``new_state`` via ``app.core.rate_limit.consume()``. The
        atomic transaction prevents lost-update under multi-worker SQLite.

        Args:
            bucket_key: Unique bucket identifier.
            new_state: Mapping with at least ``tokens`` (int) and ``last_refill``
                (datetime) keys.

        Raises:
            DatabaseOperationError: If the upsert fails.
        """
        ...
