"""Add self-service signup, verification, and onboarding.

Revision ID: 0002_self_service_signup
Revises: 0001_initial_schema
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_self_service_signup"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE company_status ADD VALUE IF NOT EXISTS 'pending_verification'")
    op.execute("ALTER TYPE company_status ADD VALUE IF NOT EXISTS 'trial'")
    op.execute("ALTER TYPE company_status ADD VALUE IF NOT EXISTS 'cancelled'")

    op.add_column("companies", sa.Column("country", sa.String(2), nullable=True))
    op.add_column(
        "companies", sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "companies", sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "companies",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("companies", sa.Column("signup_source", sa.String(100), nullable=True))

    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True)
    )

    op.execute(
        """DO $$ BEGIN
        CREATE TYPE auth_token_type AS ENUM (
            'email_verification', 'password_reset', 'refresh_token'
        );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;"""
    )
    op.create_table(
        "auth_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "token_type",
            postgresql.ENUM(
                "email_verification",
                "password_reset",
                "refresh_token",
                name="auth_token_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_tokens_user_id", "auth_tokens", ["user_id"])
    op.create_index("ix_auth_tokens_hash", "auth_tokens", ["token_hash"], unique=True)
    op.create_index(
        "ix_auth_tokens_type_expires",
        "auth_tokens",
        ["token_type", "expires_at"],
    )

    op.execute(
        """DO $$ BEGIN
        CREATE TYPE telephony_connection_type AS ENUM ('managed_number', 'sip_trunk');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;"""
    )
    op.execute(
        """DO $$ BEGIN
        CREATE TYPE telephony_connection_status AS ENUM (
            'pending', 'testing', 'active', 'rejected'
        );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;"""
    )
    op.create_table(
        "telephony_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_type",
            postgresql.ENUM(
                "managed_number",
                "sip_trunk",
                name="telephony_connection_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "testing",
                "active",
                "rejected",
                name="telephony_connection_status",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("configuration", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_telephony_connections_company_id",
        "telephony_connections",
        ["company_id"],
    )


def downgrade() -> None:
    op.drop_table("telephony_connections")
    op.execute("DROP TYPE IF EXISTS telephony_connection_status")
    op.execute("DROP TYPE IF EXISTS telephony_connection_type")

    op.drop_table("auth_tokens")
    op.execute("DROP TYPE IF EXISTS auth_token_type")

    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email_verified")

    op.drop_column("companies", "signup_source")
    op.drop_column("companies", "onboarding_completed_at")
    op.drop_column("companies", "trial_ends_at")
    op.drop_column("companies", "trial_started_at")
    op.drop_column("companies", "country")
