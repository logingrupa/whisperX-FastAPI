"""RateLimitService — wraps app.core.rate_limit + IRateLimitRepository."""

from __future__ import annotations

from datetime import datetime, timezone

from app.core import rate_limit
from app.core.logging import logger
from app.domain.repositories.rate_limit_repository import IRateLimitRepository


class RateLimitService:
    """Token-bucket rate limit with SQLite-backed persistence (BEGIN IMMEDIATE).

    Phase 13 wires concrete buckets and policies; this service is the
    pure mechanism (CONTEXT §90-103 locked).
    """

    def __init__(self, repository: IRateLimitRepository) -> None:
        self.repository = repository

    def check_and_consume(
        self,
        bucket_key: str,
        *,
        tokens_needed: int,
        rate: float,
        capacity: int,
    ) -> bool:
        """Check + consume + persist atomically. Returns True if allowed."""
        now = datetime.now(timezone.utc)
        existing = self.repository.get_by_key(bucket_key)
        bucket: rate_limit.BucketState
        if existing is None:
            bucket = {"tokens": capacity, "last_refill": now}
        else:
            bucket = {
                "tokens": existing.tokens,
                "last_refill": existing.last_refill,
            }
        new_state, allowed = rate_limit.consume(
            bucket,
            tokens_needed=tokens_needed,
            now=now,
            rate=rate,
            capacity=capacity,
        )
        self.repository.upsert_atomic(bucket_key, dict(new_state))
        if not allowed:
            logger.debug("RateLimit denied bucket=%s", bucket_key)
        return allowed
