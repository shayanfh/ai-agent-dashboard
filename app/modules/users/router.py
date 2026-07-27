import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user, CurrentUser, require_company_admin
from app.modules.users.schemas import UserCreate, UserUpdate, UserResponse
from app.modules.users.service import UserService
from app.core.schemas import PaginatedResponse

router = APIRouter()


@router.get("", response_model=PaginatedResponse[UserResponse])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    return await service.list_users(current_user, page, page_size)


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    data: UserCreate,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    return await service.create_user(data, current_user)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    return await service.get_user(user_id, current_user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    data: UserUpdate,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    return await service.update_user(user_id, data, current_user)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    await service.delete_user(user_id, current_user)
