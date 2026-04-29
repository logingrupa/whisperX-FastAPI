"""SQLAlchemy implementation of the ITaskRepository interface.

Phase 13-07 — per-user scoping
------------------------------
``set_user_scope(user_id)`` pushes a ``WHERE user_id = :user_id`` predicate
into every read/write performed afterwards via the shared ``_scoped_query``
helper (DRT). The scope is request-bound: ``get_scoped_task_repository``
sets it before yielding and clears it on cleanup, so concurrent callers
never observe a stale filter even if the Factory provider is pooled.

A fail-loud guard in ``add()`` refuses to persist a Task that has neither
an explicit ``user_id`` nor a scope set — closes T-13-34 (orphan-task
write via mis-wired route) per /tiger-style.

Default scope is ``None`` so existing un-scoped callers (Phase 12 CLI,
internal services) keep working unchanged.
"""

from typing import Any
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Query, Session

from app.core.exceptions import DatabaseOperationError
from app.core.logging import logger
from app.domain.entities.task import Task as DomainTask
from app.infrastructure.database.mappers.task_mapper import to_domain, to_orm
from app.infrastructure.database.models import Task as ORMTask


class SQLAlchemyTaskRepository:
    """
    SQLAlchemy implementation of the ITaskRepository interface.

    This class provides concrete implementations of all task repository
    operations using SQLAlchemy for database access.

    Attributes:
        session: The SQLAlchemy database session for executing queries
        _user_scope: Optional user id pushed into every read/write WHERE
            clause; ``None`` means unscoped (admin / CLI default).
    """

    def __init__(self, session: Session):
        """
        Initialize the repository with a database session.

        Args:
            session: The SQLAlchemy database session
        """
        self.session = session
        self._user_scope: int | None = None

    def set_user_scope(self, user_id: int | None) -> None:
        """Push a user_id filter into all subsequent reads/writes.

        See ``ITaskRepository.set_user_scope`` for the contract. ``None``
        clears the filter; an int sets it. Idempotent — calling twice with
        the same value is a no-op.
        """
        self._user_scope = user_id

    def _scoped_query(self) -> Query:
        """Return a base query filtered by ``_user_scope`` when set.

        Single source of truth for the scope predicate — get_by_id, get_all,
        update, and delete all funnel through this helper (DRT). When
        ``_user_scope is None`` the query is un-filtered (admin/CLI path).
        """
        query = self.session.query(ORMTask)
        if self._user_scope is not None:
            query = query.filter(ORMTask.user_id == self._user_scope)
        return query

    def add(self, task: DomainTask) -> str:
        """
        Add a new task to the database.

        Args:
            task: The Task entity to add

        Returns:
            str: UUID of the newly created task

        Raises:
            ValueError: If neither ``task.user_id`` nor ``_user_scope``
                is set (T-13-34 fail-loud — refuses to persist orphan tasks).
            DatabaseOperationError: If the underlying INSERT fails.
        """
        # Inject scope user_id when the entity lacks an explicit owner.
        if (task.user_id is None or task.user_id == 0) and self._user_scope is not None:
            task.user_id = self._user_scope

        # Fail-loud: refuse to persist a task with no owner. /tiger-style —
        # silent orphan writes break per-user scoping invariants downstream
        # (cross-user GET would leak the row because user_id IS NULL).
        if task.user_id is None or task.user_id == 0:
            raise ValueError(
                "Cannot persist task without user_id (no scope set, no explicit value)"
            )

        try:
            # If task doesn't have a UUID yet, generate one
            if not task.uuid:
                task.uuid = str(uuid4())

            orm_task = to_orm(task)
            self.session.add(orm_task)
            self.session.commit()
            self.session.refresh(orm_task)

            logger.info(
                f"Task added successfully with UUID: {orm_task.uuid} user_id={orm_task.user_id}"
            )
            return str(orm_task.uuid)

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Failed to add task: {str(e)}")
            raise DatabaseOperationError(
                operation="add",
                reason=str(e),
                original_error=e,
                identifier=task.uuid,
            )

    def get_by_id(self, identifier: str) -> DomainTask | None:
        """
        Get a task by its UUID — scoped to ``_user_scope`` when set.

        Cross-user lookups return None (route then raises 404 opaquely —
        no enumeration of foreign tasks per SCOPE-02..04).

        Args:
            identifier: The UUID of the task to retrieve

        Returns:
            DomainTask | None: The Task entity if found AND owned by the
            scoped user (or any task when unscoped), None otherwise.
        """
        try:
            orm_task = (
                self._scoped_query().filter(ORMTask.uuid == identifier).first()
            )

            if orm_task:
                logger.debug(f"Task found with UUID: {identifier}")
                return to_domain(orm_task)
            else:
                logger.debug(f"Task not found with UUID: {identifier}")
                return None

        except SQLAlchemyError as e:
            logger.error(f"Failed to get task by ID {identifier}: {str(e)}")
            return None

    def get_all(self) -> list[DomainTask]:
        """
        Get all tasks from the database — scoped to ``_user_scope`` when set.

        Scoped callers see only their own tasks; unscoped callers (CLI,
        admin) see every row.

        Returns:
            list[DomainTask]: List of Task entities matching the scope.
        """
        try:
            orm_tasks = self._scoped_query().all()
            domain_tasks = [to_domain(orm_task) for orm_task in orm_tasks]

            logger.debug(f"Retrieved {len(domain_tasks)} tasks from database")
            return domain_tasks

        except SQLAlchemyError as e:
            logger.error(f"Failed to get all tasks: {str(e)}")
            return []

    def update(self, identifier: str, update_data: dict[str, Any]) -> None:
        """
        Update a task by its UUID — scoped to ``_user_scope`` when set.

        Cross-user updates raise ``ValueError("Task not found...")`` because
        the scoped query returns no row — identical surface to a genuine
        miss (no enumeration).

        Args:
            identifier: The UUID of the task to update
            update_data: Dictionary containing the attributes to update
                        along with their new values

        Raises:
            ValueError: If the task is not found within the current scope.
            DatabaseOperationError: If the underlying UPDATE fails.
        """
        orm_task = (
            self._scoped_query().filter(ORMTask.uuid == identifier).first()
        )

        if not orm_task:
            logger.error(f"Task not found for update with UUID: {identifier}")
            raise ValueError(f"Task not found with UUID: {identifier}")

        try:
            # Update attributes
            for key, value in update_data.items():
                if hasattr(orm_task, key):
                    setattr(orm_task, key, value)

            self.session.commit()
            logger.info(f"Task updated successfully with UUID: {identifier}")

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Failed to update task {identifier}: {str(e)}")
            raise DatabaseOperationError(
                operation="update",
                reason=str(e),
                original_error=e,
                identifier=identifier,
            )

    def delete(self, identifier: str) -> bool:
        """
        Delete a task by its UUID — scoped to ``_user_scope`` when set.

        Cross-user deletes return False (route then raises 404 opaquely);
        the foreign row is never touched.

        Args:
            identifier: The UUID of the task to delete

        Returns:
            bool: True if the task was deleted, False if not found within
            the current scope.
        """
        try:
            orm_task = (
                self._scoped_query().filter(ORMTask.uuid == identifier).first()
            )

            if orm_task:
                self.session.delete(orm_task)
                self.session.commit()
                logger.info(f"Task deleted successfully with UUID: {identifier}")
                return True
            else:
                logger.debug(f"Task not found for deletion with UUID: {identifier}")
                return False

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Failed to delete task {identifier}: {str(e)}")
            return False
