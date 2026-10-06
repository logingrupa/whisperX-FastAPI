"""task_uuid_unique — tasks.uuid is unique.

Revision ID: 0007_task_uuid_unique
Revises: 0006_task_submission_key
Create Date: 2026-10-06

Clients address tasks by uuid (polling, and the SPA's TUS taskId becomes the
task uuid). Without a unique index a second row could share a live job's
identifier. Prod had no duplicates when this was written (2,143 rows).

Re-runnable: create/drop use IF [NOT] EXISTS.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0007_task_uuid_unique"
down_revision: Union[str, None] = "0006_task_submission_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Unique index on tasks.uuid."""
    op.create_index("uq_tasks_uuid", "tasks", ["uuid"], unique=True, if_not_exists=True)


def downgrade() -> None:
    """Reverse: drop the unique index."""
    op.drop_index("uq_tasks_uuid", table_name="tasks", if_exists=True)
