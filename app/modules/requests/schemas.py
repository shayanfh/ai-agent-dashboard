import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.modules.requests.models import RequestStatus, RequestType


class RequestCreate(BaseModel):
    call_id: Optional[uuid.UUID] = None
    agent_id: Optional[uuid.UUID] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    request_type: RequestType
    request_data: Optional[dict] = None


class RequestUpdate(BaseModel):
    status: Optional[RequestStatus] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    request_data: Optional[dict] = None
    external_reference: Optional[str] = None


class RequestResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    call_id: Optional[uuid.UUID]
    agent_id: Optional[uuid.UUID]
    customer_name: Optional[str]
    customer_phone: Optional[str]
    request_type: RequestType
    status: RequestStatus
    request_data: Optional[dict]
    external_reference: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
