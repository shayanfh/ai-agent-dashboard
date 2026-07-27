import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from sqlalchemy import String, Text, JSON, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class CompanyStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    default_language: Mapped[str] = mapped_column(String(10), default="en")
    timezone: Mapped[str] = mapped_column(String(100), default="UTC")
    phone_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    business_hours: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[CompanyStatus] = mapped_column(
        SAEnum(CompanyStatus, name="company_status"), default=CompanyStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    users: Mapped[list] = relationship("User", back_populates="company", lazy="noload")
    agents: Mapped[list] = relationship("Agent", back_populates="company", lazy="noload")
    phone_numbers: Mapped[list] = relationship("PhoneNumber", back_populates="company", lazy="noload")
    calls: Mapped[list] = relationship("Call", back_populates="company", lazy="noload")
    requests: Mapped[list] = relationship("Request", back_populates="company", lazy="noload")
    integrations: Mapped[list] = relationship("Integration", back_populates="company", lazy="noload")
