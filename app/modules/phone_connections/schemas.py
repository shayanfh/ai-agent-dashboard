import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.modules.onboarding.models import PhoneProvider, TelephonyConnectionStatus

E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


class SipConnectionConfig(BaseModel):
    allowed_addresses: list[str] = Field(default_factory=list, max_length=50)
    auth_username: str | None = Field(default=None, min_length=4, max_length=100)
    auth_password: str | None = Field(default=None, min_length=12, max_length=255)
    transport: str = Field(default="tcp", pattern="^(tcp|tls|udp)$")


class TwilioConnectionConfig(BaseModel):
    account_sid: str = Field(pattern=r"^AC[0-9a-fA-F]{32}$")
    auth_token: str = Field(min_length=16, max_length=255)
    phone_number_sid: str = Field(pattern=r"^PN[0-9a-fA-F]{32}$")


class PhoneConnectionCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    provider: PhoneProvider
    phone_number: str = Field(min_length=8, max_length=16)
    extension: str = Field(default="", max_length=20)
    agent_id: uuid.UUID | None = None
    sip: SipConnectionConfig | None = None
    twilio: TwilioConnectionConfig | None = None

    @model_validator(mode="after")
    def validate_provider_configuration(self) -> "PhoneConnectionCreate":
        self.phone_number = self.phone_number.strip()
        self.extension = self.extension.strip()
        if not E164_PATTERN.fullmatch(self.phone_number):
            raise ValueError("phone_number must use E.164 format, for example +14155550100")
        if self.provider == PhoneProvider.TWILIO and not self.twilio:
            raise ValueError("twilio configuration is required")
        if self.provider in (PhoneProvider.GENERIC_SIP, PhoneProvider.ASTERISK):
            self.sip = self.sip or SipConnectionConfig()
        if self.provider == PhoneProvider.MANAGED:
            raise ValueError("Managed-number inventory is not configured")
        return self


class PhoneConnectionResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    phone_number_id: uuid.UUID | None
    name: str | None
    provider: PhoneProvider | None
    status: TelephonyConnectionStatus
    phone_number: str | None = None
    extension: str = ""
    agent_id: uuid.UUID | None = None
    livekit_trunk_id: str | None
    dispatch_rule_id: str | None
    external_trunk_id: str | None
    configuration: dict | None
    last_error: str | None
    connected_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PhoneConnectionProvisionResponse(BaseModel):
    connection: PhoneConnectionResponse
    provider_setup: dict


class PhoneConnectionTestResponse(BaseModel):
    success: bool
    status: TelephonyConnectionStatus
    message: str

