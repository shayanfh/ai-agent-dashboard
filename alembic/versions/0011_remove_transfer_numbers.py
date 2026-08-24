"""Remove unused transfer-number settings from agents and phone numbers.

Revision ID: 0011_remove_transfer_numbers
Revises: 0010_outbound_campaigns
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_remove_transfer_numbers"
down_revision: str | None = "0010_outbound_campaigns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("agents", "transfer_number")
    op.drop_column("phone_numbers", "transfer_number")


def downgrade() -> None:
    op.add_column(
        "phone_numbers",
        sa.Column("transfer_number", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "agents",
        sa.Column("transfer_number", sa.String(length=50), nullable=True),
    )
