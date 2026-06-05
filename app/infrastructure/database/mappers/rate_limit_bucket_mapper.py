"""Mapper functions for converting between domain and ORM RateLimitBucket models."""

from __future__ import annotations

from app.core.time import ensure_utc_aware
from app.domain.entities.rate_limit_bucket import RateLimitBucket as DomainBucket
from app.infrastructure.database.models import RateLimitBucket as ORMBucket


def to_domain(orm_bucket: ORMBucket) -> DomainBucket:
    """Convert ORM RateLimitBucket to domain RateLimitBucket entity.

    ``rate_limit.consume`` subtracts ``last_refill`` from a tz-aware ``now``,
    so the SQLite-naive read is normalised to UTC-aware (see
    ``app.core.time.ensure_utc_aware``).
    """
    return DomainBucket(
        id=orm_bucket.id,
        bucket_key=orm_bucket.bucket_key,
        tokens=orm_bucket.tokens,
        last_refill=ensure_utc_aware(orm_bucket.last_refill),
    )


def to_orm(domain_bucket: DomainBucket) -> ORMBucket:
    """Convert domain RateLimitBucket to ORM RateLimitBucket."""
    return ORMBucket(
        bucket_key=domain_bucket.bucket_key,
        tokens=domain_bucket.tokens,
        last_refill=domain_bucket.last_refill,
    )
