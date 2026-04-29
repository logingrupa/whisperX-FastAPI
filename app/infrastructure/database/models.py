"""This module defines the database models for the application."""

from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


# ---------------------------------------------------------------------------
# Column factories — DRY: shared shapes reused across every ORM class with
# standard created_at/updated_at semantics (Task, User, ApiKey, Subscription,
# UsageEvent, DeviceFingerprint).
# Per CONTEXT §65-71: SRP one-purpose, no nested ifs, fail-loud at module load.
# ---------------------------------------------------------------------------


def _created_at_column() -> Mapped[datetime]:
    """Factory for created_at column with UTC default and tz-aware DateTime.

    Returns:
        mapped_column with DateTime(timezone=True), NOT NULL,
        default=lambda: datetime.now(timezone.utc).
    """
    return mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="Date and time of creation (UTC, tz-aware)",
    )


def _updated_at_column() -> Mapped[datetime]:
    """Factory for updated_at column with UTC default + onupdate.

    Returns:
        mapped_column with DateTime(timezone=True), NOT NULL,
        default and onupdate set to datetime.now(timezone.utc).
    """
    return mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="Date and time of last update (UTC, tz-aware)",
    )


class Task(Base):
    """
    Table to store tasks information.

    Attributes:
    - id: Unique identifier for each task (Primary Key).
    - uuid: Universally unique identifier for each task.
    - status: Current status of the task.
    - result: JSON data representing the result of the task.
    - file_name: Name of the file associated with the task.
    - task_type: Type/category of the task.
    - duration: Duration of the task execution.
    - error: Error message, if any, associated with the task.
    - created_at: Date and time of creation.
    - updated_at: Date and time of last update.
    """

    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier for each task (Primary Key)",
    )
    uuid: Mapped[str] = mapped_column(
        String,
        default=lambda: str(uuid4()),
        comment="Universally unique identifier for each task",
    )
    status: Mapped[str] = mapped_column(String, comment="Current status of the task")
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, comment="JSON data representing the result of the task"
    )
    file_name: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Name of the file associated with the task"
    )
    url: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="URL of the file associated with the task"
    )
    callback_url: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Callback URL to POST results to"
    )
    audio_duration: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Duration of the audio in seconds"
    )
    language: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Language of the file associated with the task"
    )
    task_type: Mapped[str] = mapped_column(String, comment="Type/category of the task")
    task_params: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, comment="Parameters of the task"
    )
    duration: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Duration of the task execution"
    )
    start_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="Start time of the task execution"
    )
    end_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="End time of the task execution"
    )
    error: Mapped[str | None] = mapped_column(
        String, nullable=True, comment="Error message, if any, associated with the task"
    )
    created_at: Mapped[datetime] = _created_at_column()
    updated_at: Mapped[datetime] = _updated_at_column()
    progress_percentage: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=0,
        comment="Current progress percentage (0-100)"
    )
    progress_stage: Mapped[str | None] = mapped_column(
        String, nullable=True,
        comment="Current processing stage (queued, transcribing, aligning, diarizing, complete)"
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL", name="fk_tasks_user_id"),
        nullable=True,
        comment="Owning user (nullable until Phase 12 backfill)",
    )
