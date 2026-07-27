import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.modules.integrations.models import IntegrationType, IntegrationStatus


class IntegrationCreate(BaseModel):
    integration_type: IntegrationType
    name: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    configuration: Optional[dict] = None


class IntegrationUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    configuration: Optional[dict] = None
    status: Optional[IntegrationStatus] = None


class IntegrationResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    integration_type: IntegrationType
    name: str
    base_url: Optional[str]
    configuration: Optional[dict]
    status: IntegrationStatus
    last_sync_at: Optional[datetime]
    last_error: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IntegrationLogResponse(BaseModel):
    id: uuid.UUID
    integration_id: uuid.UUID
    event_type: str
    status: str
    request_payload: Optional[dict]
    response_payload: Optional[dict]
    error_message: Optional[str]
    retry_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
    details: Optional[dict] = None
