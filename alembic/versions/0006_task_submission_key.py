"""task_submission_key — resubmit dedupe key + task-list index on tasks.

Revision ID: 0006_task_submission_key
Revises: 0005_api_key_unlimited
Create Date: 2026-10-06

Adds:
  - ``tasks.submission_key`` (nullable String(64)): SHA-256 of the uploaded
    file bytes + task type + language + params. A submit whose key matches
    a task still ``processing`` for the same user returns that task instead
    of queueing a duplicate GPU job.
  - ``uq_tasks_in_flight_submission``: partial UNIQUE (user_id,
    submission_key) WHERE status = 'processing'. Backs the dedupe lookup
    against two identical submits racing. Pre-existing rows keep NULL keys,
    which never collide.
  - ``idx_tasks_user_id_created_at``: (user_id, created_at) so the task
    list's ``WHERE user_id = ? ORDER BY created_at DESC LIMIT n`` walks the
    index instead of sorting every row (and its multi-MB result payload)
    in a temp b-tree.

Plain ``op.add_column`` (SQLite ALTER TABLE ADD COLUMN): no table rebuild,
so the 450+ MB tasks table is not copied.

Re-runnable: SQLite commits each DDL statement on its own, so a run that
fails mid-way (e.g. "database is locked" during an index build) can leave
the column without the indexes. Every step skips work already done.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_task_submission_key"
down_revision: Union[str, None] = "0005_api_key_unlimited"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add submission_key + the in-flight unique index + the list index."""
    task_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("tasks")
    }
    if "submission_key" not in task_columns:
        op.add_column(
            "tasks",
            sa.Column("submission_key", sa.String(length=64), nullable=True),
        )
    op.create_index(
        "idx_tasks_user_id_created_at",
        "tasks",
        ["user_id", "created_at"],
        if_not_exists=True,
    )
    op.create_index(
        "uq_tasks_in_flight_submission",
        "tasks",
        ["user_id", "submission_key"],
        unique=True,
        sqlite_where=sa.text("status = 'processing'"),
        if_not_exists=True,
    )


def downgrade() -> None:
    """Reverse: drop both indexes, then the column."""
    op.drop_index("uq_tasks_in_flight_submission", table_name="tasks", if_exists=True)
    op.drop_index("idx_tasks_user_id_created_at", table_name="tasks", if_exists=True)
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_column("submission_key")
