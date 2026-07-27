"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-27

"""
from typing import Union
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ENUM types ────────────────────────────────────────────────────────────
    op.execute("""DO $$ BEGIN CREATE TYPE company_status AS ENUM ('active', 'inactive', 'suspended'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;""")
    op.execute("""DO $$ BEGIN CREATE TYPE user_role AS ENUM ('super_admin', 'company_admin', 'operator'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;""")
    op.execute("""DO $$ BEGIN CREATE TYPE agent_status AS ENUM ('active', 'inactive', 'draft'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;""")
    op.execute("""DO $$ BEGIN CREATE TYPE connection_status AS ENUM ('connected', 'disconnected', 'error', 'pending'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;""")
    op.execute("""DO $$ BEGIN CREATE TYPE call_status AS ENUM ('initiated', 'ringing', 'answered', 'in_progress', 'completed', 'missed', 'failed', 'transferred'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;""")
    op.execute("""DO $$ BEGIN CREATE TYPE call_outcome AS ENUM ('booking_created', 'information_request', 'callback_requested', 'no_action', 'failed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;""")
    op.execute("""DO $$ BEGIN CREATE TYPE speaker_type AS ENUM ('caller', 'assistant', 'system'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;""")
    op.execute("""DO $$ BEGIN CREATE TYPE request_type AS ENUM ('car_booking', 'table_reservation', 'callback', 'service_request', 'general_request'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;""")
    op.execute("""DO $$ BEGIN CREATE TYPE request_status AS ENUM ('new', 'confirmed', 'contacted', 'cancelled', 'completed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;""")
    op.execute("""DO $$ BEGIN CREATE TYPE kb_item_status AS ENUM ('active', 'inactive'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;""")
    op.execute("""DO $$ BEGIN CREATE TYPE doc_processing_status AS ENUM ('pending', 'processing', 'completed', 'failed'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;""")
    op.execute("""DO $$ BEGIN CREATE TYPE integration_type AS ENUM ('erpnext', 'webhook', 'email', 'whatsapp'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;""")
    op.execute("""DO $$ BEGIN CREATE TYPE integration_status AS ENUM ('connected', 'disconnected', 'error', 'pending'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;""")

    # ── companies ─────────────────────────────────────────────────────────────
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("logo_url", sa.Text, nullable=True),
        sa.Column("business_type", sa.String(100), nullable=True),
        sa.Column("default_language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("timezone", sa.String(100), nullable=False, server_default="UTC"),
        sa.Column("phone_number", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("business_hours", postgresql.JSONB, nullable=True),
        sa.Column("status", postgresql.ENUM("active", "inactive", "suspended",name="company_status", create_type=False), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", postgresql.ENUM("super_admin", "company_admin", "operator",name="user_role", create_type=False), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_company_id", "users", ["company_id"])

    # ── agents ────────────────────────────────────────────────────────────────
    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("business_type", sa.String(100), nullable=True),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        # Realtime mode
        sa.Column("use_realtime", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("realtime_provider", sa.String(50), nullable=True),
        sa.Column("realtime_model", sa.String(100), nullable=True),
        # Pipeline mode
        sa.Column("voice_provider", sa.String(50), nullable=True),
        sa.Column("voice_id", sa.String(100), nullable=True),
        sa.Column("tts_provider", sa.String(50), nullable=True),
        sa.Column("tts_model", sa.String(100), nullable=True),
        sa.Column("stt_provider", sa.String(50), nullable=True),
        sa.Column("stt_model", sa.String(100), nullable=True),
        sa.Column("llm_provider", sa.String(50), nullable=True),
        sa.Column("llm_model", sa.String(100), nullable=True),
        sa.Column("system_prompt", sa.Text, nullable=True),
        sa.Column("greeting_message", sa.Text, nullable=True),
        sa.Column("transfer_number", sa.String(50), nullable=True),
        sa.Column("status", postgresql.ENUM("active", "inactive", "draft",name="agent_status", create_type=False), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agents_company_id", "agents", ["company_id"])
    op.create_index("ix_agents_status", "agents", ["status"])

    # ── phone_numbers ─────────────────────────────────────────────────────────
    op.create_table(
        "phone_numbers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("phone_number", sa.String(50), nullable=False),
        sa.Column("extension", sa.String(20), nullable=True),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("sip_trunk_id", sa.String(255), nullable=True),
        sa.Column("livekit_trunk_id", sa.String(255), nullable=True),
        sa.Column("dispatch_rule_id", sa.String(255), nullable=True),
        sa.Column("transfer_number", sa.String(50), nullable=True),
        sa.Column("operating_hours", postgresql.JSONB, nullable=True),
        sa.Column("connection_status", postgresql.ENUM("connected", "disconnected", "error", "pending",name="connection_status", create_type=False), nullable=False, server_default="pending"),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_phone_numbers_company_id", "phone_numbers", ["company_id"])
    op.create_index("ix_phone_numbers_phone_number", "phone_numbers", ["phone_number"])

    # ── calls ─────────────────────────────────────────────────────────────────
    op.create_table(
        "calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("phone_number_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("phone_numbers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("caller_number", sa.String(50), nullable=True),
        sa.Column("livekit_room_name", sa.String(255), nullable=True),
        sa.Column("status", postgresql.ENUM("initiated", "ringing", "answered", "in_progress", "completed", "missed", "failed", "transferred",name="call_status", create_type=False), nullable=False, server_default="initiated"),
        sa.Column("outcome", postgresql.ENUM("booking_created", "information_request", "callback_requested", "no_action", "failed",name="call_outcome", create_type=False), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("was_transferred", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("transfer_number", sa.String(50), nullable=True),
        sa.Column("recording_url", sa.Text, nullable=True),
        sa.Column("recording_duration_seconds", sa.Integer, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("extracted_data", postgresql.JSONB, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_calls_company_id", "calls", ["company_id"])
    op.create_index("ix_calls_agent_id", "calls", ["agent_id"])
    op.create_index("ix_calls_status", "calls", ["status"])
    op.create_index("ix_calls_started_at", "calls", ["started_at"])
    op.create_index("ix_calls_caller_number", "calls", ["caller_number"])

    # ── call_messages ─────────────────────────────────────────────────────────
    op.create_table(
        "call_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("call_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("speaker", postgresql.ENUM("caller", "assistant", "system",name="speaker_type", create_type=False), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_call_messages_company_id", "call_messages", ["company_id"])
    op.create_index("ix_call_messages_call_id", "call_messages", ["call_id"])

    # ── requests ──────────────────────────────────────────────────────────────
    op.create_table(
        "requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("call_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("calls.id", ondelete="SET NULL"), nullable=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("customer_name", sa.String(255), nullable=True),
        sa.Column("customer_phone", sa.String(50), nullable=True),
        sa.Column("request_type", postgresql.ENUM("car_booking", "table_reservation", "callback", "service_request", "general_request",name="request_type", create_type=False), nullable=False),
        sa.Column("status", postgresql.ENUM("new", "confirmed", "contacted", "cancelled", "completed",name="request_status", create_type=False), nullable=False, server_default="new"),
        sa.Column("request_data", postgresql.JSONB, nullable=True),
        sa.Column("external_reference", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_requests_company_id", "requests", ["company_id"])
    op.create_index("ix_requests_status", "requests", ["status"])
    op.create_index("ix_requests_created_at", "requests", ["created_at"])

    # ── knowledge_base_items ──────────────────────────────────────────────────
    op.create_table(
        "knowledge_base_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("status", postgresql.ENUM("active", "inactive",name="kb_item_status", create_type=False), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_kb_items_company_id", "knowledge_base_items", ["company_id"])
    op.create_index("ix_kb_items_agent_id", "knowledge_base_items", ["agent_id"])

    # ── knowledge_documents ───────────────────────────────────────────────────
    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(50), nullable=True),
        sa.Column("file_url", sa.Text, nullable=True),
        sa.Column("processing_status", postgresql.ENUM("pending", "processing", "completed", "failed",name="doc_processing_status", create_type=False), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_kb_docs_company_id", "knowledge_documents", ["company_id"])
    op.create_index("ix_kb_docs_agent_id", "knowledge_documents", ["agent_id"])

    # ── integrations ──────────────────────────────────────────────────────────
    op.create_table(
        "integrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("integration_type", postgresql.ENUM("erpnext", "webhook", "email", "whatsapp",name="integration_type", create_type=False), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("base_url", sa.Text, nullable=True),
        sa.Column("api_key_encrypted", sa.Text, nullable=True),
        sa.Column("api_secret_encrypted", sa.Text, nullable=True),
        sa.Column("configuration", postgresql.JSONB, nullable=True),
        sa.Column("status", postgresql.ENUM("connected", "disconnected", "error", "pending",name="integration_status", create_type=False), nullable=False, server_default="pending"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_integrations_company_id", "integrations", ["company_id"])

    # ── integration_logs ──────────────────────────────────────────────────────
    op.create_table(
        "integration_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("request_payload", postgresql.JSONB, nullable=True),
        sa.Column("response_payload", postgresql.JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_integration_logs_company_id", "integration_logs", ["company_id"])
    op.create_index("ix_integration_logs_integration_id", "integration_logs", ["integration_id"])


def downgrade() -> None:
    op.drop_table("integration_logs")
    op.drop_table("integrations")
    op.drop_table("knowledge_documents")
    op.drop_table("knowledge_base_items")
    op.drop_table("requests")
    op.drop_table("call_messages")
    op.drop_table("calls")
    op.drop_table("phone_numbers")
    op.drop_table("agents")
    op.drop_table("users")
    op.drop_table("companies")

    op.execute("DROP TYPE IF EXISTS integration_status")
    op.execute("DROP TYPE IF EXISTS integration_type")
    op.execute("DROP TYPE IF EXISTS doc_processing_status")
    op.execute("DROP TYPE IF EXISTS kb_item_status")
    op.execute("DROP TYPE IF EXISTS request_status")
    op.execute("DROP TYPE IF EXISTS request_type")
    op.execute("DROP TYPE IF EXISTS speaker_type")
    op.execute("DROP TYPE IF EXISTS call_outcome")
    op.execute("DROP TYPE IF EXISTS call_status")
    op.execute("DROP TYPE IF EXISTS connection_status")
    op.execute("DROP TYPE IF EXISTS agent_status")
    op.execute("DROP TYPE IF EXISTS user_role")
    op.execute("DROP TYPE IF EXISTS company_status")