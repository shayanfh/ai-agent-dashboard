from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserMeResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    company_id: str | None
    is_active: bool
    email_verified: bool

    model_config = {"from_attributes": True}


class SignupRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str
    company_name: str = Field(min_length=2, max_length=255)
    business_type: str = Field(min_length=2, max_length=100)
    phone_number: str = Field(min_length=5, max_length=50)
    country: str = Field(min_length=2, max_length=2)
    default_language: str = Field(default="en", min_length=2, max_length=10)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    signup_source: Optional[str] = Field(default="self_service", max_length=100)


class SignupResponse(BaseModel):
    message: str
    company_id: str
    user_id: str
    email: str
    verification_required: bool = True


class TokenInput(BaseModel):
    token: str = Field(min_length=20)


class VerifyEmailResponse(TokenResponse):
    message: str = "Email verified successfully"


class EmailInput(BaseModel):
    email: EmailStr


class MessageResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20)
    new_password: str
