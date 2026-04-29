"""tasks_user_id_not_null — tighten tasks.user_id to NOT NULL + add idx_tasks_user_id.

Revision ID: 0003_tasks_user_id_not_null
Revises: 0002_auth_schema
Create Date: 2026-04-29

Pre-condition: `python -m app.cli backfill-tasks --admin-email <e>` MUST have
run successfully — i.e. every `tasks.user_id IS NULL` row reassigned to an
admin user. This migration's `upgrade()` performs a pre-flight orphan-row
count via `op.get_bind().execute(...)` and raises RuntimeError with a clear
operator message if non-zero — refuses to alter the column rather than
fail mid-migration with an FK / NOT NULL violation (CONTEXT §138, locked
tiger-style fail-loud).

Operations (in order):
  1. Pre-flight: SELECT COUNT(*) FROM tasks WHERE user_id IS NULL — raise
     RuntimeError if > 0.
  2. batch_alter_table('tasks'):
       - alter_column user_id to NOT NULL (existing FK fk_tasks_user_id is
         preserved by batch op)
       - create_index idx_tasks_user_id on (user_id) for SCOPE-02 lookups
         (per-user task queries land in Phase 13).

Downgrade reverses: drop index, then alter user_id back to nullable.

Code quality (locked, CONTEXT §65-71):
  DRY    — orphan-count SQL lives in a single named constant.
  SRP    — this revision adds NOT NULL + index; nothing else.
  tiger  — pre-flight refuses to run if guard violated (no silent skip).
  no nested ifs — flat guard clause inside upgrade().
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_tasks_user_id_not_null"
down_revision: Union[str, None] = "0002_auth_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COUNT_ORPHANS_SQL = "SELECT COUNT(*) FROM tasks WHERE user_id IS NULL"


def upgrade() -> None:
    """Tighten tasks.user_id to NOT NULL; create idx_tasks_user_id."""
    # Pre-flight: refuse to run if orphan rows remain.
    bind = op.get_bind()
    orphan_count = bind.execute(sa.text(_COUNT_ORPHANS_SQL)).scalar_one()
    if orphan_count > 0:
        raise RuntimeError(
            f"Refusing to apply 0003_tasks_user_id_not_null: "
            f"{orphan_count} tasks have user_id IS NULL. "
            f"Run `python -m app.cli backfill-tasks --admin-email <e>` first."
        )

    with op.batch_alter_table("tasks") as batch_op:
        batch_op.alter_column(
            "user_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.create_index("idx_tasks_user_id", ["user_id"])


def downgrade() -> None:
    """Reverse: drop index, restore user_id to nullable."""
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_index("idx_tasks_user_id")
        batch_op.alter_column(
            "user_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
