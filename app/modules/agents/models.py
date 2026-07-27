import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from sqlalchemy import String, Text, DateTime, Boolean, Index, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class AgentStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (
        Index("ix_agents_company_id", "company_id"),
        Index("ix_agents_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="en")
    # ── Realtime mode ─────────────────────────────────────────────────────────
    # When True, a single realtime API (e.g. OpenAI Realtime) handles STT+LLM+TTS
    # in one WebSocket connection. realtime_provider/realtime_model are used instead
    # of the separate stt/llm/tts fields.
    use_realtime: Mapped[bool] = mapped_column(Boolean, default=False)
    realtime_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    realtime_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # ── Pipeline mode ─────────────────────────────────────────────────────────
    # When use_realtime=False, each stage uses its own provider/model.
    voice_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    voice_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tts_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tts_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    stt_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    stt_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    llm_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    llm_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    system_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    greeting_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transfer_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[AgentStatus] = mapped_column(
        SAEnum(AgentStatus, name="agent_status", values_callable=lambda x: [e.value for e in x]),
        default=AgentStatus.DRAFT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    company: Mapped["Company"] = relationship("Company", back_populates="agents")
    phone_numbers: Mapped[list] = relationship("PhoneNumber", back_populates="agent", lazy="noload")
    calls: Mapped[list] = relationship("Call", back_populates="agent", lazy="noload")
    knowledge_items: Mapped[list] = relationship("KnowledgeBaseItem", back_populates="agent", lazy="noload")
    knowledge_documents: Mapped[list] = relationship("KnowledgeDocument", back_populates="agent", lazy="noload")
