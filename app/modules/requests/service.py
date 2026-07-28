import uuid
import math
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.dependencies import CurrentUser
from app.modules.requests.models import RequestStatus, RequestType
from app.modules.requests.repository import RequestRepository
from app.modules.requests.schemas import RequestCreate, RequestUpdate, RequestResponse
from app.core.schemas import PaginatedResponse


class RequestService:
    def __init__(self, db: AsyncSession):
        self.repo = RequestRepository(db)
        self.db = db

    def _get_company_id(self, current_user: CurrentUser) -> uuid.UUID:
        if not current_user.company_id:
            raise PermissionDeniedError("No company context")
        return uuid.UUID(current_user.company_id)

    async def list_requests(
        self,
        current_user: CurrentUser,
        page: int = 1,
        page_size: int = 20,
        status: Optional[RequestStatus] = None,
        request_type: Optional[RequestType] = None,
        agent_id: Optional[uuid.UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
    ) -> PaginatedResponse[RequestResponse]:
        company_id = self._get_company_id(current_user)
        items, total = await self.repo.get_by_company(
            company_id, page, page_size, status, request_type, agent_id, date_from, date_to, search
        )
        return PaginatedResponse(
            items=[RequestResponse.model_validate(r) for r in items],
            total=total, page=page, page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def get_request(self, req_id: uuid.UUID, current_user: CurrentUser) -> RequestResponse:
        company_id = self._get_company_id(current_user)
        req = await self.repo.get_by_id_and_company(req_id, company_id)
        if not req:
            raise NotFoundError("Request not found")
        return RequestResponse.model_validate(req)

    async def create_request(self, data: RequestCreate, current_user: CurrentUser) -> RequestResponse:
        company_id = self._get_company_id(current_user)
        if data.call_id:
            from app.modules.calls.models import Call

            call = await self.db.scalar(
                select(Call).where(
                    Call.id == data.call_id,
                    Call.company_id == company_id,
                )
            )
            if not call:
                raise NotFoundError("Call not found")
        if data.agent_id:
            from app.modules.agents.models import Agent

            agent = await self.db.scalar(
                select(Agent).where(
                    Agent.id == data.agent_id,
                    Agent.company_id == company_id,
                )
            )
            if not agent:
                raise NotFoundError("Agent not found")

        req_data = data.model_dump()
        req_data["company_id"] = company_id
        req = await self.repo.create(req_data)
        return RequestResponse.model_validate(req)

    async def update_request(
        self, req_id: uuid.UUID, data: RequestUpdate, current_user: CurrentUser
    ) -> RequestResponse:
        company_id = self._get_company_id(current_user)
        req = await self.repo.get_by_id_and_company(req_id, company_id)
        if not req:
            raise NotFoundError("Request not found")
        req = await self.repo.update(req, data.model_dump(exclude_none=True))
        return RequestResponse.model_validate(req)
