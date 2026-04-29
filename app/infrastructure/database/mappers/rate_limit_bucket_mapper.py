"""Mapper functions for converting between domain and ORM RateLimitBucket models."""

from __future__ import annotations

from app.domain.entities.rate_limit_bucket import RateLimitBucket as DomainBucket
from app.infrastructure.database.models import RateLimitBucket as ORMBucket


def to_domain(orm_bucket: ORMBucket) -> DomainBucket:
    """Convert ORM RateLimitBucket to domain RateLimitBucket entity."""
    return DomainBucket(
        id=orm_bucket.id,
        bucket_key=orm_bucket.bucket_key,
        tokens=orm_bucket.tokens,
        last_refill=orm_bucket.last_refill,
    )


def to_orm(domain_bucket: DomainBucket) -> ORMBucket:
    """Convert domain RateLimitBucket to ORM RateLimitBucket."""
    return ORMBucket(
        bucket_key=domain_bucket.bucket_key,
        tokens=domain_bucket.tokens,
        last_refill=domain_bucket.last_refill,
    )
