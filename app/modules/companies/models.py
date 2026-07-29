import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Text, JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base
from app.core.types import EnumByValue

if TYPE_CHECKING:
    from app.modules.billing.models import Subscription


class CompanyStatus(str, Enum):
    PENDING_VERIFICATION = "pending_verification"
    TRIAL = "trial"
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    default_language: Mapped[str] = mapped_column(String(10), default="en")
    timezone: Mapped[str] = mapped_column(String(100), default="UTC")
    phone_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    business_hours: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[CompanyStatus] = mapped_column(
        EnumByValue(CompanyStatus, "company_status"), default=CompanyStatus.ACTIVE
    )
    trial_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    onboarding_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    signup_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    users: Mapped[list["User"]] = relationship(
        "User", back_populates="company", lazy="noload", uselist=True
    )
    agents: Mapped[list["Agent"]] = relationship(
        "Agent", back_populates="company", lazy="noload", uselist=True
    )
    phone_numbers: Mapped[list["PhoneNumber"]] = relationship(
        "PhoneNumber", back_populates="company", lazy="noload", uselist=True
    )
    calls: Mapped[list["Call"]] = relationship(
        "Call", back_populates="company", lazy="noload", uselist=True
    )
    requests: Mapped[list["Request"]] = relationship(
        "Request", back_populates="company", lazy="noload", uselist=True
    )
    integrations: Mapped[list["Integration"]] = relationship(
        "Integration", back_populates="company", lazy="noload", uselist=True
    )
    subscription: Mapped[Optional["Subscription"]] = relationship(
        "Subscription", back_populates="company", uselist=False, lazy="noload"
    )
