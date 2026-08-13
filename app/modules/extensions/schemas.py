import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.extensions.models import ExtensionStatus


class ExtensionCreate(BaseModel):
    extension: str = Field(pattern=r"^[1-9][0-9]{1,5}$")
    display_name: str = Field(min_length=2, max_length=100)
    employee_name: str | None = Field(default=None, max_length=100)
    transport: str = Field(default="udp", pattern=r"^(udp|tcp|tls)$")


class ExtensionUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=100)
    employee_name: str | None = Field(default=None, max_length=100)


class ExtensionResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    extension: str
    display_name: str
    employee_name: str | None
    sip_username: str
    transport: str
    status: ExtensionStatus
    is_enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SipCredentials(BaseModel):
    server: str
    port: int
    transport: str
    username: str
    password: str
    extension: str


class ExtensionCredentialsResponse(BaseModel):
    extension: ExtensionResponse
    credentials: SipCredentials
