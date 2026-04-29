"""SQLAlchemy implementation of IDeviceFingerprintRepository (insert + read-only)."""

from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import DatabaseOperationError
from app.core.logging import logger
from app.domain.entities.device_fingerprint import DeviceFingerprint as DomainFp
from app.infrastructure.database.mappers.device_fingerprint_mapper import (
    to_domain,
    to_orm,
)
from app.infrastructure.database.models import DeviceFingerprint as ORMFp


class SQLAlchemyDeviceFingerprintRepository:
    """SQLAlchemy implementation of IDeviceFingerprintRepository (ANTI-03).

    Insert + read-only — no update or delete (audit-trail semantics).
    Logging hygiene per CONTEXT §86-90: NEVER log the hash columns or
    ``ip_subnet`` payload; only ``id`` and ``user_id`` are safe.
    """

    def __init__(self, session: Session) -> None:
        """Initialise repository with a SQLAlchemy session."""
        self.session = session

    def add(self, fingerprint: DomainFp) -> int:
        """Insert a fingerprint row; return its primary-key id."""
        try:
            orm_fp = to_orm(fingerprint)
            self.session.add(orm_fp)
            self.session.commit()
            self.session.refresh(orm_fp)
            # Log only id + user_id — never the hashes or subnet payload.
            logger.info(
                "DeviceFingerprint added id=%s user_id=%s",
                orm_fp.id,
                orm_fp.user_id,
            )
            return int(orm_fp.id)
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error("Failed to add device fingerprint: %s", str(e))
            raise DatabaseOperationError(
                operation="add_device_fingerprint",
                reason=str(e),
                original_error=e,
            )

    def get_recent_for_user(
        self, user_id: int, limit: int = 50,
    ) -> list[DomainFp]:
        """Return most recent ``limit`` fingerprints for a user (newest first)."""
        try:
            orm_fps = (
                self.session.query(ORMFp)
                .filter(ORMFp.user_id == user_id)
                .order_by(ORMFp.created_at.desc())
                .limit(limit)
                .all()
            )
            return [to_domain(fp) for fp in orm_fps]
        except SQLAlchemyError as e:
            logger.error(
                "Failed to get device fingerprints user_id=%s: %s",
                user_id,
                str(e),
            )
            return []
