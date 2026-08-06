"""Add tenant billing, invoices, and payments.

Revision ID: 0005_billing_invoices
Revises: 0004_phone_connections
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_billing_invoices"
down_revision: str | None = "0004_phone_connections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    invoice_status = postgresql.ENUM(
        "open",
        "paid",
        "void",
        "uncollectible",
        name="invoice_status",
        create_type=False,
    )
    payment_status = postgresql.ENUM(
        "succeeded",
        "failed",
        "refunded",
        name="payment_status",
        create_type=False,
    )
    invoice_status.create(op.get_bind(), checkfirst=True)
    payment_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "plans",
        sa.Column(
            "price_monthly_minor", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.create_check_constraint(
        "ck_plans_price_monthly_nonnegative",
        "plans",
        "price_monthly_minor >= 0",
    )
    op.add_column(
        "plans",
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
    )
    op.add_column(
        "subscriptions",
        sa.Column("pending_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column(
            "cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "subscriptions",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_subscriptions_pending_plan_id",
        "subscriptions",
        "plans",
        ["pending_plan_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("number", sa.String(40), nullable=False),
        sa.Column("status", invoice_status, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("subtotal_minor", sa.Integer(), nullable=False),
        sa.Column("tax_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_minor", sa.Integer(), nullable=False),
        sa.Column("amount_paid_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amount_due_minor", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "subtotal_minor >= 0", name="ck_invoices_subtotal_nonnegative"
        ),
        sa.CheckConstraint("tax_minor >= 0", name="ck_invoices_tax_nonnegative"),
        sa.CheckConstraint("total_minor >= 0", name="ck_invoices_total_nonnegative"),
        sa.CheckConstraint(
            "amount_paid_minor >= 0", name="ck_invoices_amount_paid_nonnegative"
        ),
        sa.CheckConstraint(
            "amount_due_minor >= 0", name="ck_invoices_amount_due_nonnegative"
        ),
        sa.CheckConstraint(
            "total_minor = subtotal_minor + tax_minor",
            name="ck_invoices_total_components",
        ),
        sa.CheckConstraint(
            "amount_due_minor = total_minor - amount_paid_minor",
            name="ck_invoices_payment_balance",
        ),
        sa.UniqueConstraint("number"),
    )
    op.create_index(
        "ix_invoices_company_id_created_at",
        "invoices",
        ["company_id", "created_at"],
    )
    op.create_index("ix_invoices_status", "invoices", ["status"])

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", payment_status, nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("external_reference", sa.String(255), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount_minor > 0", name="ck_payments_amount_positive"),
        sa.UniqueConstraint("external_reference"),
    )
    op.create_index(
        "ix_payments_company_id_created_at",
        "payments",
        ["company_id", "created_at"],
    )
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_payments_invoice_id", table_name="payments")
    op.drop_index("ix_payments_company_id_created_at", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_invoices_status", table_name="invoices")
    op.drop_index("ix_invoices_company_id_created_at", table_name="invoices")
    op.drop_table("invoices")
    op.drop_constraint(
        "fk_subscriptions_pending_plan_id", "subscriptions", type_="foreignkey"
    )
    op.drop_column("subscriptions", "cancelled_at")
    op.drop_column("subscriptions", "cancel_at_period_end")
    op.drop_column("subscriptions", "pending_plan_id")
    op.drop_constraint(
        "ck_plans_price_monthly_nonnegative", "plans", type_="check"
    )
    op.drop_column("plans", "currency")
    op.drop_column("plans", "price_monthly_minor")
    postgresql.ENUM(name="payment_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="invoice_status").drop(op.get_bind(), checkfirst=True)
