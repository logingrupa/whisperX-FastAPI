"""baseline — creates the tasks table matching the current ORM shape.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-29

Greenfield: `alembic upgrade head` runs upgrade() and creates tasks.
Brownfield (existing records.db): operator runs `alembic stamp 0001_baseline`
to mark the chain at 0001 without re-creating tasks (it already exists).
Subsequent `alembic upgrade head` then runs only 0002 (auth_schema).

Tasks table shape mirrors app/infrastructure/database/models.py::Task verbatim
as of Phase 10 start. Plan 03's 0002_auth_schema.py alters created_at/updated_at
to DateTime(timezone=True) and adds user_id FK.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the tasks table mirroring the pre-Phase-10 ORM Task shape."""
    op.create_table("tasks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("uuid", sa.String, nullable=True),
        sa.Column("status", sa.String, nullable=True),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("file_name", sa.String, nullable=True),
        sa.Column("url", sa.String, nullable=True),
        sa.Column("callback_url", sa.String, nullable=True),
        sa.Column("audio_duration", sa.Float, nullable=True),
        sa.Column("language", sa.String, nullable=True),
        sa.Column("task_type", sa.String, nullable=True),
        sa.Column("task_params", sa.JSON, nullable=True),
        sa.Column("duration", sa.Float, nullable=True),
        sa.Column("start_time", sa.DateTime(), nullable=True),
        sa.Column("end_time", sa.DateTime(), nullable=True),
        sa.Column("error", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("progress_percentage", sa.Integer, nullable=True, server_default="0"),
        sa.Column("progress_stage", sa.String, nullable=True),
    )


def downgrade() -> None:
    """Drop the tasks table."""
    op.drop_table("tasks")
