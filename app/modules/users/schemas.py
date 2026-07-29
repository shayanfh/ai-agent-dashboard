import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr
from app.core.permissions import UserRole


class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    role: UserRole = UserRole.OPERATOR
    company_id: Optional[uuid.UUID] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    id: uuid.UUID
    company_id: Optional[uuid.UUID]
    full_name: str
    email: str
    role: UserRole
    is_active: bool
    email_verified: bool
    email_verified_at: Optional[datetime]
    failed_login_attempts: int
    locked_until: Optional[datetime]
    last_login_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
