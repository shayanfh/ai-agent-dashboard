import uuid
import math
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.dependencies import CurrentUser
from app.modules.calls.models import CallStatus, CallOutcome
from app.modules.calls.repository import CallRepository
from app.modules.calls.schemas import (
    CallCreate, CallUpdate, CallCompleteRequest, CallMessageCreate,
    CallResponse, CallDetailResponse, CallMessageResponse,
    AgentBrief, PhoneNumberBrief, RequestBrief,
)
from app.core.schemas import PaginatedResponse

logger = logging.getLogger(__name__)

REQUEST_OUTCOMES = {
    CallOutcome.BOOKING_CREATED,
    CallOutcome.CALLBACK_REQUESTED,
}

REQUEST_TYPE_MAP = {
    "car_booking": "car_booking",
    "table_reservation": "table_reservation",
    "callback": "callback",
    "service_request": "service_request",
}


class CallService:
    def __init__(self, db: AsyncSession):
        self.repo = CallRepository(db)
        self.db = db

    def _get_company_id(self, current_user: CurrentUser) -> uuid.UUID:
        if not current_user.company_id:
            raise PermissionDeniedError("No company context")
        return uuid.UUID(current_user.company_id)

    async def list_calls(
        self,
        current_user: CurrentUser,
        page: int = 1,
        page_size: int = 20,
        agent_id: Optional[uuid.UUID] = None,
        status: Optional[CallStatus] = None,
        outcome: Optional[CallOutcome] = None,
        caller_number: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        was_transferred: Optional[bool] = None,
    ) -> PaginatedResponse[CallResponse]:
        company_id = self._get_company_id(current_user)
        calls, total = await self.repo.get_by_company(
            company_id, page, page_size, agent_id, status, outcome,
            caller_number, date_from, date_to, was_transferred,
        )
        return PaginatedResponse(
            items=[CallResponse.model_validate(c) for c in calls],
            total=total, page=page, page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def get_call(self, call_id: uuid.UUID, current_user: CurrentUser) -> CallDetailResponse:
        company_id = self._get_company_id(current_user)
        call = await self.repo.get_by_id_and_company(call_id, company_id)
        if not call:
            raise NotFoundError("Call not found")

        return CallDetailResponse.model_validate(call)

    async def create_call(self, data: CallCreate, current_user: CurrentUser) -> CallResponse:
        company_id = self._get_company_id(current_user)
        call_data = data.model_dump()
        call_data["company_id"] = company_id
        if not call_data.get("started_at"):
            call_data["started_at"] = datetime.now(timezone.utc)
        call = await self.repo.create(call_data)
        return CallResponse.model_validate(call)

    async def update_call(self, call_id: uuid.UUID, data: CallUpdate, current_user: CurrentUser) -> CallResponse:
        company_id = self._get_company_id(current_user)
        call = await self.repo.get_by_id(call_id)
        if not call or str(call.company_id) != str(company_id):
            raise NotFoundError("Call not found")
        update_data = data.model_dump(exclude_none=True)
        call = await self.repo.update(call, update_data)
        return CallResponse.model_validate(call)

    async def add_message(
        self, call_id: uuid.UUID, data: CallMessageCreate, current_user: CurrentUser
    ) -> CallMessageResponse:
        company_id = self._get_company_id(current_user)
        call = await self.repo.get_by_id(call_id)
        if not call or str(call.company_id) != str(company_id):
            raise NotFoundError("Call not found")
        msg_data = data.model_dump()
        msg_data["call_id"] = call_id
        msg_data["company_id"] = company_id
        msg = await self.repo.add_message(msg_data)
        return CallMessageResponse.model_validate(msg)

    async def complete_call(
        self, call_id: uuid.UUID, data: CallCompleteRequest, current_user: CurrentUser
    ) -> dict:
        company_id = self._get_company_id(current_user)
        call = await self.repo.get_by_id(call_id)
        if not call or str(call.company_id) != str(company_id):
            raise NotFoundError("Call not found")

        ended_at = data.ended_at or datetime.now(timezone.utc)
        duration = data.duration_seconds
        if not duration and call.started_at:
            delta = (
                ended_at - call.started_at.replace(tzinfo=timezone.utc)
                if call.started_at.tzinfo is None
                else ended_at - call.started_at
            )
            duration = int(delta.total_seconds())

        update_data = {
            "status": CallStatus.COMPLETED,
            "outcome": data.outcome,
            "was_transferred": data.was_transferred,
            "transfer_number": data.transfer_number,
            "summary": data.summary,
            "extracted_data": data.extracted_data,
            "ended_at": ended_at,
            "duration_seconds": duration,
        }
        if data.recording_url:
            update_data["recording_url"] = data.recording_url
        if data.recording_duration_seconds:
            update_data["recording_duration_seconds"] = data.recording_duration_seconds

        call = await self.repo.update(call, update_data)
        created_request = None

        if data.outcome in REQUEST_OUTCOMES or (
            data.extracted_data and data.extracted_data.get("request_type")
        ):
            created_request = await self._create_request_from_call(call, data, company_id)

        # Queue ERPNext sync if integration exists
        if created_request:
            try:
                from app.workers.integration_tasks import sync_request_to_erpnext
                sync_request_to_erpnext.delay(str(created_request.id), str(company_id))
            except Exception as e:
                logger.warning(f"Could not queue ERPNext sync: {e}")

        return {
            "call": CallResponse.model_validate(call),
            "request": created_request,
        }

    async def _create_request_from_call(self, call, data: CallCompleteRequest, company_id: uuid.UUID):
        from app.modules.requests.models import Request, RequestStatus, RequestType
        extracted = data.extracted_data or {}
        raw_type = extracted.get("request_type", "general_request")
        try:
            req_type = RequestType(raw_type)
        except ValueError:
            req_type = RequestType.GENERAL_REQUEST

        request_data_fields = {
            k: v for k, v in extracted.items()
            if k not in ("customer_name", "customer_phone", "request_type")
        }

        req = Request(
            company_id=company_id,
            call_id=call.id,
            agent_id=call.agent_id,
            customer_name=extracted.get("customer_name"),
            customer_phone=extracted.get("customer_phone"),
            request_type=req_type,
            status=RequestStatus.NEW,
            request_data=request_data_fields,
        )
        self.db.add(req)
        await self.db.commit()
        await self.db.refresh(req)
        logger.info(f"Created request {req.id} from call {call.id}")
        return req
