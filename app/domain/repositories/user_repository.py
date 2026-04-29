"""Repository interface for User entity using Protocol for structural typing."""

from __future__ import annotations

from typing import Any, Protocol

from app.domain.entities.user import User


class IUserRepository(Protocol):
    """Repository interface for User entity.

    Implementations swap backends (SQLAlchemy, in-memory test double, etc.)
    without affecting business logic.

    All methods should handle their own error logging and raise appropriate
    typed exceptions when persistence fails.
    """

    def add(self, user: User) -> int:
        """Add a user; return new primary-key id.

        Args:
            user: The User entity to persist.

        Returns:
            int: Newly assigned primary-key id.

        Raises:
            DatabaseOperationError: If persistence fails.
        """
        ...

    def get_by_id(self, identifier: int) -> User | None:
        """Get user by primary-key id.

        Args:
            identifier: Primary-key id.

        Returns:
            User | None: User entity if found, ``None`` otherwise.
        """
        ...

    def get_by_email(self, email: str) -> User | None:
        """Get user by unique email.

        Args:
            email: Email address (unique).

        Returns:
            User | None: User entity if found, ``None`` otherwise.
        """
        ...

    def update_token_version(self, identifier: int, new_version: int) -> None:
        """Atomically set ``users.token_version`` (logout-all-devices).

        Args:
            identifier: Primary-key id of the user.
            new_version: New token version value.

        Raises:
            DatabaseOperationError: If the user is not found or update fails.
        """
        ...

    def update(self, identifier: int, update_data: dict[str, Any]) -> None:
        """Apply a partial-field update to a user row.

        Args:
            identifier: Primary-key id of the user.
            update_data: Mapping of column-name → new value.

        Raises:
            DatabaseOperationError: If the user is not found or update fails.
        """
        ...

    def delete(self, identifier: int) -> bool:
        """Hard-delete a user (cascades to api_keys/usage_events).

        Args:
            identifier: Primary-key id of the user.

        Returns:
            bool: True if removed, False if not found.
        """
        ...
