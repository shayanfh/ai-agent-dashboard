import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user, CurrentUser, require_company_admin
from app.modules.integrations.schemas import (
    IntegrationCreate, IntegrationUpdate, IntegrationResponse,
    IntegrationLogResponse, TestConnectionResponse,
)
from app.modules.integrations.service import IntegrationService
from app.core.schemas import PaginatedResponse

router = APIRouter()


@router.get("", response_model=PaginatedResponse[IntegrationResponse])
async def list_integrations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = IntegrationService(db)
    return await service.list_integrations(current_user, page, page_size)


@router.post("", response_model=IntegrationResponse, status_code=201)
async def create_integration(
    data: IntegrationCreate,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = IntegrationService(db)
    return await service.create_integration(data, current_user)


@router.get("/{integration_id}", response_model=IntegrationResponse)
async def get_integration(
    integration_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = IntegrationService(db)
    return await service.get_integration(integration_id, current_user)


@router.patch("/{integration_id}", response_model=IntegrationResponse)
async def update_integration(
    integration_id: uuid.UUID,
    data: IntegrationUpdate,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = IntegrationService(db)
    return await service.update_integration(integration_id, data, current_user)


@router.delete("/{integration_id}", status_code=204)
async def delete_integration(
    integration_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = IntegrationService(db)
    await service.delete_integration(integration_id, current_user)


@router.post("/{integration_id}/test", response_model=TestConnectionResponse)
async def test_connection(
    integration_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = IntegrationService(db)
    return await service.test_connection(integration_id, current_user)


@router.post("/{integration_id}/connect", response_model=IntegrationResponse)
async def connect_integration(
    integration_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = IntegrationService(db)
    return await service.connect(integration_id, current_user)


@router.post("/{integration_id}/disconnect", response_model=IntegrationResponse)
async def disconnect_integration(
    integration_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = IntegrationService(db)
    return await service.disconnect(integration_id, current_user)


@router.get("/{integration_id}/logs", response_model=PaginatedResponse[IntegrationLogResponse])
async def get_logs(
    integration_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = IntegrationService(db)
    return await service.get_logs(integration_id, current_user, page, page_size)
