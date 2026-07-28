import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.modules.calls.models import CallStatus, CallOutcome, Speaker


class CallCreate(BaseModel):
    agent_id: Optional[uuid.UUID] = None
    phone_number_id: Optional[uuid.UUID] = None
    caller_number: Optional[str] = None
    livekit_room_name: Optional[str] = None
    started_at: Optional[datetime] = None


class CallUpdate(BaseModel):
    status: Optional[CallStatus] = None
    outcome: Optional[CallOutcome] = None
    answered_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    was_transferred: Optional[bool] = None
    transfer_number: Optional[str] = None
    recording_url: Optional[str] = None
    recording_duration_seconds: Optional[int] = None
    summary: Optional[str] = None
    extracted_data: Optional[dict] = None
    metadata_: Optional[dict] = None


class CallCompleteRequest(BaseModel):
    summary: Optional[str] = None
    outcome: CallOutcome
    was_transferred: bool = False
    transfer_number: Optional[str] = None
    extracted_data: Optional[dict] = None
    recording_url: Optional[str] = None
    recording_duration_seconds: Optional[int] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None


class CallMessageCreate(BaseModel):
    speaker: Speaker
    text: str
    sequence: int
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    confidence: Optional[float] = None


class CallMessageResponse(BaseModel):
    id: uuid.UUID
    call_id: uuid.UUID
    speaker: Speaker
    text: str
    sequence: int
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    confidence: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentBrief(BaseModel):
    id: uuid.UUID
    name: str
    business_type: Optional[str]

    model_config = {"from_attributes": True}


class PhoneNumberBrief(BaseModel):
    id: uuid.UUID
    phone_number: str

    model_config = {"from_attributes": True}


class RequestBrief(BaseModel):
    id: uuid.UUID
    request_type: str
    status: str
    customer_name: Optional[str]

    model_config = {"from_attributes": True}


class CallResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    agent_id: Optional[uuid.UUID]
    phone_number_id: Optional[uuid.UUID]
    caller_number: Optional[str]
    livekit_room_name: Optional[str]
    status: CallStatus
    outcome: Optional[CallOutcome]
    started_at: Optional[datetime]
    answered_at: Optional[datetime]
    ended_at: Optional[datetime]
    duration_seconds: Optional[int]
    was_transferred: bool
    transfer_number: Optional[str]
    recording_url: Optional[str]
    recording_duration_seconds: Optional[int]
    summary: Optional[str]
    extracted_data: Optional[dict]
    metadata_: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CallDetailResponse(CallResponse):
    messages: list[CallMessageResponse] = Field(default_factory=list)
    agent: Optional[AgentBrief] = None
    phone_number: Optional[PhoneNumberBrief] = Field(
        default=None,
        validation_alias="phone_number_obj",
    )
    request: Optional[RequestBrief] = None
