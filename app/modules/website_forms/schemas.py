import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, HttpUrl


class WebsitePayload(BaseModel):
    source: str = Field(default="website", max_length=64)
    form_type: str | None = Field(default=None, max_length=30)
    page_url: HttpUrl | None = None


class ContactCreate(WebsitePayload):
    name: str = Field(min_length=1, max_length=256)
    email: EmailStr
    company_name: str = Field(min_length=1, max_length=256)
    subject: str | None = Field(default=None, max_length=256)
    message: str | None = Field(default=None, max_length=5000)


class DemoRequestCreate(WebsitePayload):
    name: str = Field(min_length=1, max_length=256)
    email: EmailStr
    company_name: str = Field(min_length=1, max_length=256)
    monthly_call_volume: str | None = Field(default=None, max_length=256)
    industry: str | None = Field(default=None, max_length=256)
    current_systems: str | None = Field(default=None, max_length=1000)
    phone: str | None = Field(default=None, max_length=64)
    message: str | None = Field(default=None, max_length=5000)
    marketing_consent: bool = False


class NewsletterCreate(WebsitePayload):
    email: EmailStr
    marketing_consent: bool


class SubmissionResponse(BaseModel):
    id: uuid.UUID
    message: str
    created_at: datetime
