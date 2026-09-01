import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime, Integer, Index, ForeignKey, Float, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base
from app.core.types import EnumByValue

if TYPE_CHECKING:
    from app.modules.companies.models import Company
    from app.modules.agents.models import Agent
    from app.modules.phone_numbers.models import PhoneNumber
    from app.modules.requests.models import Request


class CallStatus(str, Enum):
    INITIATED = "initiated"
    RINGING = "ringing"
    ANSWERED = "answered"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    MISSED = "missed"
    FAILED = "failed"
    TRANSFERRED = "transferred"


class CallDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallSource(str, Enum):
    TELEPHONY = "telephony"
    WEB_TEST = "web_test"


class CallOutcome(str, Enum):
    BOOKING_CREATED = "booking_created"
    INFORMATION_REQUEST = "information_request"
    CALLBACK_REQUESTED = "callback_requested"
    NO_ACTION = "no_action"
    FAILED = "failed"


class Speaker(str, Enum):
    CALLER = "caller"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Call(Base):
    __tablename__ = "calls"
    __table_args__ = (
        Index("ix_calls_company_id", "company_id"),
        Index("ix_calls_agent_id", "agent_id"),
        Index("ix_calls_status", "status"),
        Index("ix_calls_started_at", "started_at"),
        Index("ix_calls_caller_number", "caller_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    phone_number_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("phone_numbers.id", ondelete="SET NULL"), nullable=True
    )
    campaign_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outbound_campaigns.id", ondelete="SET NULL"), nullable=True
    )
    recipient_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outbound_recipients.id", ondelete="SET NULL"), nullable=True
    )
    direction: Mapped[CallDirection] = mapped_column(
        EnumByValue(CallDirection, "call_direction"), default=CallDirection.INBOUND
    )
    source: Mapped[CallSource] = mapped_column(
        String(20), default=CallSource.TELEPHONY, nullable=False
    )
    caller_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    destination_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    livekit_room_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[CallStatus] = mapped_column(
        EnumByValue(CallStatus, "call_status"), default=CallStatus.INITIATED
    )
    outcome: Mapped[Optional[CallOutcome]] = mapped_column(
        EnumByValue(CallOutcome, "call_outcome"), nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    was_transferred: Mapped[bool] = mapped_column(Boolean, default=False)
    transfer_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    recording_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recording_duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    company: Mapped["Company"] = relationship("Company", back_populates="calls", lazy="raise")
    agent: Mapped[Optional["Agent"]] = relationship("Agent", back_populates="calls", lazy="raise")
    phone_number_obj: Mapped[Optional["PhoneNumber"]] = relationship("PhoneNumber", back_populates="calls", lazy="raise")
    messages: Mapped[list["CallMessage"]] = relationship(
        "CallMessage",
        back_populates="call",
        order_by="CallMessage.sequence",
        lazy="raise",
        uselist=True,
    )
    request: Mapped[Optional["Request"]] = relationship("Request", back_populates="call", uselist=False, lazy="raise")


class CallMessage(Base):
    __tablename__ = "call_messages"
    __table_args__ = (
        Index("ix_call_messages_company_id", "company_id"),
        Index("ix_call_messages_call_id", "call_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False
    )
    speaker: Mapped[Speaker] = mapped_column(EnumByValue(Speaker, "speaker_type"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    call: Mapped["Call"] = relationship("Call", back_populates="messages")
