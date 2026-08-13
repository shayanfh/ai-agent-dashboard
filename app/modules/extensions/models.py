import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.types import EnumByValue

if TYPE_CHECKING:
    from app.modules.companies.models import Company


class ExtensionStatus(str, Enum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


class Extension(Base):
    __tablename__ = "extensions"
    __table_args__ = (
        Index("ix_extensions_company_id", "company_id"),
        UniqueConstraint(
            "company_id", "extension", name="uq_extensions_company_number"
        ),
        UniqueConstraint("sip_username", name="uq_extensions_sip_username"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    extension: Mapped[str] = mapped_column(String(6), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    employee_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sip_username: Mapped[str] = mapped_column(String(100), nullable=False)
    sip_password_encrypted: Mapped[str] = mapped_column(String(1024), nullable=False)
    transport: Mapped[str] = mapped_column(String(10), default="udp", nullable=False)
    asterisk_resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[ExtensionStatus] = mapped_column(
        EnumByValue(ExtensionStatus, "extension_status"),
        default=ExtensionStatus.PROVISIONING,
        nullable=False,
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    company: Mapped["Company"] = relationship("Company", back_populates="extensions")
