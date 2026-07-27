import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from app.modules.requests.models import Request, RequestStatus, RequestType


class RequestRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_company(
        self,
        company_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status: Optional[RequestStatus] = None,
        request_type: Optional[RequestType] = None,
        agent_id: Optional[uuid.UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
    ) -> tuple[List[Request], int]:
        offset = (page - 1) * page_size
        query = select(Request).where(Request.company_id == company_id)
        if status:
            query = query.where(Request.status == status)
        if request_type:
            query = query.where(Request.request_type == request_type)
        if agent_id:
            query = query.where(Request.agent_id == agent_id)
        if date_from:
            query = query.where(Request.created_at >= date_from)
        if date_to:
            query = query.where(Request.created_at <= date_to)
        if search:
            query = query.where(
                or_(
                    Request.customer_name.ilike(f"%{search}%"),
                    Request.customer_phone.ilike(f"%{search}%"),
                )
            )
        count_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar_one()
        result = await self.db.execute(
            query.order_by(Request.created_at.desc()).offset(offset).limit(page_size)
        )
        return result.scalars().all(), total

    async def get_by_id_and_company(self, req_id: uuid.UUID, company_id: uuid.UUID) -> Optional[Request]:
        result = await self.db.execute(
            select(Request).where(Request.id == req_id, Request.company_id == company_id)
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> Request:
        req = Request(**data)
        self.db.add(req)
        await self.db.commit()
        await self.db.refresh(req)
        return req

    async def update(self, req: Request, data: dict) -> Request:
        for key, value in data.items():
            setattr(req, key, value)
        await self.db.commit()
        await self.db.refresh(req)
        return req
