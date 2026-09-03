"""Add Stripe billing identifiers and webhook idempotency.

Revision ID: 0014_stripe_billing
Revises: 0013_web_test_calls
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0014_stripe_billing"
down_revision: str | None = "0013_web_test_calls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("stripe_customer_id", sa.String(255), nullable=True))
    op.create_unique_constraint(
        "uq_companies_stripe_customer_id", "companies", ["stripe_customer_id"]
    )
    op.add_column("plans", sa.Column("stripe_price_id", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_plans_stripe_price_id", "plans", ["stripe_price_id"])
    op.add_column(
        "subscriptions", sa.Column("stripe_subscription_id", sa.String(255), nullable=True)
    )
    op.create_unique_constraint(
        "uq_subscriptions_stripe_subscription_id",
        "subscriptions",
        ["stripe_subscription_id"],
    )
    op.add_column("invoices", sa.Column("stripe_invoice_id", sa.String(255), nullable=True))
    op.add_column(
        "invoices", sa.Column("stripe_checkout_session_id", sa.String(255), nullable=True)
    )
    op.create_unique_constraint(
        "uq_invoices_stripe_invoice_id", "invoices", ["stripe_invoice_id"]
    )
    op.create_unique_constraint(
        "uq_invoices_stripe_checkout_session_id",
        "invoices",
        ["stripe_checkout_session_id"],
    )
    op.create_table(
        "stripe_events",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("event_type", sa.String(255), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("stripe_events")
    op.drop_constraint(
        "uq_invoices_stripe_checkout_session_id", "invoices", type_="unique"
    )
    op.drop_constraint("uq_invoices_stripe_invoice_id", "invoices", type_="unique")
    op.drop_column("invoices", "stripe_checkout_session_id")
    op.drop_column("invoices", "stripe_invoice_id")
    op.drop_constraint(
        "uq_subscriptions_stripe_subscription_id", "subscriptions", type_="unique"
    )
    op.drop_column("subscriptions", "stripe_subscription_id")
    op.drop_constraint("uq_plans_stripe_price_id", "plans", type_="unique")
    op.drop_column("plans", "stripe_price_id")
    op.drop_constraint("uq_companies_stripe_customer_id", "companies", type_="unique")
    op.drop_column("companies", "stripe_customer_id")
