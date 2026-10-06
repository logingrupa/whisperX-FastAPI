"""api_key_unlimited — add per-key `unlimited` bypass flag to api_keys.

Revision ID: 0005_api_key_unlimited
Revises: 0004_api_key_usage_attribution
Create Date: 2026-06-20

Adds a single boolean column ``api_keys.unlimited``. When a transcription
request authenticates via a bearer key whose ``unlimited`` is true, the
FreeTierGate is bypassed entirely (no trial/file/model/diarize/rate/daily/
concurrency checks, no bucket consume). Limits remain per-user for every
other key; this flag is the ONLY per-key override and is operator-set
(no self-service endpoint in v1.2).

NOT NULL with server_default '0' (false) so every pre-existing key keeps
its current tier-bound behaviour with no backfill.

Code quality (locked, mirrors 0004):
  DRY   — single additive column; no copy-paste.
  SRP   — this revision only adds the bypass flag.
  tiger — additive + defaulted; no destructive step, no data migration.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_api_key_unlimited"
down_revision: Union[str, None] = "0004_api_key_usage_attribution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add NOT NULL boolean ``unlimited`` (default false) to api_keys."""
    with op.batch_alter_table("api_keys") as batch_op:
        batch_op.add_column(
            sa.Column(
                "unlimited",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    """Reverse: drop the ``unlimited`` column."""
    with op.batch_alter_table("api_keys") as batch_op:
        batch_op.drop_column("unlimited")
