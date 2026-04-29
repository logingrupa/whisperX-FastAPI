"""SQLAlchemy implementation of the IApiKeyRepository interface."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import DatabaseOperationError
from app.core.logging import logger
from app.domain.entities.api_key import ApiKey as DomainApiKey
from app.infrastructure.database.mappers.api_key_mapper import to_domain, to_orm
from app.infrastructure.database.models import ApiKey as ORMApiKey


class SQLAlchemyApiKeyRepository:
    """SQLAlchemy implementation of IApiKeyRepository.

    KEY-08: ``get_by_prefix`` relies on ``idx_api_keys_prefix`` (Phase 10) for
    O(log n) bearer-auth lookups — never a full-table scan. Filters on
    ``revoked_at IS NULL`` so revoked keys can never authenticate (T-11-12).

    Logging hygiene per CONTEXT §86-90: log only ``id`` and ``prefix``;
    NEVER log the full ``hash`` or any plaintext key material.
    """

    def __init__(self, session: Session) -> None:
        """Initialise repository with a SQLAlchemy session."""
        self.session = session

    def add(self, api_key: DomainApiKey) -> int:
        """Persist a new api_key row; return its primary-key id."""
        try:
            orm_key = to_orm(api_key)
            self.session.add(orm_key)
            self.session.commit()
            self.session.refresh(orm_key)
            logger.info("ApiKey added id=%s prefix=%s", orm_key.id, orm_key.prefix)
            return int(orm_key.id)
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error("Failed to add api_key: %s", str(e))
            raise DatabaseOperationError(
                operation="add_api_key",
                reason=str(e),
                original_error=e,
            )

    def get_by_id(self, identifier: int) -> DomainApiKey | None:
        """Read an api_key by id; ``None`` on miss or read failure."""
        try:
            orm_key = (
                self.session.query(ORMApiKey)
                .filter(ORMApiKey.id == identifier)
                .first()
            )
            return to_domain(orm_key) if orm_key else None
        except SQLAlchemyError as e:
            logger.error("Failed to get api_key id=%s: %s", identifier, str(e))
            return None

    def get_by_prefix(self, prefix: str) -> list[DomainApiKey]:
        """Indexed lookup using ``idx_api_keys_prefix``; ACTIVE keys only.

        Filters by prefix-column equality AND ``revoked_at IS NULL`` —
        the index makes this O(log n); revoked keys are always excluded
        (mitigates T-11-12 spoofing-via-revoked-key).
        """
        try:
            orm_keys = (
                self.session.query(ORMApiKey)
                .filter(ORMApiKey.prefix == prefix)
                .filter(ORMApiKey.revoked_at.is_(None))
                .all()
            )
            return [to_domain(k) for k in orm_keys]
        except SQLAlchemyError as e:
            logger.error(
                "Failed to get api_keys by prefix=%s: %s", prefix, str(e),
            )
            return []

    def get_by_user(self, user_id: int) -> list[DomainApiKey]:
        """Return all keys (active and revoked) belonging to a user."""
        try:
            orm_keys = (
                self.session.query(ORMApiKey)
                .filter(ORMApiKey.user_id == user_id)
                .all()
            )
            return [to_domain(k) for k in orm_keys]
        except SQLAlchemyError as e:
            logger.error(
                "Failed to get api_keys for user_id=%s: %s", user_id, str(e),
            )
            return []

    def mark_used(self, identifier: int, when: datetime) -> None:
        """Update ``last_used_at`` on a single api_key row."""
        try:
            orm_key = (
                self.session.query(ORMApiKey)
                .filter(ORMApiKey.id == identifier)
                .first()
            )
            if orm_key is None:
                raise DatabaseOperationError(
                    operation="mark_used",
                    reason=f"api_key id={identifier} not found",
                )
            orm_key.last_used_at = when
            self.session.commit()
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error("Failed to mark_used id=%s: %s", identifier, str(e))
            raise DatabaseOperationError(
                operation="mark_used",
                reason=str(e),
                original_error=e,
            )

    def revoke(self, identifier: int) -> None:
        """Soft-delete (set ``revoked_at = now``). Idempotent."""
        try:
            orm_key = (
                self.session.query(ORMApiKey)
                .filter(ORMApiKey.id == identifier)
                .first()
            )
            if orm_key is None:
                raise DatabaseOperationError(
                    operation="revoke",
                    reason=f"api_key id={identifier} not found",
                )
            if orm_key.revoked_at is None:
                orm_key.revoked_at = datetime.now(timezone.utc)
                self.session.commit()
            logger.info("ApiKey revoked id=%s", identifier)
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error("Failed to revoke api_key id=%s: %s", identifier, str(e))
            raise DatabaseOperationError(
                operation="revoke",
                reason=str(e),
                original_error=e,
            )
