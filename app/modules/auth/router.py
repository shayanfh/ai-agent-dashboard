from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user, CurrentUser
from app.modules.auth.schemas import LoginRequest, TokenResponse, RefreshRequest, UserMeResponse
from app.modules.auth.service import AuthService

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
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
