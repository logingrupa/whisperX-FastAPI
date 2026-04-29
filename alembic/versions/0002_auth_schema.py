"""auth_schema — adds 6 new tables and tasks.user_id FK; migrates tasks tz-aware datetimes.

Revision ID: 0002_auth_schema
Revises: 0001_baseline
Create Date: 2026-04-29

Tables created: users, api_keys, subscriptions, usage_events,
rate_limit_buckets, device_fingerprints.

tasks ALTERs (via batch_alter_table for SQLite safety):
- add column user_id INTEGER NULL with FK fk_tasks_user_id -> users.id ON DELETE SET NULL
- alter created_at to DateTime(timezone=True)
- alter updated_at to DateTime(timezone=True)

Pre-condition: tasks table exists. On greenfield, 0001_baseline.upgrade() creates it.
On brownfield (existing records.db stamped to 0001_baseline), it already exists.

All datetime columns are DateTime(timezone=True). All FKs are explicitly named
(fk_<table>_<col>). Code quality (locked, CONTEXT 65-71): DRY (no copy-paste
column shapes — each table is one flat create-table call), SRP (one revision
one concern: schema add), tiger-style (no silent defaults — every nullable column
is explicit), no nested ifs (zero conditional flow in migration ops).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_auth_schema"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create 6 new tables; add tasks.user_id FK; migrate tasks datetimes to tz-aware."""
    # ---- users ----
    op.create_table("users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("email", sa.String, nullable=False),
        sa.Column("password_hash", sa.String, nullable=False),
        sa.Column(
            "plan_tier",
            sa.String,
            nullable=False,
            server_default="trial",
        ),
        sa.Column("stripe_customer_id", sa.String, nullable=True),
        sa.Column(
            "token_version",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("stripe_customer_id", name="uq_users_stripe_customer_id"),
        sa.CheckConstraint(
            "plan_tier IN ('free','trial','pro','team')",
            name="ck_users_plan_tier",
        ),
    )

    # ---- api_keys ----
    op.create_table("api_keys",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_api_keys_user_id",
            ),
            nullable=False,
        ),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("prefix", sa.String(8), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column(
            "scopes",
            sa.String,
            nullable=False,
            server_default="transcribe",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_api_keys_prefix", "api_keys", ["prefix"])

    # ---- subscriptions ----
    op.create_table("subscriptions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_subscriptions_user_id",
            ),
            nullable=False,
        ),
        sa.Column("stripe_subscription_id", sa.String, nullable=True),
        sa.Column("plan", sa.String, nullable=True),
        sa.Column("status", sa.String, nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "stripe_subscription_id",
            name="uq_subscriptions_stripe_subscription_id",
        ),
    )

    # ---- usage_events ----
    op.create_table("usage_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_usage_events_user_id",
            ),
            nullable=False,
        ),
        sa.Column(
            "task_id",
            sa.Integer,
            sa.ForeignKey(
                "tasks.id",
                name="fk_usage_events_task_id",
            ),
            nullable=True,
        ),
        sa.Column("gpu_seconds", sa.Float, nullable=True),
        sa.Column("file_seconds", sa.Float, nullable=True),
        sa.Column("model", sa.String, nullable=True),
        sa.Column("idempotency_key", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_usage_events_idempotency_key",
        ),
    )

    # ---- rate_limit_buckets ----
    op.create_table("rate_limit_buckets",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("bucket_key", sa.String, nullable=False),
        sa.Column("tokens", sa.Integer, nullable=False),
        sa.Column("last_refill", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("bucket_key", name="uq_rate_limit_buckets_bucket_key"),
    )

    # ---- device_fingerprints ----
    op.create_table("device_fingerprints",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey(
                "users.id",
                ondelete="CASCADE",
                name="fk_device_fingerprints_user_id",
            ),
            nullable=False,
        ),
        sa.Column("cookie_hash", sa.String(64), nullable=False),
        sa.Column("ua_hash", sa.String(64), nullable=False),
        sa.Column("ip_subnet", sa.String, nullable=False),
        sa.Column("device_id", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "cookie_hash",
            "ua_hash",
            "ip_subnet",
            "device_id",
            name="uq_device_fingerprints_composite",
        ),
    )

    # ---- tasks ALTER (SQLite-safe via batch_alter_table) ----
    # tasks pre-exists at this revision (created by 0001_baseline on greenfield;
    # already on disk for brownfield records.db that was stamped to 0001).
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(
            sa.Column("user_id", sa.Integer, nullable=True),
        )
        batch_op.create_foreign_key(
            "fk_tasks_user_id",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.alter_column(
            "created_at",
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "updated_at",
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Reverse auth_schema: drop FK, alter datetimes back, drop 6 tables."""
    # ---- tasks revert ----
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.alter_column(
            "updated_at",
            type_=sa.DateTime(),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "created_at",
            type_=sa.DateTime(),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=False,
        )
        batch_op.drop_constraint("fk_tasks_user_id", type_="foreignkey")
        batch_op.drop_column("user_id")

    # ---- drop in reverse FK-dependency order ----
    op.drop_table("device_fingerprints")
    op.drop_table("rate_limit_buckets")
    op.drop_table("usage_events")
    op.drop_table("subscriptions")
    op.drop_index("idx_api_keys_prefix", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_table("users")
