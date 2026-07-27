import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Index, Enum as SAEnum, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    PENDING = "pending"


class PhoneNumber(Base):
    __tablename__ = "phone_numbers"
    __table_args__ = (
        Index("ix_phone_numbers_company_id", "company_id"),
        Index("ix_phone_numbers_phone_number", "phone_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    phone_number: Mapped[str] = mapped_column(String(50), nullable=False)
    extension: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sip_trunk_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    livekit_trunk_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dispatch_rule_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    transfer_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    operating_hours: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    connection_status: Mapped[ConnectionStatus] = mapped_column(
        SAEnum(ConnectionStatus, name="connection_status"), default=ConnectionStatus.PENDING
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    company: Mapped["Company"] = relationship("Company", back_populates="phone_numbers")
    agent: Mapped[Optional["Agent"]] = relationship("Agent", back_populates="phone_numbers")
    calls: Mapped[list] = relationship("Call", back_populates="phone_number_obj", lazy="noload")
