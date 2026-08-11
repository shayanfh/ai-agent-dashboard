import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.types import EnumByValue


class TelephonyConnectionType(str, Enum):
    MANAGED_NUMBER = "managed_number"
    SIP_TRUNK = "sip_trunk"


class PhoneProvider(str, Enum):
    GENERIC_SIP = "generic_sip"
    TWILIO = "twilio"
    ASTERISK = "asterisk"
    MANAGED = "managed"


class SipConnectionMode(str, Enum):
    REGISTRATION = "registration"
    IP_TRUNK = "ip_trunk"


class TelephonyConnectionStatus(str, Enum):
    PENDING = "pending"
    PROVISIONING = "provisioning"
    TESTING = "testing"
    ACTIVE = "active"
    ERROR = "error"
    DISCONNECTED = "disconnected"
    AWAITING_PROVIDER_SETUP = "awaiting_provider_setup"
    REGISTERING = "registering"
    REJECTED = "rejected"


class TelephonyConnection(Base):
    __tablename__ = "telephony_connections"
    __table_args__ = (Index("ix_telephony_connections_company_id", "company_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    provider: Mapped[Optional[PhoneProvider]] = mapped_column(
        EnumByValue(PhoneProvider, "phone_provider"), nullable=True
    )
    connection_type: Mapped[TelephonyConnectionType] = mapped_column(
        EnumByValue(TelephonyConnectionType, "telephony_connection_type"), nullable=False
    )
    status: Mapped[TelephonyConnectionStatus] = mapped_column(
        EnumByValue(TelephonyConnectionStatus, "telephony_connection_status"),
        default=TelephonyConnectionStatus.PENDING,
    )
    configuration: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    credentials_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    livekit_trunk_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dispatch_rule_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    external_trunk_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    asterisk_resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    connected_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
