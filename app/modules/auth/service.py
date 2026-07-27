import logging
from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.exceptions import AuthenticationError
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import LoginRequest, TokenResponse, UserMeResponse
from app.modules.companies.models import CompanyStatus
from jose import JWTError

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.repo = AuthRepository(db)

    async def login(self, data: LoginRequest) -> TokenResponse:
        user = await self.repo.get_user_by_email(data.email)
        if not user or not verify_password(data.password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")
        if not user.is_active:
            raise AuthenticationError("User account is disabled")
        if user.company_id:
            from sqlalchemy.ext.asyncio import AsyncSession
            from sqlalchemy import select
            from app.modules.companies.models import Company
            db = self.repo.db
            result = await db.execute(select(Company).where(Company.id == user.company_id))
            company = result.scalar_one_or_none()
            if company and company.status != CompanyStatus.ACTIVE:
                raise AuthenticationError("Company account is not active")
        await self.repo.update_last_login(str(user.id))
        access_token = create_access_token(
            user_id=str(user.id),
            company_id=str(user.company_id) if user.company_id else None,
            role=user.role.value,
        )
        refresh_token = create_refresh_token(user_id=str(user.id))
        logger.info(f"User {user.email} logged in")
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    async def refresh(self, refresh_token: str) -> TokenResponse:
        try:
            payload = decode_token(refresh_token)
            if payload.get("type") != "refresh":
                raise AuthenticationError("Invalid token type")
            user_id = payload.get("sub")
        except JWTError:
            raise AuthenticationError("Invalid or expired refresh token")
        user = await self.repo.get_user_by_id(user_id)
        if not user or not user.is_active:
            raise AuthenticationError("User not found or disabled")
        access_token = create_access_token(
            user_id=str(user.id),
            company_id=str(user.company_id) if user.company_id else None,
            role=user.role.value,
        )
        new_refresh = create_refresh_token(user_id=str(user.id))
        return TokenResponse(access_token=access_token, refresh_token=new_refresh)

    async def get_me(self, user_id: str) -> UserMeResponse:
        user = await self.repo.get_user_by_id(user_id)
        if not user:
            raise AuthenticationError("User not found")
        return UserMeResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
            company_id=str(user.company_id) if user.company_id else None,
            is_active=user.is_active,
        )
