import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.onboarding.models import PhoneProvider, TelephonyConnectionStatus
from app.modules.phone_connections.schemas import (
    PhoneConnectionCreate,
    PhoneConnectionTestResponse,
    SipConnectionConfig,
    TwilioConnectionConfig,
)
from app.modules.phone_numbers.models import ConnectionStatus


class PhoneNumberCreate(BaseModel):
    """Public phone-number input, including its optional provider connection."""

    phone_number: str
    agent_id: uuid.UUID | None = None
    operating_hours: dict | None = None
    is_enabled: bool = True
    name: str | None = Field(default=None, min_length=2, max_length=255)
    provider: PhoneProvider | None = None
    sip: SipConnectionConfig | None = None
    twilio: TwilioConnectionConfig | None = None

    @field_validator("phone_number", mode="before")
    @classmethod
    def normalize_routing_value(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value
        return value

    @model_validator(mode="after")
    def validate_connection(self) -> "PhoneNumberCreate":
        if self.provider is not None:
            PhoneConnectionCreate.model_validate(
                {
                    "name": self.name or f"{self.provider.value} {self.phone_number}",
                    "provider": self.provider,
                    "phone_number": self.phone_number,
                    "agent_id": self.agent_id,
                    "sip": self.sip,
                    "twilio": self.twilio,
                }
            )
        elif self.sip is not None or self.twilio is not None:
            raise ValueError(
                "provider is required when connection settings are supplied"
            )
        return self

    def to_connection_create(self) -> PhoneConnectionCreate:
        if self.provider is None:
            raise ValueError("provider is required")
        return PhoneConnectionCreate(
            name=self.name or f"{self.provider.value} {self.phone_number}",
            provider=self.provider,
            phone_number=self.phone_number,
            agent_id=self.agent_id,
            sip=self.sip,
            twilio=self.twilio,
        )


class PhoneNumberUpdate(BaseModel):
    phone_number: str | None = None
    agent_id: uuid.UUID | None = None
    operating_hours: dict | None = None
    is_enabled: bool | None = None
    name: str | None = Field(default=None, min_length=2, max_length=255)

    @field_validator("phone_number", mode="before")
    @classmethod
    def normalize_routing_value(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class PhoneNumberResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    agent_id: uuid.UUID | None
    connection_id: uuid.UUID | None
    name: str | None
    phone_number: str
    provider: PhoneProvider | None
    status: TelephonyConnectionStatus
    connection_status: ConnectionStatus
    sip_trunk_id: str | None
    external_trunk_id: str | None
    asterisk_resource_id: str | None
    livekit_trunk_id: str | None
    dispatch_rule_id: str | None
    configuration: dict | None
    last_error: str | None
    connected_at: datetime | None
    operating_hours: dict | None
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class PhoneNumberProvisionResponse(BaseModel):
    phone_number: PhoneNumberResponse
    provider_setup: dict


PhoneNumberTestResponse = PhoneConnectionTestResponse
