"""Repository interface for RateLimitBucket entity."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from app.domain.entities.rate_limit_bucket import RateLimitBucket


T = TypeVar("T")

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

    def update_atomic(
        self,
        bucket_key: str,
        compute: Callable[[RateLimitBucket | None], tuple[dict[str, Any] | None, T]],
    ) -> T:
        """Read, recompute and write one bucket inside a single ``BEGIN IMMEDIATE``.

        The SQLite RESERVED lock spans the read and the write, so concurrent
        callers on any thread or connection never lose an update.

        Args:
            bucket_key: Unique bucket identifier.
            compute: Gets the stored bucket (``None`` if absent) and returns
                ``(new_state, result)``. ``new_state`` holds ``tokens`` (int)
                and ``last_refill`` (datetime); ``None`` writes nothing.

        Returns:
            The ``result`` that ``compute`` returned.

        Raises:
            DatabaseOperationError: If the transaction fails.
        """
        ...
