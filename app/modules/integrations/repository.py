import uuid
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.modules.integrations.models import Integration, IntegrationLog, IntegrationStatus


class IntegrationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_company(self, company_id: uuid.UUID, page: int = 1, page_size: int = 20) -> tuple[List[Integration], int]:
        offset = (page - 1) * page_size
        query = select(Integration).where(Integration.company_id == company_id)
        count_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar_one()
        result = await self.db.execute(
            query.order_by(Integration.created_at.desc()).offset(offset).limit(page_size)
        )
        return result.scalars().all(), total

    async def get_by_id_and_company(self, integration_id: uuid.UUID, company_id: uuid.UUID) -> Optional[Integration]:
        result = await self.db.execute(
            select(Integration).where(
                Integration.id == integration_id,
                Integration.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_connected_erpnext(self, company_id: uuid.UUID) -> Optional[Integration]:
        from app.modules.integrations.models import IntegrationType
        result = await self.db.execute(
            select(Integration).where(
                Integration.company_id == company_id,
                Integration.integration_type == IntegrationType.ERPNEXT,
                Integration.status == IntegrationStatus.CONNECTED,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> Integration:
        integration = Integration(**data)
        self.db.add(integration)
        await self.db.commit()
        await self.db.refresh(integration)
        return integration

    async def update(self, integration: Integration, data: dict) -> Integration:
        for k, v in data.items():
            setattr(integration, k, v)
        await self.db.commit()
        await self.db.refresh(integration)
        return integration

    async def delete(self, integration: Integration) -> None:
        await self.db.delete(integration)
        await self.db.commit()

    async def get_logs(self, integration_id: uuid.UUID, page: int = 1, page_size: int = 20) -> tuple[List[IntegrationLog], int]:
        offset = (page - 1) * page_size
        query = select(IntegrationLog).where(IntegrationLog.integration_id == integration_id)
        count_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar_one()
        result = await self.db.execute(
            query.order_by(IntegrationLog.created_at.desc()).offset(offset).limit(page_size)
        )
        return result.scalars().all(), total

    async def create_log(self, data: dict) -> IntegrationLog:
        log = IntegrationLog(**data)
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log
