import uuid
from typing import Optional
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.permissions import UserRole
from app.core.security import decode_token

security = HTTPBearer()


class CurrentUser:
    def __init__(self, user_id: str, company_id: Optional[str], role: str):
        self.user_id = user_id
        self.company_id = company_id
        self.role = role

    @property
    def is_super_admin(self) -> bool:
        return self.role == UserRole.SUPER_ADMIN

    @property
    def is_company_admin(self) -> bool:
        return self.role == UserRole.COMPANY_ADMIN

    @property
    def is_operator(self) -> bool:
        return self.role == UserRole.OPERATOR


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> CurrentUser:
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise AuthenticationError("Invalid token type")
        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Invalid token payload")
        return CurrentUser(
            user_id=user_id,
            company_id=payload.get("company_id"),
            role=payload.get("role"),
        )
    except JWTError:
        raise AuthenticationError("Invalid or expired token")


async def require_super_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not current_user.is_super_admin:
        raise PermissionDeniedError("Super admin access required")
    return current_user


async def require_company_admin(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current_user.role not in (UserRole.SUPER_ADMIN, UserRole.COMPANY_ADMIN):
        raise PermissionDeniedError("Company admin access required")
    return current_user


async def require_any_role(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return current_user


class TenantDependency:
    """Ensures all queries are scoped to the authenticated user's company."""

    def __init__(self, current_user: CurrentUser = Depends(get_current_user)):
        if not current_user.is_super_admin and not current_user.company_id:
            raise AuthenticationError("No company context")
        self.company_id = current_user.company_id
        self.current_user = current_user


async def get_tenant(
    current_user: CurrentUser = Depends(get_current_user),
) -> TenantDependency:
    return TenantDependency(current_user=current_user)


async def verify_internal_api_key(x_internal_api_key: str = Header(...)) -> None:
    if x_internal_api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal API key")
