import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from sqlalchemy import String, DateTime, Index, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class RequestStatus(str, Enum):
    NEW = "new"
    CONFIRMED = "confirmed"
    CONTACTED = "contacted"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class RequestType(str, Enum):
    CAR_BOOKING = "car_booking"
    TABLE_RESERVATION = "table_reservation"
    CALLBACK = "callback"
    SERVICE_REQUEST = "service_request"
    GENERAL_REQUEST = "general_request"


class Request(Base):
    __tablename__ = "requests"
    __table_args__ = (
        Index("ix_requests_company_id", "company_id"),
        Index("ix_requests_status", "status"),
        Index("ix_requests_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    call_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    customer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    customer_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    request_type: Mapped[RequestType] = mapped_column(
        SAEnum(RequestType, name="request_type"), nullable=False
    )
    status: Mapped[RequestStatus] = mapped_column(
        SAEnum(RequestStatus, name="request_status"), default=RequestStatus.NEW
    )
    request_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    external_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    company: Mapped["Company"] = relationship("Company", back_populates="requests")
    call: Mapped[Optional["Call"]] = relationship("Call", back_populates="request")
    agent: Mapped[Optional["Agent"]] = relationship("Agent")
