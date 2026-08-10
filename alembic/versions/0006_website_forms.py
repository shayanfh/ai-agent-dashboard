"""Add website contact, demo, and newsletter storage.

Revision ID: 0006_website_forms
Revises: 0005_billing_invoices
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_website_forms"
down_revision: str | None = "0005_billing_invoices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "website_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("company_name", sa.String(256), nullable=False),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("subject", sa.String(256), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("marketing_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("source", sa.String(64), nullable=False, server_default="website"),
        sa.Column("page_url", sa.String(2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_website_submissions_kind_created_at", "website_submissions", ["kind", "created_at"])
    op.create_index("ix_website_submissions_email", "website_submissions", ["email"])

    op.create_table(
        "newsletter_subscribers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("marketing_consent", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source", sa.String(64), nullable=False, server_default="website"),
        sa.Column("page_url", sa.String(2048), nullable=True),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_newsletter_subscribers_email", "newsletter_subscribers", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_newsletter_subscribers_email", table_name="newsletter_subscribers")
    op.drop_table("newsletter_subscribers")
    op.drop_index("ix_website_submissions_email", table_name="website_submissions")
    op.drop_index("ix_website_submissions_kind_created_at", table_name="website_submissions")
    op.drop_table("website_submissions")
