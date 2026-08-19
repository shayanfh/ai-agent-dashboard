import uuid
from datetime import datetime, time

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.outbound_campaigns.models import (
    CampaignStatus,
    CampaignType,
    RecipientStatus,
)
from app.modules.website_forms.voice_preview import VoiceName


class CampaignCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    campaign_type: CampaignType
    phone_number_id: uuid.UUID
    agent_id: uuid.UUID | None = None
    message_text: str | None = Field(default=None, min_length=1, max_length=5000)
    voice: VoiceName = "coral"
    language: str = Field(default="en", min_length=2, max_length=10)
    timezone: str = Field(default="UTC", max_length=64)
    calling_window_start: time = time(9, 0)
    calling_window_end: time = time(18, 0)
    max_concurrency: int = Field(default=1, ge=1, le=20)
    max_attempts: int = Field(default=2, ge=1, le=5)
    retry_delay_minutes: int = Field(default=30, ge=1, le=1440)
    ring_timeout_seconds: int = Field(default=45, ge=15, le=120)
    keypad_actions: dict[str, str] | None = None
    settings: dict | None = None

    @field_validator("keypad_actions")
    @classmethod
    def validate_keypad_actions(
        cls, value: dict[str, str] | None
    ) -> dict[str, str] | None:
        for digit, action in (value or {}).items():
            if digit not in set("0123456789*#"):
                raise ValueError("keypad action keys must be DTMF digits")
            if action not in {"hangup", "repeat", "ai", "opt_out"} and (
                not action.startswith("extension:")
                or not action.removeprefix("extension:").isdigit()
            ):
                raise ValueError("unsupported keypad action")
        return value

    @model_validator(mode="after")
    def validate_type(self) -> "CampaignCreate":
        if self.campaign_type == CampaignType.AI_CONVERSATION and not self.agent_id:
            raise ValueError("agent_id is required for AI conversation campaigns")
        if self.campaign_type != CampaignType.AI_CONVERSATION and not self.message_text:
            raise ValueError("message_text is required for voice broadcast campaigns")
        if (
            self.campaign_type == CampaignType.VOICE_BROADCAST_KEYPAD
            and not self.keypad_actions
        ):
            raise ValueError("keypad_actions is required for keypad campaigns")
        if self.calling_window_start >= self.calling_window_end:
            raise ValueError("calling_window_start must be before calling_window_end")
        return self


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    agent_id: uuid.UUID | None = None
    message_text: str | None = Field(default=None, min_length=1, max_length=5000)
    voice: VoiceName | None = None
    language: str | None = Field(default=None, min_length=2, max_length=10)
    timezone: str | None = Field(default=None, max_length=64)
    calling_window_start: time | None = None
    calling_window_end: time | None = None
    max_concurrency: int | None = Field(default=None, ge=1, le=20)
    max_attempts: int | None = Field(default=None, ge=1, le=5)
    retry_delay_minutes: int | None = Field(default=None, ge=1, le=1440)
    ring_timeout_seconds: int | None = Field(default=None, ge=15, le=120)
    keypad_actions: dict[str, str] | None = None
    settings: dict | None = None

    _validate_keypad_actions = field_validator("keypad_actions")(
        CampaignCreate.validate_keypad_actions.__func__
    )


class CampaignScheduleRequest(BaseModel):
    scheduled_at: datetime

    @field_validator("scheduled_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("scheduled_at must include a timezone")
        return value


class CampaignResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    campaign_type: CampaignType
    status: CampaignStatus
    agent_id: uuid.UUID | None
    phone_number_id: uuid.UUID
    message_text: str | None
    voice: str
    language: str
    audio_ready: bool = False
    scheduled_at: datetime | None
    timezone: str
    calling_window_start: time
    calling_window_end: time
    max_concurrency: int
    max_attempts: int
    retry_delay_minutes: int
    ring_timeout_seconds: int
    keypad_actions: dict | None
    settings: dict | None
    total_recipients: int = 0
    completed_recipients: int = 0
    failed_recipients: int = 0
    created_at: datetime
    updated_at: datetime


class RecipientResponse(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    phone_number: str
    first_name: str | None
    last_name: str | None
    language: str | None
    timezone: str | None
    external_id: str | None
    consent_at: datetime | None
    custom_fields: dict | None
    status: RecipientStatus
    attempts_count: int
    next_attempt_at: datetime | None
    last_error: str | None
    last_call_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ImportErrorRow(BaseModel):
    row: int
    phone_number: str | None = None
    error: str


class ImportResponse(BaseModel):
    imported: int
    duplicates: int
    rejected: int
    errors: list[ImportErrorRow]


class CampaignValidationResponse(BaseModel):
    valid: bool
    total: int
    callable: int
    invalid: int
    do_not_call: int
    errors: list[str]


class AudioResponse(BaseModel):
    audio_ready: bool
    storage_key: str
    media_id: str


class AudioPlaybackResponse(BaseModel):
    url: str
    expires_in_seconds: int
    media_id: str


class AudioGenerateRequest(BaseModel):
    message_text: str = Field(min_length=1, max_length=5000)
    voice: VoiceName | None = None


class OutboundEventRequest(BaseModel):
    attempt_id: uuid.UUID
    status: RecipientStatus
    provider_call_id: str | None = None
    reason: str | None = None
    timestamp: datetime | None = None
    duration_seconds: int | None = Field(default=None, ge=0)


class SingleOutboundCallRequest(BaseModel):
    campaign_type: CampaignType
    phone_number_id: uuid.UUID
    destination_number: str
    agent_id: uuid.UUID | None = None
    message_text: str | None = Field(default=None, max_length=5000)
    voice: VoiceName = "coral"
    language: str = "en"


class CampaignTestCallRequest(BaseModel):
    destination_number: str


class DoNotCallCreate(BaseModel):
    phone_number: str
    reason: str | None = Field(default=None, max_length=500)


class DoNotCallResponse(BaseModel):
    id: uuid.UUID
    phone_number: str
    reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
