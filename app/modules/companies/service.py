import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.dependencies import CurrentUser
from app.modules.companies.repository import CompanyRepository
from app.modules.companies.schemas import CompanyCreate, CompanyUpdate, CompanyResponse
from app.core.schemas import PaginatedResponse
import math


class CompanyService:
    def __init__(self, db: AsyncSession):
        self.repo = CompanyRepository(db)

    async def list_companies(
        self, current_user: CurrentUser, page: int = 1, page_size: int = 20
    ) -> PaginatedResponse[CompanyResponse]:
        if not current_user.is_super_admin:
            raise PermissionDeniedError()
        companies, total = await self.repo.get_all(page, page_size)
        return PaginatedResponse(
            items=[CompanyResponse.model_validate(c) for c in companies],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def get_company(self, company_id: uuid.UUID, current_user: CurrentUser) -> CompanyResponse:
        if not current_user.is_super_admin:
            if str(current_user.company_id) != str(company_id):
                raise PermissionDeniedError()
        company = await self.repo.get_by_id(company_id)
        if not company:
            raise NotFoundError("Company not found")
        return CompanyResponse.model_validate(company)

    async def create_company(self, data: CompanyCreate, current_user: CurrentUser) -> CompanyResponse:
        if not current_user.is_super_admin:
            raise PermissionDeniedError()
        company = await self.repo.create(data.model_dump())
        return CompanyResponse.model_validate(company)

    async def update_company(
        self, company_id: uuid.UUID, data: CompanyUpdate, current_user: CurrentUser
    ) -> CompanyResponse:
        if not current_user.is_super_admin:
            if str(current_user.company_id) != str(company_id):
                raise PermissionDeniedError()
            # Operators/company admins cannot change status
            if data.status is not None and not current_user.is_super_admin:
                raise PermissionDeniedError("Only super admins can change company status")
        company = await self.repo.get_by_id(company_id)
        if not company:
            raise NotFoundError("Company not found")
        update_data = data.model_dump(exclude_none=True)
        company = await self.repo.update(company, update_data)
        return CompanyResponse.model_validate(company)
