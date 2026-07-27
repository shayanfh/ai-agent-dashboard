import uuid
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.modules.companies.models import Company, CompanyStatus


class CompanyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all(self, page: int = 1, page_size: int = 20) -> tuple[List[Company], int]:
        offset = (page - 1) * page_size
        count_result = await self.db.execute(select(func.count()).select_from(Company))
        total = count_result.scalar_one()
        result = await self.db.execute(
            select(Company).order_by(Company.created_at.desc()).offset(offset).limit(page_size)
        )
        return result.scalars().all(), total

    async def get_by_id(self, company_id: uuid.UUID) -> Optional[Company]:
        result = await self.db.execute(select(Company).where(Company.id == company_id))
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> Company:
        company = Company(**data)
        self.db.add(company)
        await self.db.commit()
        await self.db.refresh(company)
        return company

    async def update(self, company: Company, data: dict) -> Company:
        for key, value in data.items():
            setattr(company, key, value)
        await self.db.commit()
        await self.db.refresh(company)
        return company
