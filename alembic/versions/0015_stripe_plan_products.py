"""Store Stripe Product identifiers for automatically managed plans.

Revision ID: 0015_stripe_plan_products
Revises: 0014_stripe_billing
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0015_stripe_plan_products"
down_revision: str | None = "0014_stripe_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plans", sa.Column("stripe_product_id", sa.String(255), nullable=True)
    )
    op.create_unique_constraint(
        "uq_plans_stripe_product_id", "plans", ["stripe_product_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_plans_stripe_product_id", "plans", type_="unique")
    op.drop_column("plans", "stripe_product_id")
