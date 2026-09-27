"""Add website profile fields to companies.

Revision ID: 0016_company_website_profile
Revises: 0015_stripe_plan_products
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0016_company_website_profile"
down_revision: str | None = "0015_stripe_plan_products"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("website_url", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "description")
    op.drop_column("companies", "website_url")
