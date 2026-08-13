"""Add tenant SIP extensions and separate them from phone numbers.

Revision ID: 0008_employee_extensions
Revises: 0007_asterisk_gateway
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_employee_extensions"
down_revision: str | None = "0007_asterisk_gateway"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT phone_number
                FROM phone_numbers
                GROUP BY phone_number
                HAVING COUNT(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'Duplicate phone_numbers must be consolidated before migration 0008';
            END IF;
        END $$;
        """
    )
    extension_status = postgresql.ENUM(
        "provisioning",
        "active",
        "disabled",
        "error",
        name="extension_status",
        create_type=False,
    )
    extension_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "extensions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("extension", sa.String(6), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("employee_name", sa.String(100), nullable=True),
        sa.Column("sip_username", sa.String(100), nullable=False),
        sa.Column("sip_password_encrypted", sa.String(1024), nullable=False),
        sa.Column("transport", sa.String(10), nullable=False),
        sa.Column("asterisk_resource_id", sa.String(255), nullable=True),
        sa.Column("status", extension_status, nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id", "extension", name="uq_extensions_company_number"
        ),
        sa.UniqueConstraint("sip_username", name="uq_extensions_sip_username"),
    )
    op.create_index("ix_extensions_company_id", "extensions", ["company_id"])
    op.drop_constraint(
        "uq_phone_numbers_number_extension", "phone_numbers", type_="unique"
    )
    op.drop_column("phone_numbers", "extension")
    op.create_unique_constraint(
        "uq_phone_numbers_number", "phone_numbers", ["phone_number"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_phone_numbers_number", "phone_numbers", type_="unique")
    op.add_column(
        "phone_numbers",
        sa.Column("extension", sa.String(20), nullable=False, server_default=""),
    )
    op.create_unique_constraint(
        "uq_phone_numbers_number_extension",
        "phone_numbers",
        ["phone_number", "extension"],
    )
    op.drop_index("ix_extensions_company_id", table_name="extensions")
    op.drop_table("extensions")
    postgresql.ENUM(name="extension_status").drop(op.get_bind(), checkfirst=True)
