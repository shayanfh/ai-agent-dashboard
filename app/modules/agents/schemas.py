import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator
from app.modules.agents.models import AgentStatus


REALTIME_PROVIDER = "openai"
REALTIME_MODEL = "gpt-realtime"
REALTIME_TTS_PROVIDER = "elevenlabs"
REALTIME_TTS_MODEL = "eleven_flash_v2_5"
DEFAULT_REALTIME_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"


class AgentCreate(BaseModel):
    model_config = {"extra": "forbid"}

    name: str
    business_type: Optional[str] = None
    language: str = "en"
    # ── Realtime mode ─────────────────────────────────────────────────────────
    use_realtime: bool = False
    # ── Pipeline mode ─────────────────────────────────────────────────────────
    voice_id: Optional[str] = Field(default=None, min_length=1, max_length=100)
    tts_provider: Optional[str] = None
    tts_model: Optional[str] = None
    stt_provider: Optional[str] = None
    stt_model: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    system_prompt: Optional[str] = None
    greeting_message: Optional[str] = None
    status: AgentStatus = AgentStatus.DRAFT


class AgentUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    name: Optional[str] = None
    business_type: Optional[str] = None
    language: Optional[str] = None
    use_realtime: Optional[bool] = None
    voice_id: Optional[str] = Field(default=None, min_length=1, max_length=100)
    tts_provider: Optional[str] = None
    tts_model: Optional[str] = None
    stt_provider: Optional[str] = None
    stt_model: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    system_prompt: Optional[str] = None
    greeting_message: Optional[str] = None
    status: Optional[AgentStatus] = None


class AgentResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    business_type: Optional[str]
    language: str
    use_realtime: bool
    realtime_provider: Optional[str]
    realtime_model: Optional[str]
    voice_provider: Optional[str]
    voice_id: Optional[str]
    tts_provider: Optional[str]
    tts_model: Optional[str]
    stt_provider: Optional[str]
    stt_model: Optional[str]
    llm_provider: Optional[str]
    llm_model: Optional[str]
    system_prompt: Optional[str]
    greeting_message: Optional[str]
    status: AgentStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ElevenLabsVoice(BaseModel):
    voice_id: str
    name: str
    category: str | None = None
    description: str | None = None
    preview_url: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    public_owner_id: str | None = None
    in_my_voices: bool = False

    @field_validator("labels", mode="before")
    @classmethod
    def normalize_nullable_labels(cls, value: Any) -> Any:
        return value or {}

class ElevenLabsVoiceListResponse(BaseModel):
    voices: list[ElevenLabsVoice]
    total: int
    cached: bool


class AgentTemplate(BaseModel):
    business_type: str
    name: str
    language: str
    use_realtime: bool = False
    # Realtime: OpenAI handles audio input and text output; ElevenLabs renders speech.
    realtime_provider: Optional[str] = None
    realtime_model: Optional[str] = None
    # Pipeline: separate providers per stage
    voice_provider: Optional[str] = None
    voice_id: Optional[str] = None
    tts_provider: Optional[str] = None
    tts_model: Optional[str] = None
    stt_provider: Optional[str] = None
    stt_model: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    system_prompt: str
    greeting_message: str


AGENT_TEMPLATES: list[AgentTemplate] = [
    # ── Realtime templates (single WebSocket, lowest latency) ─────────────────
    AgentTemplate(
        business_type="car_rental",
        name="Car Rental Booking Agent (Realtime)",
        language="en",
        use_realtime=True,
        realtime_provider=REALTIME_PROVIDER,
        realtime_model=REALTIME_MODEL,
        voice_provider=REALTIME_TTS_PROVIDER,
        voice_id=DEFAULT_REALTIME_VOICE_ID,
        tts_provider=REALTIME_TTS_PROVIDER,
        tts_model=REALTIME_TTS_MODEL,
        system_prompt=(
            "You are a professional car rental booking assistant. Help customers reserve vehicles. "
            "Collect: vehicle type, pickup location, pickup date, return date, and customer contact. "
            "Always confirm availability and provide pricing estimates."
        ),
        greeting_message="Welcome to our car rental service! How can I assist you today?",
    ),
    AgentTemplate(
        business_type="restaurant",
        name="Restaurant Reservation Agent (Realtime)",
        language="en",
        use_realtime=True,
        realtime_provider=REALTIME_PROVIDER,
        realtime_model=REALTIME_MODEL,
        voice_provider=REALTIME_TTS_PROVIDER,
        voice_id="21m00Tcm4TlvDq8ikWAM",
        tts_provider=REALTIME_TTS_PROVIDER,
        tts_model=REALTIME_TTS_MODEL,
        system_prompt=(
            "You are a friendly restaurant reservation assistant. Help customers make table reservations. "
            "Ask for: date, time, number of guests, and branch preference. "
            "Confirm the booking details before finalizing."
        ),
        greeting_message="Welcome! I'm your restaurant assistant. How can I help you today?",
    ),
    # ── Pipeline template (STT → LLM → TTS as separate stages) ───────────────
    AgentTemplate(
        business_type="customer_support",
        name="Customer Support Agent (Pipeline)",
        language="en",
        use_realtime=False,
        voice_provider="openai",
        voice_id="nova",
        tts_provider="openai",
        tts_model="tts-1",
        stt_provider="openai",
        stt_model="whisper-1",
        llm_provider="openai",
        llm_model="gpt-4.1-mini",
        system_prompt=(
            "You are a helpful customer support agent. Assist customers with inquiries, complaints, and service requests. "
            "Be empathetic and professional. Escalate complex issues to human agents when needed."
        ),
        greeting_message="Thank you for calling customer support. How can I help you today?",
    ),
]
