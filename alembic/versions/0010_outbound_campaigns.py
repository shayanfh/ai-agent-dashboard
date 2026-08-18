"""Add outbound campaigns, recipients, attempts, and call direction.

Revision ID: 0010_outbound_campaigns
Revises: 0009_knowledge_pipeline
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010_outbound_campaigns"
down_revision: str | None = "0009_knowledge_pipeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str):
    enum = postgresql.ENUM(*values, name=name, create_type=False)
    enum.create(op.get_bind(), checkfirst=True)
    return enum


def upgrade() -> None:
    campaign_type = _enum(
        "outbound_campaign_type",
        "ai_conversation",
        "voice_broadcast",
        "voice_broadcast_keypad",
    )
    campaign_status = _enum(
        "outbound_campaign_status",
        "draft",
        "ready",
        "scheduled",
        "running",
        "paused",
        "completed",
        "cancelled",
        "failed",
    )
    recipient_status = _enum(
        "outbound_recipient_status",
        "pending",
        "queued",
        "dialing",
        "ringing",
        "answered",
        "completed",
        "busy",
        "no_answer",
        "failed",
        "cancelled",
        "do_not_call",
    )
    call_direction = _enum("call_direction", "inbound", "outbound")

    op.create_table(
        "outbound_campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("campaign_type", campaign_type, nullable=False),
        sa.Column("status", campaign_status, nullable=False),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "phone_number_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("phone_numbers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("message_text", sa.Text(), nullable=True),
        sa.Column("voice", sa.String(50), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("audio_storage_key", sa.Text(), nullable=True),
        sa.Column("audio_media_id", sa.String(100), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("calling_window_start", sa.Time(), nullable=False),
        sa.Column("calling_window_end", sa.Time(), nullable=False),
        sa.Column("max_concurrency", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("retry_delay_minutes", sa.Integer(), nullable=False),
        sa.Column("ring_timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("keypad_actions", postgresql.JSONB(), nullable=True),
        sa.Column("settings", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_outbound_campaigns_company_status",
        "outbound_campaigns",
        ["company_id", "status"],
    )
    op.create_index(
        "ix_outbound_campaigns_scheduled_at", "outbound_campaigns", ["scheduled_at"]
    )

    op.create_table(
        "outbound_recipients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("outbound_campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phone_number", sa.String(50), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("custom_fields", postgresql.JSONB(), nullable=True),
        sa.Column("status", recipient_status, nullable=False),
        sa.Column("attempts_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "last_call_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("calls.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "campaign_id", "phone_number", name="uq_outbound_recipient_campaign_phone"
        ),
    )
    op.create_index(
        "ix_outbound_recipients_campaign_status",
        "outbound_recipients",
        ["campaign_id", "status"],
    )
    op.create_index(
        "ix_outbound_recipients_company_phone",
        "outbound_recipients",
        ["company_id", "phone_number"],
    )

    op.create_table(
        "outbound_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "campaign_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("outbound_campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recipient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("outbound_recipients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "call_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("calls.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", recipient_status, nullable=False),
        sa.Column("provider_call_id", sa.String(255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "recipient_id",
            "attempt_number",
            name="uq_outbound_attempt_recipient_number",
        ),
    )
    op.create_index(
        "ix_outbound_attempts_campaign", "outbound_attempts", ["campaign_id"]
    )

    op.create_table(
        "do_not_call_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phone_number", sa.String(50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "phone_number", name="uq_dnc_company_phone"),
    )

    op.add_column(
        "calls", sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "calls", sa.Column("recipient_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "calls",
        sa.Column(
            "direction", call_direction, server_default="inbound", nullable=False
        ),
    )
    op.add_column(
        "calls", sa.Column("destination_number", sa.String(50), nullable=True)
    )
    op.create_foreign_key(
        "fk_calls_campaign",
        "calls",
        "outbound_campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_calls_recipient",
        "calls",
        "outbound_recipients",
        ["recipient_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("calls", "direction", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_calls_recipient", "calls", type_="foreignkey")
    op.drop_constraint("fk_calls_campaign", "calls", type_="foreignkey")
    for column in ("destination_number", "direction", "recipient_id", "campaign_id"):
        op.drop_column("calls", column)
    op.drop_table("do_not_call_entries")
    op.drop_index("ix_outbound_attempts_campaign", table_name="outbound_attempts")
    op.drop_table("outbound_attempts")
    op.drop_index(
        "ix_outbound_recipients_company_phone", table_name="outbound_recipients"
    )
    op.drop_index(
        "ix_outbound_recipients_campaign_status", table_name="outbound_recipients"
    )
    op.drop_table("outbound_recipients")
    op.drop_index("ix_outbound_campaigns_scheduled_at", table_name="outbound_campaigns")
    op.drop_index(
        "ix_outbound_campaigns_company_status", table_name="outbound_campaigns"
    )
    op.drop_table("outbound_campaigns")
    for name in (
        "call_direction",
        "outbound_recipient_status",
        "outbound_campaign_status",
        "outbound_campaign_type",
    ):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
