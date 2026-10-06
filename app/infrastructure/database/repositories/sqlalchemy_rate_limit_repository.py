"""SQLAlchemy implementation of IRateLimitRepository (BEGIN IMMEDIATE atomic update)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import DatabaseOperationError
from app.core.logging import logger
from app.domain.entities.rate_limit_bucket import RateLimitBucket as DomainBucket
from app.infrastructure.database.mappers.rate_limit_bucket_mapper import to_domain
from app.infrastructure.database.models import RateLimitBucket as ORMBucket

T = TypeVar("T")


class SQLAlchemyRateLimitRepository:
    """SQLAlchemy implementation of IRateLimitRepository.

    ``update_atomic`` uses SQLite ``BEGIN IMMEDIATE`` to escalate to RESERVED
    lock immediately and reads, recomputes and writes under it, preventing
    lost updates under concurrent token-bucket consumption (CONTEXT §96-102
    locked; mitigates T-11-10).
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

    def update_atomic(
        self,
        bucket_key: str,
        compute: Callable[[DomainBucket | None], tuple[dict[str, Any] | None, T]],
    ) -> T:
        """Read, recompute and write one bucket under ``BEGIN IMMEDIATE``.

        Args:
            bucket_key: Unique bucket identifier.
            compute: Gets the stored bucket (``None`` if absent) and returns
                ``(new_state, result)``; ``new_state=None`` writes nothing.

        Returns:
            The ``result`` that ``compute`` returned.

        Raises:
            DatabaseOperationError: If the transaction fails.
        """
        try:
            # SQLite-specific: BEGIN IMMEDIATE takes the RESERVED lock now, so
            # the read, the computation and the write see no other writer.
            self.session.execute(text("BEGIN IMMEDIATE"))
            orm_bucket = (
                self.session.query(ORMBucket)
                .filter(ORMBucket.bucket_key == bucket_key)
                .populate_existing()
                .first()
            )
            new_state, result = compute(to_domain(orm_bucket) if orm_bucket else None)
            if new_state is not None:
                self._write(orm_bucket, bucket_key, new_state)
            self.session.commit()
            return result
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error("Failed to update bucket key=%s: %s", bucket_key, str(e))
            raise DatabaseOperationError(
                operation="update_rate_limit",
                reason=str(e),
                original_error=e,
            )

    def _write(
        self, orm_bucket: ORMBucket | None, bucket_key: str, new_state: dict[str, Any]
    ) -> None:
        """Stage the new token count on the existing row or a new one."""
        if orm_bucket is None:
            self.session.add(
                ORMBucket(
                    bucket_key=bucket_key,
                    tokens=new_state["tokens"],
                    last_refill=new_state["last_refill"],
                )
            )
            return
        orm_bucket.tokens = new_state["tokens"]
        orm_bucket.last_refill = new_state["last_refill"]
