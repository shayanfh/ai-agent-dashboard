import uuid
from datetime import datetime, time, timezone
from enum import Enum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import EnumByValue


class CampaignType(str, Enum):
    AI_CONVERSATION = "ai_conversation"
    VOICE_BROADCAST = "voice_broadcast"
    VOICE_BROADCAST_KEYPAD = "voice_broadcast_keypad"


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class RecipientStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    DIALING = "dialing"
    RINGING = "ringing"
    ANSWERED = "answered"
    COMPLETED = "completed"
    BUSY = "busy"
    NO_ANSWER = "no_answer"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DO_NOT_CALL = "do_not_call"


class OutboundCampaign(Base):
    __tablename__ = "outbound_campaigns"
    __table_args__ = (
        Index("ix_outbound_campaigns_company_status", "company_id", "status"),
        Index("ix_outbound_campaigns_scheduled_at", "scheduled_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    campaign_type: Mapped[CampaignType] = mapped_column(
        EnumByValue(CampaignType, "outbound_campaign_type"), nullable=False
    )
    status: Mapped[CampaignStatus] = mapped_column(
        EnumByValue(CampaignStatus, "outbound_campaign_status"),
        default=CampaignStatus.DRAFT,
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    phone_number_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("phone_numbers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    message_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice: Mapped[str] = mapped_column(String(50), default="coral")
    language: Mapped[str] = mapped_column(String(10), default="en")
    audio_storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_media_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    calling_window_start: Mapped[time] = mapped_column(Time(), default=time(9, 0))
    calling_window_end: Mapped[time] = mapped_column(Time(), default=time(18, 0))
    max_concurrency: Mapped[int] = mapped_column(Integer, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, default=2)
    retry_delay_minutes: Mapped[int] = mapped_column(Integer, default=30)
    ring_timeout_seconds: Mapped[int] = mapped_column(Integer, default=45)
    keypad_actions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class OutboundRecipient(Base):
    __tablename__ = "outbound_recipients"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "phone_number", name="uq_outbound_recipient_campaign_phone"
        ),
        Index("ix_outbound_recipients_campaign_status", "campaign_id", "status"),
        Index("ix_outbound_recipients_company_phone", "company_id", "phone_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("outbound_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    phone_number: Mapped[str] = mapped_column(String(50), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    custom_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[RecipientStatus] = mapped_column(
        EnumByValue(RecipientStatus, "outbound_recipient_status"),
        default=RecipientStatus.PENDING,
    )
    attempts_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_call_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("calls.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class OutboundAttempt(Base):
    __tablename__ = "outbound_attempts"
    __table_args__ = (
        UniqueConstraint(
            "recipient_id",
            "attempt_number",
            name="uq_outbound_attempt_recipient_number",
        ),
        Index("ix_outbound_attempts_campaign", "campaign_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("outbound_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("outbound_recipients.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    call_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="SET NULL"), nullable=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[RecipientStatus] = mapped_column(
        EnumByValue(RecipientStatus, "outbound_recipient_status"),
        default=RecipientStatus.QUEUED,
    )
    provider_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class DoNotCallEntry(Base):
    __tablename__ = "do_not_call_entries"
    __table_args__ = (
        UniqueConstraint("company_id", "phone_number", name="uq_dnc_company_phone"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    phone_number: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
