import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator
from app.modules.phone_numbers.models import ConnectionStatus


class PhoneNumberCreate(BaseModel):
    phone_number: str
    extension: Optional[str] = None
    agent_id: Optional[uuid.UUID] = None
    provider: Optional[str] = None
    sip_trunk_id: Optional[str] = None
    livekit_trunk_id: Optional[str] = None
    dispatch_rule_id: Optional[str] = None
    transfer_number: Optional[str] = None
    operating_hours: Optional[dict] = None
    is_enabled: bool = True

    @field_validator("phone_number", "extension", mode="before")
    @classmethod
    def normalize_routing_value(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class PhoneNumberUpdate(BaseModel):
    phone_number: Optional[str] = None
    extension: Optional[str] = None
    agent_id: Optional[uuid.UUID] = None
    provider: Optional[str] = None
    sip_trunk_id: Optional[str] = None
    livekit_trunk_id: Optional[str] = None
    dispatch_rule_id: Optional[str] = None
    transfer_number: Optional[str] = None
    operating_hours: Optional[dict] = None
    connection_status: Optional[ConnectionStatus] = None
    is_enabled: Optional[bool] = None

    @field_validator("phone_number", "extension", mode="before")
    @classmethod
    def normalize_routing_value(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class PhoneNumberResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    agent_id: Optional[uuid.UUID]
    phone_number: str
    extension: Optional[str]
    provider: Optional[str]
    sip_trunk_id: Optional[str]
    livekit_trunk_id: Optional[str]
    dispatch_rule_id: Optional[str]
    transfer_number: Optional[str]
    operating_hours: Optional[dict]
    connection_status: ConnectionStatus
    is_enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
