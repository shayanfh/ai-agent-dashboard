"""Add browser test-call source tracking.

Revision ID: 0013_web_test_calls
Revises: 0012_realtime_elevenlabs
"""

import sqlalchemy as sa
from alembic import op


revision: str = "0013_web_test_calls"
down_revision: str | None = "0012_realtime_elevenlabs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calls",
        sa.Column("source", sa.String(length=20), nullable=False, server_default="telephony"),
    )
    op.create_index("ix_calls_source", "calls", ["source"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_calls_source", table_name="calls")
    op.drop_column("calls", "source")
