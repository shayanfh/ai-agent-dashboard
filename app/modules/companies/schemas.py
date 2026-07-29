import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr
from app.modules.companies.models import CompanyStatus


class CompanyCreate(BaseModel):
    name: str
    logo_url: Optional[str] = None
    business_type: Optional[str] = None
    default_language: str = "en"
    timezone: str = "UTC"
    phone_number: Optional[str] = None
    country: Optional[str] = None
    email: Optional[EmailStr] = None
    business_hours: Optional[dict] = None


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    business_type: Optional[str] = None
    default_language: Optional[str] = None
    timezone: Optional[str] = None
    phone_number: Optional[str] = None
    country: Optional[str] = None
    email: Optional[EmailStr] = None
    business_hours: Optional[dict] = None
    status: Optional[CompanyStatus] = None


class CompanyResponse(BaseModel):
    id: uuid.UUID
    name: str
    logo_url: Optional[str]
    business_type: Optional[str]
    default_language: str
    timezone: str
    phone_number: Optional[str]
    country: Optional[str]
    email: Optional[str]
    business_hours: Optional[dict]
    status: CompanyStatus
    trial_started_at: Optional[datetime]
    trial_ends_at: Optional[datetime]
    onboarding_completed_at: Optional[datetime]
    signup_source: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
