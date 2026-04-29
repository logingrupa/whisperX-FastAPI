"""SQLAlchemy implementation of the IUserRepository interface."""

from __future__ import annotations

from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import DatabaseOperationError
from app.core.logging import logger
from app.domain.entities.user import User as DomainUser
from app.infrastructure.database.mappers.user_mapper import to_domain, to_orm
from app.infrastructure.database.models import User as ORMUser


class SQLAlchemyUserRepository:
    """SQLAlchemy implementation of IUserRepository.

    Logging hygiene per CONTEXT §86-90: NEVER log ``password_hash`` or raw
    email payloads. Only ``id`` is safe for info-level logs.
    """

    def __init__(self, session: Session) -> None:
        """Initialise repository with a SQLAlchemy session."""
        self.session = session

    def add(self, user: DomainUser) -> int:
        """Persist a new user; return its primary-key id."""
        try:
            orm_user = to_orm(user)
            self.session.add(orm_user)
            self.session.commit()
            self.session.refresh(orm_user)
            logger.info("User added with id=%s", orm_user.id)
            return int(orm_user.id)
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error("Failed to add user: %s", str(e))
            raise DatabaseOperationError(
                operation="add_user",
                reason=str(e),
                original_error=e,
            )

    def get_by_id(self, identifier: int) -> DomainUser | None:
        """Read a user by primary-key id; ``None`` on miss or read failure."""
        try:
            orm_user = (
                self.session.query(ORMUser).filter(ORMUser.id == identifier).first()
            )
            return to_domain(orm_user) if orm_user else None
        except SQLAlchemyError as e:
            logger.error("Failed to get user by id=%s: %s", identifier, str(e))
            return None

    def get_by_email(self, email: str) -> DomainUser | None:
        """Read a user by unique email; ``None`` on miss or read failure."""
        try:
            orm_user = (
                self.session.query(ORMUser).filter(ORMUser.email == email).first()
            )
            if orm_user is None:
                logger.debug("User not found by email lookup")
                return None
            logger.debug("User found by email lookup id=%s", orm_user.id)
            return to_domain(orm_user)
        except SQLAlchemyError as e:
            logger.error("Failed to get user by email: %s", str(e))
            return None

    def update_token_version(self, identifier: int, new_version: int) -> None:
        """Atomically set ``users.token_version`` (logout-all-devices)."""
        try:
            orm_user = (
                self.session.query(ORMUser).filter(ORMUser.id == identifier).first()
            )
            if orm_user is None:
                raise DatabaseOperationError(
                    operation="update_token_version",
                    reason=f"user id={identifier} not found",
                )
            orm_user.token_version = new_version
            self.session.commit()
            logger.info("Token version bumped for user id=%s", identifier)
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(
                "Failed to bump token_version id=%s: %s", identifier, str(e),
            )
            raise DatabaseOperationError(
                operation="update_token_version",
                reason=str(e),
                original_error=e,
            )

    def update(self, identifier: int, update_data: dict[str, Any]) -> None:
        """Apply a partial-field update to a user row."""
        orm_user = (
            self.session.query(ORMUser).filter(ORMUser.id == identifier).first()
        )
        if orm_user is None:
            raise DatabaseOperationError(
                operation="update_user",
                reason=f"user id={identifier} not found",
            )
        try:
            for key, value in update_data.items():
                if hasattr(orm_user, key):
                    setattr(orm_user, key, value)
            self.session.commit()
            logger.info("User updated id=%s", identifier)
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error("Failed to update user id=%s: %s", identifier, str(e))
            raise DatabaseOperationError(
                operation="update_user",
                reason=str(e),
                original_error=e,
            )

    def delete(self, identifier: int) -> bool:
        """Hard-delete a user; cascades to api_keys/usage_events."""
        try:
            orm_user = (
                self.session.query(ORMUser).filter(ORMUser.id == identifier).first()
            )
            if orm_user is None:
                return False
            self.session.delete(orm_user)
            self.session.commit()
            logger.info("User deleted id=%s", identifier)
            return True
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error("Failed to delete user id=%s: %s", identifier, str(e))
            return False
