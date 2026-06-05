"""api_key_usage_attribution — add nullable api_key_id to tasks + usage_events.

Revision ID: 0004_api_key_usage_attribution
Revises: 0003_tasks_user_id_not_null
Create Date: 2026-06-06

Enables per-API-key usage attribution on /dashboard/usage. A transcription
request authenticated via a bearer key stamps the resolving ``api_key_id``
onto its task; the worker copies it onto the ``usage_events`` row it writes.

Both columns are NULLABLE on purpose:
  - Pre-existing tasks / usage_events predate attribution -> NULL ("unattributed").
  - Cookie/session-authenticated transcriptions have no API key -> NULL.

FK uses ON DELETE SET NULL so revoking/deleting a key preserves the usage
history (the row survives, attribution drops to "unattributed").

Code quality (locked, mirrors 0003):
  DRY    — single helper per table; no copy-pasted column spec.
  SRP    — this revision only adds attribution columns + one index.
  tiger  — additive + nullable; no data backfill, no destructive step.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_api_key_usage_attribution"
down_revision: Union[str, None] = "0003_tasks_user_id_not_null"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable api_key_id FK to tasks + usage_events; index the latter."""
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("api_key_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_tasks_api_key_id",
            "api_keys",
            ["api_key_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("usage_events") as batch_op:
        batch_op.add_column(sa.Column("api_key_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_usage_events_api_key_id",
            "api_keys",
            ["api_key_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("idx_usage_events_api_key_id", ["api_key_id"])


def downgrade() -> None:
    """Reverse: drop index + FK + column on both tables."""
    with op.batch_alter_table("usage_events") as batch_op:
        batch_op.drop_index("idx_usage_events_api_key_id")
        batch_op.drop_constraint("fk_usage_events_api_key_id", type_="foreignkey")
        batch_op.drop_column("api_key_id")

    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_constraint("fk_tasks_api_key_id", type_="foreignkey")
        batch_op.drop_column("api_key_id")
