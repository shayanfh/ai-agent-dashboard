import uuid
import math
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.dependencies import CurrentUser
from app.modules.agents.models import AgentStatus
from app.modules.agents.repository import AgentRepository
from app.modules.agents.schemas import (
    AGENT_TEMPLATES,
    DEFAULT_REALTIME_VOICE_ID,
    REALTIME_MODEL,
    REALTIME_PROVIDER,
    REALTIME_TTS_MODEL,
    REALTIME_TTS_PROVIDER,
    AgentCreate,
    AgentResponse,
    AgentTemplate,
    AgentUpdate,
)
from app.core.schemas import PaginatedResponse


class AgentService:
    def __init__(self, db: AsyncSession):
        self.repo = AgentRepository(db)

    def _get_company_id(self, current_user: CurrentUser) -> uuid.UUID:
        if not current_user.company_id:
            raise PermissionDeniedError("No company context")
        return uuid.UUID(current_user.company_id)

    @staticmethod
    def _apply_realtime_configuration(
        values: dict,
        *,
        existing_voice_id: str | None = None,
        existing_voice_provider: str | None = None,
    ) -> None:
        """Apply server-owned Realtime and TTS settings.

        Customers may choose only the ElevenLabs voice for Realtime agents. Provider and
        model values are deliberately canonicalized server-side, even if an older client
        sends pipeline fields in the same request.
        """
        selected_voice_id = values.get("voice_id")
        if not selected_voice_id and (existing_voice_provider or "").lower() == "elevenlabs":
            selected_voice_id = existing_voice_id
        values.update(
            realtime_provider=REALTIME_PROVIDER,
            realtime_model=REALTIME_MODEL,
            voice_provider=REALTIME_TTS_PROVIDER,
            voice_id=selected_voice_id or DEFAULT_REALTIME_VOICE_ID,
            tts_provider=REALTIME_TTS_PROVIDER,
            tts_model=REALTIME_TTS_MODEL,
            stt_provider=None,
            stt_model=None,
            llm_provider=None,
            llm_model=None,
        )

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
        if data.use_realtime:
            self._apply_realtime_configuration(agent_data)
        else:
            agent_data.update(realtime_provider=None, realtime_model=None)
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
        values = data.model_dump(exclude_none=True)
        use_realtime = values.get("use_realtime", agent.use_realtime)
        if use_realtime:
            self._apply_realtime_configuration(
                values,
                existing_voice_id=agent.voice_id,
                existing_voice_provider=agent.tts_provider or agent.voice_provider,
            )
        elif values.get("use_realtime") is False:
            values.update(realtime_provider=None, realtime_model=None)
        agent = await self.repo.update(agent, values)
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
