import uuid
import math
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.dependencies import CurrentUser
from app.modules.agents.models import Agent
from app.modules.phone_numbers.models import ConnectionStatus
from app.modules.phone_numbers.repository import PhoneNumberRepository
from app.modules.phone_numbers.schemas import PhoneNumberCreate, PhoneNumberUpdate, PhoneNumberResponse
from app.core.schemas import PaginatedResponse


class PhoneNumberService:
    def __init__(self, db: AsyncSession):
        self.repo = PhoneNumberRepository(db)
        self.db = db

    def _get_company_id(self, current_user: CurrentUser) -> uuid.UUID:
        if not current_user.company_id:
            raise PermissionDeniedError("No company context")
        return uuid.UUID(current_user.company_id)

    async def _validate_agent(self, agent_id: uuid.UUID, company_id: uuid.UUID) -> None:
        agent = await self.db.scalar(
            select(Agent).where(
                Agent.id == agent_id,
                Agent.company_id == company_id,
            )
        )
        if not agent:
            raise NotFoundError("Agent not found")

    async def list_phone_numbers(self, current_user: CurrentUser, page: int = 1, page_size: int = 20) -> PaginatedResponse[PhoneNumberResponse]:
        company_id = self._get_company_id(current_user)
        items, total = await self.repo.get_by_company(company_id, page, page_size)
        return PaginatedResponse(
            items=[PhoneNumberResponse.model_validate(p) for p in items],
            total=total, page=page, page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def get_phone_number(self, phone_id: uuid.UUID, current_user: CurrentUser) -> PhoneNumberResponse:
        company_id = self._get_company_id(current_user)
        pn = await self.repo.get_by_id_and_company(phone_id, company_id)
        if not pn:
            raise NotFoundError("Phone number not found")
        return PhoneNumberResponse.model_validate(pn)

    async def create_phone_number(self, data: PhoneNumberCreate, current_user: CurrentUser) -> PhoneNumberResponse:
        if not current_user.is_company_admin and not current_user.is_super_admin:
            raise PermissionDeniedError()
        company_id = self._get_company_id(current_user)
        if data.agent_id:
            await self._validate_agent(data.agent_id, company_id)
        pn_data = data.model_dump()
        pn_data["company_id"] = company_id
        pn = await self.repo.create(pn_data)
        return PhoneNumberResponse.model_validate(pn)

    async def update_phone_number(self, phone_id: uuid.UUID, data: PhoneNumberUpdate, current_user: CurrentUser) -> PhoneNumberResponse:
        if not current_user.is_company_admin and not current_user.is_super_admin:
            raise PermissionDeniedError()
        company_id = self._get_company_id(current_user)
        pn = await self.repo.get_by_id_and_company(phone_id, company_id)
        if not pn:
            raise NotFoundError("Phone number not found")
        if data.agent_id:
            await self._validate_agent(data.agent_id, company_id)
        pn = await self.repo.update(pn, data.model_dump(exclude_unset=True))
        return PhoneNumberResponse.model_validate(pn)

    async def delete_phone_number(self, phone_id: uuid.UUID, current_user: CurrentUser) -> None:
        if not current_user.is_company_admin and not current_user.is_super_admin:
            raise PermissionDeniedError()
        company_id = self._get_company_id(current_user)
        pn = await self.repo.get_by_id_and_company(phone_id, company_id)
        if not pn:
            raise NotFoundError("Phone number not found")
        await self.repo.delete(pn)

    async def set_enabled(self, phone_id: uuid.UUID, enabled: bool, current_user: CurrentUser) -> PhoneNumberResponse:
        if not current_user.is_company_admin and not current_user.is_super_admin:
            raise PermissionDeniedError()
        company_id = self._get_company_id(current_user)
        pn = await self.repo.get_by_id_and_company(phone_id, company_id)
        if not pn:
            raise NotFoundError("Phone number not found")
        pn = await self.repo.update(pn, {"is_enabled": enabled})
        return PhoneNumberResponse.model_validate(pn)
