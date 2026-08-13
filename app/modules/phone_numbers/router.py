# ruff: noqa: B008
import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser, get_current_user, require_company_admin
from app.core.schemas import PaginatedResponse
from app.modules.phone_numbers.schemas import (
    PhoneNumberCreate,
    PhoneNumberProvisionResponse,
    PhoneNumberResponse,
    PhoneNumberTestResponse,
    PhoneNumberUpdate,
)
from app.modules.phone_numbers.service import PhoneNumberService

router = APIRouter()


@router.get("", response_model=PaginatedResponse[PhoneNumberResponse])
async def list_phone_numbers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await PhoneNumberService(db).list_phone_numbers(
        current_user, page, page_size
    )


@router.post("", response_model=PhoneNumberResponse, status_code=201)
async def create_phone_number(
    data: PhoneNumberCreate,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await PhoneNumberService(db).create_phone_number(data, current_user)


@router.get("/{phone_id}", response_model=PhoneNumberResponse)
async def get_phone_number(
    phone_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await PhoneNumberService(db).get_phone_number(phone_id, current_user)


@router.patch("/{phone_id}", response_model=PhoneNumberResponse)
async def update_phone_number(
    phone_id: uuid.UUID,
    data: PhoneNumberUpdate,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await PhoneNumberService(db).update_phone_number(
        phone_id, data, current_user
    )


@router.post(
    "/{phone_id}/provision", response_model=PhoneNumberProvisionResponse
)
async def provision_phone_number(
    phone_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await PhoneNumberService(db).provision(phone_id, current_user)


@router.post("/{phone_id}/test", response_model=PhoneNumberTestResponse)
async def test_phone_number(
    phone_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await PhoneNumberService(db).test(phone_id, current_user)


@router.post("/{phone_id}/disconnect", response_model=PhoneNumberResponse)
async def disconnect_phone_number(
    phone_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await PhoneNumberService(db).disconnect(phone_id, current_user)


@router.delete("/{phone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_phone_number(
    phone_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await PhoneNumberService(db).delete_phone_number(phone_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{phone_id}/enable", response_model=PhoneNumberResponse)
async def enable_phone_number(
    phone_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await PhoneNumberService(db).set_enabled(phone_id, True, current_user)


@router.post("/{phone_id}/disable", response_model=PhoneNumberResponse)
async def disable_phone_number(
    phone_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await PhoneNumberService(db).set_enabled(phone_id, False, current_user)
