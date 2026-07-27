import uuid
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.modules.phone_numbers.models import PhoneNumber


class PhoneNumberRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_company(self, company_id: uuid.UUID, page: int = 1, page_size: int = 20) -> tuple[List[PhoneNumber], int]:
        offset = (page - 1) * page_size
        query = select(PhoneNumber).where(PhoneNumber.company_id == company_id)
        count_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar_one()
        result = await self.db.execute(
            query.order_by(PhoneNumber.created_at.desc()).offset(offset).limit(page_size)
        )
        return result.scalars().all(), total

    async def get_by_id_and_company(self, phone_id: uuid.UUID, company_id: uuid.UUID) -> Optional[PhoneNumber]:
        result = await self.db.execute(
            select(PhoneNumber).where(PhoneNumber.id == phone_id, PhoneNumber.company_id == company_id)
        )
        return result.scalar_one_or_none()

    async def get_by_number(self, phone_number: str, extension: Optional[str] = None) -> Optional[PhoneNumber]:
        query = select(PhoneNumber).where(PhoneNumber.phone_number == phone_number, PhoneNumber.is_enabled == True)
        if extension:
            query = query.where(PhoneNumber.extension == extension)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> PhoneNumber:
        pn = PhoneNumber(**data)
        self.db.add(pn)
        await self.db.commit()
        await self.db.refresh(pn)
        return pn

    async def update(self, pn: PhoneNumber, data: dict) -> PhoneNumber:
        for key, value in data.items():
            setattr(pn, key, value)
        await self.db.commit()
        await self.db.refresh(pn)
        return pn

    async def delete(self, pn: PhoneNumber) -> None:
        await self.db.delete(pn)
        await self.db.commit()
