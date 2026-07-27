import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user, CurrentUser, require_super_admin
from app.modules.companies.schemas import CompanyCreate, CompanyUpdate, CompanyResponse
from app.modules.companies.service import CompanyService
from app.core.schemas import PaginatedResponse

router = APIRouter()


@router.get("", response_model=PaginatedResponse[CompanyResponse])
async def list_companies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    service = CompanyService(db)
    return await service.list_companies(current_user, page, page_size)


@router.post("", response_model=CompanyResponse, status_code=201)
async def create_company(
    data: CompanyCreate,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    service = CompanyService(db)
    return await service.create_company(data, current_user)


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = CompanyService(db)
    return await service.get_company(company_id, current_user)


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: uuid.UUID,
    data: CompanyUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = CompanyService(db)
    return await service.update_company(company_id, data, current_user)
