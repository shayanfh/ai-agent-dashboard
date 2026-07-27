import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Optional
from sqlalchemy import String, Text, DateTime, Integer, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base
from app.core.types import EnumByValue

if TYPE_CHECKING:
    from app.modules.companies.models import Company


class IntegrationType(str, Enum):
    ERPNEXT = "erpnext"
    WEBHOOK = "webhook"
    EMAIL = "email"
    WHATSAPP = "whatsapp"


class IntegrationStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    PENDING = "pending"


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (
        Index("ix_integrations_company_id", "company_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    integration_type: Mapped[IntegrationType] = mapped_column(
        EnumByValue(IntegrationType, "integration_type"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_secret_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    configuration: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    status: Mapped[IntegrationStatus] = mapped_column(
        EnumByValue(IntegrationStatus, "integration_status"), default=IntegrationStatus.PENDING
    )
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    company: Mapped["Company"] = relationship("Company", back_populates="integrations")
    logs: Mapped[list] = relationship("IntegrationLog", back_populates="integration", lazy="noload")


class IntegrationLog(Base):
    __tablename__ = "integration_logs"
    __table_args__ = (
        Index("ix_integration_logs_company_id", "company_id"),
        Index("ix_integration_logs_integration_id", "integration_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    integration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integrations.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    request_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    response_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    integration: Mapped["Integration"] = relationship("Integration", back_populates="logs")
