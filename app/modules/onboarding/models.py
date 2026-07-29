import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import EnumByValue


class TelephonyConnectionType(str, Enum):
    MANAGED_NUMBER = "managed_number"
    SIP_TRUNK = "sip_trunk"


class TelephonyConnectionStatus(str, Enum):
    PENDING = "pending"
    TESTING = "testing"
    ACTIVE = "active"
    REJECTED = "rejected"


class TelephonyConnection(Base):
    __tablename__ = "telephony_connections"
    __table_args__ = (Index("ix_telephony_connections_company_id", "company_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    connection_type: Mapped[TelephonyConnectionType] = mapped_column(
        EnumByValue(TelephonyConnectionType, "telephony_connection_type"), nullable=False
    )
    status: Mapped[TelephonyConnectionStatus] = mapped_column(
        EnumByValue(TelephonyConnectionStatus, "telephony_connection_status"),
        default=TelephonyConnectionStatus.PENDING,
    )
    configuration: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
