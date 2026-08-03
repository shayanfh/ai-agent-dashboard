# ruff: noqa: B008
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser, require_company_admin
from app.core.schemas import PaginatedResponse
from app.modules.phone_connections.schemas import (
    PhoneConnectionCreate,
    PhoneConnectionProvisionResponse,
    PhoneConnectionResponse,
    PhoneConnectionTestResponse,
)
from app.modules.phone_connections.service import PhoneConnectionService

router = APIRouter()


@router.get("", response_model=PaginatedResponse[PhoneConnectionResponse])
async def list_phone_connections(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await PhoneConnectionService(db).list(current_user, page, page_size)


@router.post("", response_model=PhoneConnectionResponse, status_code=201)
async def create_phone_connection(
    data: PhoneConnectionCreate,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await PhoneConnectionService(db).create(data, current_user)


@router.get("/{connection_id}", response_model=PhoneConnectionResponse)
async def get_phone_connection(
    connection_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await PhoneConnectionService(db).get(connection_id, current_user)


@router.post(
    "/{connection_id}/provision", response_model=PhoneConnectionProvisionResponse
)
async def provision_phone_connection(
    connection_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await PhoneConnectionService(db).provision(connection_id, current_user)


@router.post("/{connection_id}/test", response_model=PhoneConnectionTestResponse)
async def test_phone_connection(
    connection_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await PhoneConnectionService(db).test(connection_id, current_user)


@router.post("/{connection_id}/disconnect", response_model=PhoneConnectionResponse)
async def disconnect_phone_connection(
    connection_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await PhoneConnectionService(db).disconnect(connection_id, current_user)
