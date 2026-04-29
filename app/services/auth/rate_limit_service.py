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

    def release(
        self,
        bucket_key: str,
        *,
        tokens: int = 1,
        capacity: int = 1,
    ) -> None:
        """Refund ``tokens`` to bucket (capped at ``capacity``).

        Used to release a held slot — e.g. concurrency semaphore slot
        held while a transcription runs. Caller passes the same
        ``capacity`` it used in the matching ``check_and_consume()`` call
        so the refunded count is never inflated past the bucket cap.

        No-op if ``bucket_key`` absent (defensive — release without prior
        consume should never crash).

        Phase 13-08 W1 fix: pairs with FreeTierGate.release_concurrency()
        called from ``process_audio_common`` try/finally so a
        concurrency slot is ALWAYS returned (success OR failure).
        """
        existing = self.repository.get_by_key(bucket_key)
        if existing is None:
            logger.debug("RateLimit release no-op (no bucket) key=%s", bucket_key)
            return
        new_tokens = min(capacity, existing.tokens + tokens)
        self.repository.upsert_atomic(
            bucket_key,
            {"tokens": new_tokens, "last_refill": existing.last_refill},
        )
        logger.debug(
            "RateLimit released bucket=%s tokens=%d/%d",
            bucket_key,
            new_tokens,
            capacity,
        )
