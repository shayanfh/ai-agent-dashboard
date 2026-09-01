import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.modules.calls.models import Call, CallMessage, CallSource, CallStatus, CallOutcome


class CallRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_company(
        self,
        company_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        agent_id: Optional[uuid.UUID] = None,
        status: Optional[CallStatus] = None,
        outcome: Optional[CallOutcome] = None,
        caller_number: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        was_transferred: Optional[bool] = None,
        source: Optional[CallSource] = None,
    ) -> tuple[List[Call], int]:
        offset = (page - 1) * page_size
        query = select(Call).where(Call.company_id == company_id)
        if agent_id:
            query = query.where(Call.agent_id == agent_id)
        if status:
            query = query.where(Call.status == status)
        if outcome:
            query = query.where(Call.outcome == outcome)
        if caller_number:
            query = query.where(Call.caller_number.ilike(f"%{caller_number}%"))
        if date_from:
            query = query.where(Call.started_at >= date_from)
        if date_to:
            query = query.where(Call.started_at <= date_to)
        if was_transferred is not None:
            query = query.where(Call.was_transferred == was_transferred)
        if source is not None:
            query = query.where(Call.source == source)
        count_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar_one()
        result = await self.db.execute(
            query.order_by(Call.created_at.desc()).offset(offset).limit(page_size)
        )
        return result.scalars().all(), total

    async def get_by_id_and_company(self, call_id: uuid.UUID, company_id: uuid.UUID) -> Optional[Call]:
        result = await self.db.execute(
            select(Call)
            .options(
                selectinload(Call.messages),
                selectinload(Call.agent),
                selectinload(Call.phone_number_obj),
                selectinload(Call.request),
            )
            .where(Call.id == call_id, Call.company_id == company_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, call_id: uuid.UUID) -> Optional[Call]:
        result = await self.db.execute(select(Call).where(Call.id == call_id))
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> Call:
        call = Call(**data)
        self.db.add(call)
        await self.db.commit()
        await self.db.refresh(call)
        return call

    async def update(self, call: Call, data: dict) -> Call:
        for key, value in data.items():
            setattr(call, key, value)
        await self.db.commit()
        await self.db.refresh(call)
        return call

    async def add_message(self, data: dict) -> CallMessage:
        msg = CallMessage(**data)
        self.db.add(msg)
        await self.db.commit()
        await self.db.refresh(msg)
        return msg
