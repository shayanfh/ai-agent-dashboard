import uuid
import math
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.dependencies import CurrentUser
from app.modules.agents.models import AgentStatus
from app.modules.agents.repository import AgentRepository
from app.modules.agents.schemas import AgentCreate, AgentUpdate, AgentResponse, AGENT_TEMPLATES, AgentTemplate
from app.core.schemas import PaginatedResponse


class AgentService:
    def __init__(self, db: AsyncSession):
        self.repo = AgentRepository(db)

    def _get_company_id(self, current_user: CurrentUser) -> uuid.UUID:
        if not current_user.company_id:
            raise PermissionDeniedError("No company context")
        return uuid.UUID(current_user.company_id)

    async def list_agents(
        self,
        current_user: CurrentUser,
        page: int = 1,
        page_size: int = 20,
        status: Optional[AgentStatus] = None,
        business_type: Optional[str] = None,
        language: Optional[str] = None,
        search: Optional[str] = None,
    ) -> PaginatedResponse[AgentResponse]:
        company_id = self._get_company_id(current_user)
        agents, total = await self.repo.get_by_company(
            company_id, page, page_size, status, business_type, language, search
        )
        return PaginatedResponse(
            items=[AgentResponse.model_validate(a) for a in agents],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def get_agent(self, agent_id: uuid.UUID, current_user: CurrentUser) -> AgentResponse:
        company_id = self._get_company_id(current_user)
        agent = await self.repo.get_by_id_and_company(agent_id, company_id)
        if not agent:
            raise NotFoundError("Agent not found")
        return AgentResponse.model_validate(agent)

    async def create_agent(self, data: AgentCreate, current_user: CurrentUser) -> AgentResponse:
        if not current_user.is_company_admin and not current_user.is_super_admin:
            raise PermissionDeniedError()
        company_id = self._get_company_id(current_user)
        agent_data = data.model_dump()
        agent_data["company_id"] = company_id
        agent = await self.repo.create(agent_data)
        return AgentResponse.model_validate(agent)

    async def update_agent(
        self, agent_id: uuid.UUID, data: AgentUpdate, current_user: CurrentUser
    ) -> AgentResponse:
        if not current_user.is_company_admin and not current_user.is_super_admin:
            raise PermissionDeniedError()
        company_id = self._get_company_id(current_user)
        agent = await self.repo.get_by_id_and_company(agent_id, company_id)
        if not agent:
            raise NotFoundError("Agent not found")
        agent = await self.repo.update(agent, data.model_dump(exclude_none=True))
        return AgentResponse.model_validate(agent)

    async def delete_agent(self, agent_id: uuid.UUID, current_user: CurrentUser) -> None:
        if not current_user.is_company_admin and not current_user.is_super_admin:
            raise PermissionDeniedError()
        company_id = self._get_company_id(current_user)
        agent = await self.repo.get_by_id_and_company(agent_id, company_id)
        if not agent:
            raise NotFoundError("Agent not found")
        await self.repo.delete(agent)

    def get_templates(self) -> list[AgentTemplate]:
        return AGENT_TEMPLATES
