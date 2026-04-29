"""SQLAlchemy implementation of IRateLimitRepository (BEGIN IMMEDIATE atomic upsert)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import DatabaseOperationError
from app.core.logging import logger
from app.domain.entities.rate_limit_bucket import RateLimitBucket as DomainBucket
from app.infrastructure.database.mappers.rate_limit_bucket_mapper import to_domain
from app.infrastructure.database.models import RateLimitBucket as ORMBucket


class SQLAlchemyRateLimitRepository:
    """SQLAlchemy implementation of IRateLimitRepository.

    ``upsert_atomic`` uses SQLite ``BEGIN IMMEDIATE`` to escalate to RESERVED
    lock immediately, preventing lost-update under multi-worker token-bucket
    consumption (CONTEXT §96-102 locked; mitigates T-11-10).
    """

    def __init__(self, session: Session) -> None:
        """Initialise repository with a SQLAlchemy session."""
        self.session = session

    def get_by_key(self, bucket_key: str) -> DomainBucket | None:
        """Read a bucket by its unique key; ``None`` on miss or read failure."""
        try:
            orm_bucket = (
                self.session.query(ORMBucket)
                .filter(ORMBucket.bucket_key == bucket_key)
                .first()
            )
            return to_domain(orm_bucket) if orm_bucket else None
        except SQLAlchemyError as e:
            logger.error("Failed to get bucket key=%s: %s", bucket_key, str(e))
            return None

    def upsert_atomic(self, bucket_key: str, new_state: dict[str, Any]) -> None:
        """Read-modify-write under ``BEGIN IMMEDIATE`` for SQLite worker-safety.

        Args:
            bucket_key: Unique bucket identifier.
            new_state: Mapping with ``tokens`` (int) and ``last_refill``
                (datetime) keys, computed by ``app.core.rate_limit.consume()``.

        Raises:
            DatabaseOperationError: If the upsert fails.
        """
        try:
            # SQLite-specific: BEGIN IMMEDIATE escalates to RESERVED lock now
            # so the read+write happens under one held lock (no lost updates).
            self.session.execute(text("BEGIN IMMEDIATE"))
            orm_bucket = (
                self.session.query(ORMBucket)
                .filter(ORMBucket.bucket_key == bucket_key)
                .first()
            )
            if orm_bucket is None:
                orm_bucket = ORMBucket(
                    bucket_key=bucket_key,
                    tokens=new_state["tokens"],
                    last_refill=new_state["last_refill"],
                )
                self.session.add(orm_bucket)
            else:
                orm_bucket.tokens = new_state["tokens"]
                orm_bucket.last_refill = new_state["last_refill"]
            self.session.commit()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error("Failed to upsert bucket key=%s: %s", bucket_key, str(e))
            raise DatabaseOperationError(
                operation="upsert_rate_limit",
                reason=str(e),
                original_error=e,
            )
