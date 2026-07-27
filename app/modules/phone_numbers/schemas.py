import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
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
