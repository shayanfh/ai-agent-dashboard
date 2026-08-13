import math
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.core.schemas import PaginatedResponse
from app.modules.agents.models import Agent
from app.modules.onboarding.models import (
    TelephonyConnection,
    TelephonyConnectionStatus,
)
from app.modules.phone_connections.service import PhoneConnectionService
from app.modules.phone_numbers.models import ConnectionStatus, PhoneNumber
from app.modules.phone_numbers.repository import PhoneNumberRepository
from app.modules.phone_numbers.schemas import (
    PhoneNumberCreate,
    PhoneNumberProvisionResponse,
    PhoneNumberResponse,
    PhoneNumberTestResponse,
    PhoneNumberUpdate,
)


class PhoneNumberService:
    def __init__(self, db: AsyncSession):
        self.repo = PhoneNumberRepository(db)
        self.db = db
        self.connections = PhoneConnectionService(db)

    def _get_company_id(self, current_user: CurrentUser) -> uuid.UUID:
        if not current_user.company_id:
            raise PermissionDeniedError("No company context")
        return uuid.UUID(current_user.company_id)

    async def _validate_agent(
        self, agent_id: uuid.UUID, company_id: uuid.UUID
    ) -> None:
        agent = await self.db.scalar(
            select(Agent).where(Agent.id == agent_id, Agent.company_id == company_id)
        )
        if not agent:
            raise NotFoundError("Agent not found")

    async def _get_phone(
        self, phone_id: uuid.UUID, current_user: CurrentUser
    ) -> PhoneNumber:
        phone = await self.repo.get_by_id_and_company(
            phone_id, self._get_company_id(current_user)
        )
        if not phone:
            raise NotFoundError("Phone number not found")
        return phone

    async def _get_connection(self, phone: PhoneNumber) -> TelephonyConnection:
        if not phone.connection_id:
            raise ConflictError("Phone number does not have a provider connection")
        connection = await self.db.get(TelephonyConnection, phone.connection_id)
        if not connection or connection.company_id != phone.company_id:
            raise NotFoundError("Phone connection not found")
        return connection

    @staticmethod
    def _legacy_status(status: ConnectionStatus) -> TelephonyConnectionStatus:
        return {
            ConnectionStatus.CONNECTED: TelephonyConnectionStatus.ACTIVE,
            ConnectionStatus.DISCONNECTED: TelephonyConnectionStatus.DISCONNECTED,
            ConnectionStatus.ERROR: TelephonyConnectionStatus.ERROR,
            ConnectionStatus.PENDING: TelephonyConnectionStatus.PENDING,
        }[status]

    async def _response(self, phone: PhoneNumber) -> PhoneNumberResponse:
        connection = (
            await self.db.get(TelephonyConnection, phone.connection_id)
            if phone.connection_id
            else None
        )
        return PhoneNumberResponse(
            id=phone.id,
            company_id=phone.company_id,
            agent_id=phone.agent_id,
            connection_id=phone.connection_id,
            name=connection.name if connection else None,
            phone_number=phone.phone_number,
            provider=connection.provider if connection else phone.provider,
            status=(
                connection.status
                if connection
                else self._legacy_status(phone.connection_status)
            ),
            connection_status=phone.connection_status,
            sip_trunk_id=phone.sip_trunk_id,
            external_trunk_id=connection.external_trunk_id if connection else None,
            asterisk_resource_id=(
                connection.asterisk_resource_id if connection else None
            ),
            livekit_trunk_id=phone.livekit_trunk_id,
            dispatch_rule_id=phone.dispatch_rule_id,
            configuration=connection.configuration if connection else None,
            last_error=connection.last_error if connection else None,
            connected_at=connection.connected_at if connection else None,
            transfer_number=phone.transfer_number,
            operating_hours=phone.operating_hours,
            is_enabled=phone.is_enabled,
            created_at=phone.created_at,
            updated_at=max(
                phone.updated_at,
                connection.updated_at if connection else phone.updated_at,
            ),
        )

    async def list_phone_numbers(
        self, current_user: CurrentUser, page: int = 1, page_size: int = 20
    ) -> PaginatedResponse[PhoneNumberResponse]:
        company_id = self._get_company_id(current_user)
        items, total = await self.repo.get_by_company(company_id, page, page_size)
        return PaginatedResponse(
            items=[await self._response(phone) for phone in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def get_phone_number(
        self, phone_id: uuid.UUID, current_user: CurrentUser
    ) -> PhoneNumberResponse:
        return await self._response(await self._get_phone(phone_id, current_user))

    async def create_phone_number(
        self, data: PhoneNumberCreate, current_user: CurrentUser
    ) -> PhoneNumberResponse:
        company_id = self._get_company_id(current_user)
        if data.agent_id:
            await self._validate_agent(data.agent_id, company_id)

        if data.provider is not None:
            connection = await self.connections.create(
                data.to_connection_create(), current_user
            )
            if connection.phone_number_id is None:
                raise NotFoundError("Phone number mapping not found")
            phone = await self._get_phone(connection.phone_number_id, current_user)
            phone.transfer_number = data.transfer_number
            phone.operating_hours = data.operating_hours
            # Connected numbers start disabled until provisioning, regardless of input.
            await self.db.commit()
            return await self._response(phone)

        duplicate = await self.db.scalar(
            select(PhoneNumber.id).where(PhoneNumber.phone_number == data.phone_number)
        )
        if duplicate:
            raise ConflictError("Phone number is already registered")
        try:
            phone = await self.repo.create(
                {
                    "company_id": company_id,
                    "phone_number": data.phone_number,
                    "agent_id": data.agent_id,
                    "transfer_number": data.transfer_number,
                    "operating_hours": data.operating_hours,
                    "is_enabled": data.is_enabled,
                }
            )
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictError(
                "Phone number is already registered"
            ) from exc
        return await self._response(phone)

    async def update_phone_number(
        self,
        phone_id: uuid.UUID,
        data: PhoneNumberUpdate,
        current_user: CurrentUser,
    ) -> PhoneNumberResponse:
        company_id = self._get_company_id(current_user)
        phone = await self._get_phone(phone_id, current_user)
        if data.agent_id:
            await self._validate_agent(data.agent_id, company_id)
        update_data = data.model_dump(exclude_unset=True)
        name = update_data.pop("name", None)
        if phone.connection_id and "phone_number" in update_data:
            raise ConflictError(
                "A provider-connected phone number cannot be changed; "
                "delete and recreate the phone number"
            )
        phone = await self.repo.update(phone, update_data)
        if name is not None and phone.connection_id:
            connection = await self._get_connection(phone)
            connection.name = name
            await self.db.commit()
        return await self._response(phone)

    async def provision(
        self, phone_id: uuid.UUID, current_user: CurrentUser
    ) -> PhoneNumberProvisionResponse:
        phone = await self._get_phone(phone_id, current_user)
        connection = await self._get_connection(phone)
        result = await self.connections.provision(connection.id, current_user)
        refreshed = await self._get_phone(phone_id, current_user)
        return PhoneNumberProvisionResponse(
            phone_number=await self._response(refreshed),
            provider_setup=result.provider_setup,
        )

    async def test(
        self, phone_id: uuid.UUID, current_user: CurrentUser
    ) -> PhoneNumberTestResponse:
        phone = await self._get_phone(phone_id, current_user)
        connection = await self._get_connection(phone)
        return await self.connections.test(connection.id, current_user)

    async def disconnect(
        self, phone_id: uuid.UUID, current_user: CurrentUser
    ) -> PhoneNumberResponse:
        phone = await self._get_phone(phone_id, current_user)
        connection = await self._get_connection(phone)
        await self.connections.disconnect(connection.id, current_user)
        return await self._response(await self._get_phone(phone_id, current_user))

    async def delete_phone_number(
        self, phone_id: uuid.UUID, current_user: CurrentUser
    ) -> None:
        phone = await self._get_phone(phone_id, current_user)
        if phone.connection_id:
            await self.connections.delete(phone.connection_id, current_user)
        else:
            await self.repo.delete(phone)

    async def set_enabled(
        self, phone_id: uuid.UUID, enabled: bool, current_user: CurrentUser
    ) -> PhoneNumberResponse:
        phone = await self._get_phone(phone_id, current_user)
        phone = await self.repo.update(phone, {"is_enabled": enabled})
        return await self._response(phone)
