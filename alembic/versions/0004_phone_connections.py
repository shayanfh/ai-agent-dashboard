"""Add self-service phone connection provisioning.

Revision ID: 0004_phone_connections
Revises: 0003_billing_admin
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_phone_connections"
down_revision: str | None = "0003_billing_admin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE phone_provider AS ENUM "
        "('generic_sip', 'twilio', 'asterisk', 'managed')"
    )
    for value in ("provisioning", "error", "disconnected"):
        op.execute(
            f"ALTER TYPE telephony_connection_status ADD VALUE IF NOT EXISTS '{value}'"
        )

    op.add_column("telephony_connections", sa.Column("name", sa.String(255), nullable=True))
    op.add_column(
        "telephony_connections",
        sa.Column(
            "provider",
            postgresql.ENUM(name="phone_provider", create_type=False),
            nullable=True,
        ),
    )
    op.add_column(
        "telephony_connections", sa.Column("credentials_encrypted", sa.Text(), nullable=True)
    )
    op.add_column(
        "telephony_connections", sa.Column("livekit_trunk_id", sa.String(255), nullable=True)
    )
    op.add_column(
        "telephony_connections", sa.Column("dispatch_rule_id", sa.String(255), nullable=True)
    )
    op.add_column(
        "telephony_connections", sa.Column("external_trunk_id", sa.String(255), nullable=True)
    )
    op.add_column("telephony_connections", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column(
        "telephony_connections",
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE phone_numbers SET extension = '' WHERE extension IS NULL")
    op.alter_column("phone_numbers", "extension", nullable=False, server_default="")
    op.add_column(
        "phone_numbers",
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_phone_numbers_connection_id",
        "phone_numbers",
        "telephony_connections",
        ["connection_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_phone_numbers_connection_id", "phone_numbers", ["connection_id"]
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM phone_numbers
                GROUP BY phone_number, extension HAVING COUNT(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'Cannot migrate: duplicate phone_number/extension mappings exist';
            END IF;
        END $$
        """
    )
    op.create_unique_constraint(
        "uq_phone_numbers_number_extension",
        "phone_numbers",
        ["phone_number", "extension"],
    )

    op.execute(
        """
        UPDATE telephony_connections
        SET provider = CASE
            WHEN connection_type = 'managed_number' THEN 'managed'::phone_provider
            ELSE 'generic_sip'::phone_provider
        END,
        name = COALESCE(name, 'Onboarding phone connection')
        WHERE provider IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint("uq_phone_numbers_number_extension", "phone_numbers", type_="unique")
    op.drop_constraint("uq_phone_numbers_connection_id", "phone_numbers", type_="unique")
    op.drop_constraint("fk_phone_numbers_connection_id", "phone_numbers", type_="foreignkey")
    op.drop_column("phone_numbers", "connection_id")
    op.alter_column("phone_numbers", "extension", nullable=True, server_default=None)

    for column in (
        "connected_at",
        "last_error",
        "external_trunk_id",
        "dispatch_rule_id",
        "livekit_trunk_id",
        "credentials_encrypted",
        "provider",
        "name",
    ):
        op.drop_column("telephony_connections", column)
    op.execute("DROP TYPE phone_provider")
