"""Add plans and company subscriptions for the super-admin client report.

Revision ID: 0003_billing_admin
Revises: 0002_self_service_signup
"""

from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_billing_admin"
down_revision: Union[str, None] = "0002_self_service_signup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_PLAN_ID = "00000000-0000-0000-0000-000000000100"
TRIAL_PLAN_ID = "00000000-0000-0000-0000-000000000101"
STARTER_PLAN_ID = "00000000-0000-0000-0000-000000000102"
PROFESSIONAL_PLAN_ID = "00000000-0000-0000-0000-000000000103"


def upgrade() -> None:
    subscription_status = postgresql.ENUM(
        "trial",
        "active",
        "past_due",
        "cancelled",
        "expired",
        name="subscription_status",
        create_type=False,
    )
    subscription_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("monthly_minutes", sa.Integer(), nullable=True),
        sa.Column("max_agents", sa.Integer(), nullable=True),
        sa.Column("max_integrations", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            subscription_status,
            nullable=False,
            server_default="active",
        ),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subscriptions_company_id", "subscriptions", ["company_id"], unique=True)
    op.create_index("ix_subscriptions_plan_id", "subscriptions", ["plan_id"])

    plans = sa.table(
        "plans",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String()),
        sa.column("slug", sa.String()),
        sa.column("monthly_minutes", sa.Integer()),
        sa.column("max_agents", sa.Integer()),
        sa.column("max_integrations", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(
        plans,
        [
            {
                "id": uuid.UUID(LEGACY_PLAN_ID),
                "name": "Legacy",
                "slug": "legacy",
                "monthly_minutes": None,
                "max_agents": None,
                "max_integrations": None,
                "is_active": True,
            },
            {
                "id": uuid.UUID(TRIAL_PLAN_ID),
                "name": "Trial",
                "slug": "trial",
                "monthly_minutes": 200,
                "max_agents": 1,
                "max_integrations": 1,
                "is_active": True,
            },
            {
                "id": uuid.UUID(STARTER_PLAN_ID),
                "name": "Starter",
                "slug": "starter",
                "monthly_minutes": 500,
                "max_agents": 2,
                "max_integrations": 2,
                "is_active": True,
            },
            {
                "id": uuid.UUID(PROFESSIONAL_PLAN_ID),
                "name": "Professional",
                "slug": "professional",
                "monthly_minutes": 2000,
                "max_agents": 10,
                "max_integrations": 10,
                "is_active": True,
            },
        ],
    )
    op.execute(
        sa.text(
            """
            INSERT INTO subscriptions (
                id, company_id, plan_id, status,
                current_period_start, current_period_end, created_at, updated_at
            )
            SELECT
                id, id, :legacy_plan_id, 'active',
                date_trunc('month', now()),
                date_trunc('month', now()) + interval '1 month',
                now(), now()
            FROM companies
            """
        ).bindparams(
            sa.bindparam(
                "legacy_plan_id",
                value=uuid.UUID(LEGACY_PLAN_ID),
                type_=postgresql.UUID(as_uuid=True),
            )
        )
    )


def downgrade() -> None:
    op.drop_index("ix_subscriptions_plan_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_company_id", table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_table("plans")
    postgresql.ENUM(name="subscription_status").drop(op.get_bind(), checkfirst=True)
