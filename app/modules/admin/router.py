import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser, require_super_admin
from app.core.schemas import PaginatedResponse
from app.modules.admin.schemas import (
    ClientOverviewResponse,
    PlanResponse,
    SubscriptionUpdate,
)
from app.modules.admin.service import AdminClientService
from app.modules.companies.models import CompanyStatus

router = APIRouter()


@router.get("/clients", response_model=PaginatedResponse[ClientOverviewResponse])
async def list_clients(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=255),
    status: CompanyStatus | None = None,
    plan_id: uuid.UUID | None = None,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await AdminClientService(db).list_clients(
        page, page_size, search, status, plan_id
    )


@router.get("/clients/{company_id}", response_model=ClientOverviewResponse)
async def get_client(
    company_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await AdminClientService(db).get_client(company_id)


@router.patch(
    "/clients/{company_id}/subscription", response_model=ClientOverviewResponse
)
async def update_subscription(
    company_id: uuid.UUID,
    data: SubscriptionUpdate,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await AdminClientService(db).update_subscription(company_id, data)


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await AdminClientService(db).list_plans()

