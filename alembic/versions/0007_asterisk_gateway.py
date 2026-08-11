"""Route all customer phone connections through shared Asterisk.

Revision ID: 0007_asterisk_gateway
Revises: 0006_website_forms
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_asterisk_gateway"
down_revision: str | None = "0006_website_forms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for value in ("awaiting_provider_setup", "registering"):
        op.execute(
            f"ALTER TYPE telephony_connection_status ADD VALUE IF NOT EXISTS '{value}'"
        )
    op.add_column(
        "telephony_connections",
        sa.Column("asterisk_resource_id", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("telephony_connections", "asterisk_resource_id")
    # PostgreSQL enum values are intentionally retained; removing enum values
    # requires rebuilding the type and is unsafe while rows may reference them.
