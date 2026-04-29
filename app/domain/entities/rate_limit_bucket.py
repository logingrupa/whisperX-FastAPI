"""Domain entity for RateLimitBucket — pure persistence row."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class RateLimitBucket:
    """Persistence shape of a ``rate_limit_buckets`` row.

    NO business methods — pure-logic refill/consume math lives in
    ``app.core.rate_limit.consume()`` (Plan 11-02).

    Attributes:
        id: Primary-key id; ``None`` until persisted.
        bucket_key: Unique bucket identifier (e.g. ``user:42:tx:hour``).
        tokens: Remaining tokens in the bucket.
        last_refill: Last refill timestamp (tz-aware UTC).
    """

    id: int | None
    bucket_key: str
    tokens: int
    last_refill: datetime
