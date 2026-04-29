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


class User(Base):
    """Table to store registered user accounts.

    Attributes:
    - id: Unique identifier for each user (Primary Key).
    - email: User's email address — unique, used as login identifier.
    - password_hash: Argon2id hash of the user's password (never plaintext).
    - plan_tier: Subscription tier; one of free/trial/pro/team.
    - stripe_customer_id: Stripe customer ID (nullable, populated in v1.3).
    - token_version: Bumped to invalidate all existing JWTs (logout-all-devices).
    - trial_started_at: When trial counter started (at first API key creation).
    - created_at: Date and time of creation (UTC, tz-aware).
    - updated_at: Date and time of last update (UTC, tz-aware).
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier for each user (Primary Key)",
    )
    email: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False,
        comment="User email address (unique, login identifier)",
    )
    password_hash: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Argon2id hash of the user's password",
    )
    plan_tier: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="trial",
        server_default="trial",
        comment="Subscription tier (free/trial/pro/team)",
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String,
        unique=True,
        nullable=True,
        comment="Stripe customer ID (populated in v1.3)",
    )
    token_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Token version for logout-all-devices invalidation",
    )
    trial_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the 7-day trial counter started (first API key)",
    )
    created_at: Mapped[datetime] = _created_at_column()
    updated_at: Mapped[datetime] = _updated_at_column()

    __table_args__ = (
        CheckConstraint(
            "plan_tier IN ('free','trial','pro','team')",
            name="ck_users_plan_tier",
        ),
    )


class ApiKey(Base):
    """Table to store user API keys (whsk_*) — sha256 hashed, soft-deletable.

    Attributes:
    - id: Unique identifier for each API key (Primary Key).
    - user_id: Owning user (FK → users.id, CASCADE on user delete).
    - name: User-supplied label for the key.
    - prefix: First 8 chars of the key (whsk_<8>) — indexed for O(log n) lookup.
    - hash: SHA-256 hex digest (64 chars) of the full key (never plaintext).
    - scopes: Comma-separated scope list (defaults to 'transcribe').
    - created_at: Date and time of creation (UTC, tz-aware).
    - last_used_at: When the key was most recently presented at a request (UTC).
    - revoked_at: Soft-delete timestamp; NULL means active (UTC).
    """

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier for each API key (Primary Key)",
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_api_keys_user_id"),
        nullable=False,
        comment="Owning user (FK → users.id)",
    )
    name: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="User-supplied label for the API key",
    )
    prefix: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        comment="First 8 chars of the API key (indexed for bearer lookup)",
    )
    hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hex digest of the full key",
    )
    scopes: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="transcribe",
        server_default="transcribe",
        comment="Comma-separated scopes (default: transcribe)",
    )
    created_at: Mapped[datetime] = _created_at_column()
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the key was most recently presented (UTC, tz-aware)",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Soft-delete timestamp; NULL means active (UTC, tz-aware)",
    )

    __table_args__ = (
        Index("idx_api_keys_prefix", "prefix"),
    )


class Subscription(Base):
    """Table to store Stripe subscription records (schema only; no runtime API in v1.2).

    Attributes:
    - id: Unique identifier for each subscription (Primary Key).
    - user_id: Owning user (FK → users.id, CASCADE on user delete).
    - stripe_subscription_id: Stripe subscription ID (unique, nullable until live).
    - plan: Stripe plan/price identifier.
    - status: Stripe subscription status string.
    - current_period_start: Period start timestamp (UTC, tz-aware).
    - current_period_end: Period end timestamp (UTC, tz-aware).
    - cancelled_at: Soft-cancel timestamp (UTC, tz-aware).
    - created_at: Date and time of creation (UTC, tz-aware).
    - updated_at: Date and time of last update (UTC, tz-aware).
    """

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier for each subscription (Primary Key)",
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_subscriptions_user_id"),
        nullable=False,
        comment="Owning user (FK → users.id)",
    )
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String,
        unique=True,
        nullable=True,
        comment="Stripe subscription ID (populated by webhook in v1.3)",
    )
    plan: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        comment="Stripe plan/price identifier",
    )
    status: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        comment="Stripe subscription status string",
    )
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Subscription period start (UTC, tz-aware)",
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Subscription period end (UTC, tz-aware)",
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Soft-cancel timestamp (UTC, tz-aware)",
    )
    created_at: Mapped[datetime] = _created_at_column()
    updated_at: Mapped[datetime] = _updated_at_column()


class UsageEvent(Base):
    """Table to log per-transcription usage for billing-readiness.

    Attributes:
    - id: Unique identifier for each usage event (Primary Key).
    - user_id: Owning user (FK → users.id, CASCADE on user delete).
    - task_id: Originating task (FK → tasks.id, nullable).
    - gpu_seconds: GPU compute seconds consumed.
    - file_seconds: Audio file duration in seconds.
    - model: Model identifier used for this transcription.
    - idempotency_key: UNIQUE key for Stripe webhook replay safety.
    - created_at: Date and time of creation (UTC, tz-aware).
    """

    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier for each usage event (Primary Key)",
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_usage_events_user_id"),
        nullable=False,
        comment="Owning user (FK → users.id)",
    )
    task_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tasks.id", name="fk_usage_events_task_id"),
        nullable=True,
        comment="Originating task (FK → tasks.id)",
    )
    gpu_seconds: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="GPU compute seconds consumed",
    )
    file_seconds: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Audio file duration in seconds",
    )
    model: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        comment="Model identifier used for this transcription",
    )
    idempotency_key: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False,
        comment="UNIQUE key for Stripe webhook replay safety",
    )
    created_at: Mapped[datetime] = _created_at_column()


class RateLimitBucket(Base):
    """Table-backed token bucket for SQLite-backed rate limiting (BEGIN IMMEDIATE worker-safe).

    Attributes:
    - id: Unique identifier for each bucket (Primary Key).
    - bucket_key: Unique bucket identifier (e.g. 'user:42:hour', 'ip:10.0.0.0/24:register:hour').
    - tokens: Remaining tokens in the bucket.
    - last_refill: Last refill timestamp (UTC, tz-aware).
    """

    __tablename__ = "rate_limit_buckets"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier for each bucket (Primary Key)",
    )
    bucket_key: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False,
        comment="Unique bucket identifier (e.g. user:42:hour)",
    )
    tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Remaining tokens in the bucket",
    )
    last_refill: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Last refill timestamp (UTC, tz-aware)",
    )


class DeviceFingerprint(Base):
    """Table to log per-login device fingerprints for anti-DDOS / anomaly detection.

    Attributes:
    - id: Unique identifier for each fingerprint (Primary Key).
    - user_id: Owning user (FK → users.id, CASCADE on user delete).
    - cookie_hash: SHA-256 hash of the session cookie value.
    - ua_hash: SHA-256 hash of the User-Agent header.
    - ip_subnet: IP /24 (IPv4) or /64 (IPv6) prefix.
    - device_id: Browser-stored UUID (localStorage).
    - created_at: Date and time of creation (UTC, tz-aware).
    """

    __tablename__ = "device_fingerprints"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier for each fingerprint (Primary Key)",
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_device_fingerprints_user_id",
        ),
        nullable=False,
        comment="Owning user (FK → users.id)",
    )
    cookie_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hash of the session cookie value",
    )
    ua_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hash of the User-Agent header",
    )
    ip_subnet: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="IP /24 (IPv4) or /64 (IPv6) prefix",
    )
    device_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Browser-stored UUID (localStorage)",
    )
    created_at: Mapped[datetime] = _created_at_column()

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "cookie_hash",
            "ua_hash",
            "ip_subnet",
            "device_id",
            name="uq_device_fingerprints_composite",
        ),
    )


# ---------------------------------------------------------------------------
# Tiger-style invariants — fail loudly at module load if tablenames drift.
# Per CONTEXT §69 (locked code quality bar).
# ---------------------------------------------------------------------------
assert User.__tablename__ == "users", "User.__tablename__ drift"
assert ApiKey.__tablename__ == "api_keys", "ApiKey.__tablename__ drift"
assert Subscription.__tablename__ == "subscriptions", "Subscription.__tablename__ drift"
assert UsageEvent.__tablename__ == "usage_events", "UsageEvent.__tablename__ drift"
assert RateLimitBucket.__tablename__ == "rate_limit_buckets", "RateLimitBucket.__tablename__ drift"
assert DeviceFingerprint.__tablename__ == "device_fingerprints", (
    "DeviceFingerprint.__tablename__ drift"
)
