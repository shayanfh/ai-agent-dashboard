import uuid
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.modules.agents.models import Agent, AgentStatus


class AgentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_company(
        self,
        company_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status: Optional[AgentStatus] = None,
        business_type: Optional[str] = None,
        language: Optional[str] = None,
        search: Optional[str] = None,
    ) -> tuple[List[Agent], int]:
        offset = (page - 1) * page_size
        query = select(Agent).where(Agent.company_id == company_id)
        if status:
            query = query.where(Agent.status == status)
        if business_type:
            query = query.where(Agent.business_type == business_type)
        if language:
            query = query.where(Agent.language == language)
        if search:
            query = query.where(Agent.name.ilike(f"%{search}%"))
        count_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar_one()
        result = await self.db.execute(
            query.order_by(Agent.created_at.desc()).offset(offset).limit(page_size)
        )
        return result.scalars().all(), total

    async def get_by_id(self, agent_id: uuid.UUID) -> Optional[Agent]:
        result = await self.db.execute(select(Agent).where(Agent.id == agent_id))
        return result.scalar_one_or_none()

    async def get_by_id_and_company(self, agent_id: uuid.UUID, company_id: uuid.UUID) -> Optional[Agent]:
        result = await self.db.execute(
            select(Agent).where(Agent.id == agent_id, Agent.company_id == company_id)
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> Agent:
        agent = Agent(**data)
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def update(self, agent: Agent, data: dict) -> Agent:
        for key, value in data.items():
            setattr(agent, key, value)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def delete(self, agent: Agent) -> None:
        await self.db.delete(agent)
        await self.db.commit()
