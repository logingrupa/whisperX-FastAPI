"""Repository interface for Task entity using Protocol for structural typing."""

from typing import Any, Protocol

from app.domain.entities.task import Task


class ITaskRepository(Protocol):
    """
    Repository interface for Task entity.

    This interface defines the contract for task data access operations.
    Implementations can use different storage backends (SQLAlchemy, NoSQL, etc.)
    without affecting the business logic that depends on this interface.

    All methods should handle their own error logging and raise appropriate
    exceptions when operations fail.
    """

    def add(self, task: Task) -> str:
        """
        Add a new task to the repository.

        Args:
            task: The Task entity to add

        Returns:
            str: UUID of the newly created task

        Raises:
            Exception: If task creation fails
        """
        ...

    def get_by_id(self, identifier: str) -> Task | None:
        """
        Get a task by its UUID.

        Args:
            identifier: The UUID of the task to retrieve

        Returns:
            Task | None: The Task entity if found, None otherwise
        """
        ...

    def get_all(self) -> list[Task]:
        """
        Get all tasks from the repository.

        Returns:
            list[Task]: List of all Task entities
        """
        ...

    def list_paginated(
        self,
        *,
        q: str | None,
        status: str | None,
        offset: int,
        limit: int,
    ) -> list[Task]:
        """Return a paginated, optionally filtered slice of tasks (Plan 15-ux).

        Implementations MUST push the user-scope filter (set via
        ``set_user_scope``) AND the q/status predicates into SQL — never
        load every row into memory and slice in Python. ``q`` is matched
        case-insensitively against file_name; ``status`` is exact-match.

        Args:
            q: Case-insensitive substring filter on file_name (or None).
            status: Exact-match status filter (or None).
            offset: Rows to skip (>= 0).
            limit: Maximum rows to return (>= 1).

        Returns:
            list[Task]: The page slice, ordered by created_at DESC so the
            newest tasks appear first.
        """
        ...

    def count(self, *, q: str | None, status: str | None) -> int:
        """Return the count of tasks matching q/status under the active scope.

        Mirrors ``list_paginated`` filters so the route can render
        "Page N of M". Single SELECT COUNT(*) — no N+1.

        Args:
            q: Case-insensitive substring filter on file_name (or None).
            status: Exact-match status filter (or None).

        Returns:
            int: Number of matching tasks (0 if none / scope mismatch).
        """
        ...

    def update(self, identifier: str, update_data: dict[str, Any]) -> None:
        """
        Update a task by its UUID.

        Args:
            identifier: The UUID of the task to update
            update_data: Dictionary containing the attributes to update
                        along with their new values

        Raises:
            ValueError: If the task is not found
            Exception: If update fails
        """
        ...

    def delete(self, identifier: str) -> bool:
        """
        Delete a task by its UUID.

        Args:
            identifier: The UUID of the task to delete

        Returns:
            bool: True if the task was deleted, False if not found
        """
        ...

    def set_user_scope(self, user_id: int | None) -> None:
        """
        Push a user_id filter into all subsequent reads/writes.

        When ``set_user_scope(N)`` is called:
          - ``get_by_id``, ``get_all``, ``update``, ``delete`` filter
            ``WHERE user_id = N`` at the SQL layer.
          - ``add()`` injects ``task.user_id = N`` if the entity does not
            already carry an explicit owner.
        When ``set_user_scope(None)`` is called:
          - All filters removed (admin / unscoped CLI access).

        The scope is request-bound — set by ``get_scoped_task_repository``
        before yielding and cleared on cleanup. Cross-user requests therefore
        see an empty result set (returns None / [] / False) and routes raise
        ``404`` opaquely (no enumeration of foreign tasks — SCOPE-02..04).

        Args:
            user_id: The owning user's id, or None for unscoped operations.
        """
        ...
