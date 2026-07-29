from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user, CurrentUser
from app.modules.auth.schemas import (
    EmailInput,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    ResetPasswordRequest,
    SignupRequest,
    SignupResponse,
    TokenInput,
    TokenResponse,
    UserMeResponse,
    VerifyEmailResponse,
)
from app.modules.auth.service import AuthService
from app.core.rate_limit import enforce_rate_limit
from app.core.security import normalize_email

router = APIRouter()


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", maxsplit=1)[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/signup", response_model=SignupResponse, status_code=201)
async def signup(data: SignupRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(
        f"signup:{_client_ip(request)}",
        limit=5,
        window_seconds=3600,
    )
    return await AuthService(db).signup(data)


@router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(data: TokenInput, db: AsyncSession = Depends(get_db)):
    return await AuthService(db).verify_email(data.token)


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    data: EmailInput,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await enforce_rate_limit(
        f"resend:{_client_ip(request)}:{normalize_email(str(data.email))}",
        limit=3,
        window_seconds=3600,
    )
    await AuthService(db).resend_verification(str(data.email))
    return MessageResponse(
        message="If the account requires verification, a new email has been sent."
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    data: EmailInput,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await enforce_rate_limit(
        f"forgot:{_client_ip(request)}",
        limit=5,
        window_seconds=3600,
    )
    await AuthService(db).forgot_password(str(data.email))
    return MessageResponse(
        message="If an account exists for this email, reset instructions have been sent."
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    await AuthService(db).reset_password(data.token, data.new_password)
    return MessageResponse(message="Password has been reset successfully.")


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(
        f"login:{_client_ip(request)}:{normalize_email(str(data.email))}",
        limit=10,
        window_seconds=900,
    )
    service = AuthService(db)
    return await service.login(data)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    return await service.refresh(data.refresh_token)


@router.post("/logout")
async def logout(current_user: CurrentUser = Depends(get_current_user)):
    # JWT is stateless; client should discard tokens
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserMeResponse)
async def get_me(current_user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    return await service.get_me(current_user.user_id)
