import json
import logging
import math
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import CurrentUser
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.core.schemas import PaginatedResponse
from app.core.security import decrypt_credential, encrypt_credential
from app.modules.agents.models import Agent
from app.modules.onboarding.models import (
    PhoneProvider,
    TelephonyConnection,
    TelephonyConnectionStatus,
    TelephonyConnectionType,
)
from app.modules.phone_connections.providers import (
    LiveKitProvisioner,
    TwilioElasticSipClient,
)
from app.modules.phone_connections.schemas import (
    PhoneConnectionCreate,
    PhoneConnectionProvisionResponse,
    PhoneConnectionResponse,
    PhoneConnectionTestResponse,
)
from app.modules.phone_numbers.models import ConnectionStatus, PhoneNumber

logger = logging.getLogger(__name__)


class PhoneConnectionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _company_id(current_user: CurrentUser) -> uuid.UUID:
        if not current_user.company_id:
            raise PermissionDeniedError("No company context")
        return uuid.UUID(current_user.company_id)

    async def _get(
        self, connection_id: uuid.UUID, company_id: uuid.UUID
    ) -> TelephonyConnection:
        connection = await self.db.scalar(
            select(TelephonyConnection).where(
                TelephonyConnection.id == connection_id,
                TelephonyConnection.company_id == company_id,
            )
        )
        if not connection:
            raise NotFoundError("Phone connection not found")
        return connection

    async def _response(self, connection: TelephonyConnection) -> PhoneConnectionResponse:
        phone = await self.db.scalar(
            select(PhoneNumber).where(PhoneNumber.connection_id == connection.id)
        )
        return PhoneConnectionResponse(
            id=connection.id,
            company_id=connection.company_id,
            phone_number_id=phone.id if phone else None,
            name=connection.name,
            provider=connection.provider,
            status=connection.status,
            phone_number=phone.phone_number if phone else None,
            extension=phone.extension if phone else "",
            agent_id=phone.agent_id if phone else None,
            livekit_trunk_id=connection.livekit_trunk_id,
            dispatch_rule_id=connection.dispatch_rule_id,
            external_trunk_id=connection.external_trunk_id,
            configuration=connection.configuration,
            last_error=connection.last_error,
            connected_at=connection.connected_at,
            created_at=connection.created_at,
            updated_at=connection.updated_at,
        )

    async def list(
        self, current_user: CurrentUser, page: int, page_size: int
    ) -> PaginatedResponse[PhoneConnectionResponse]:
        company_id = self._company_id(current_user)
        query = select(TelephonyConnection).where(
            TelephonyConnection.company_id == company_id
        )
        from sqlalchemy import func

        total = int(
            (await self.db.scalar(select(func.count()).select_from(query.subquery()))) or 0
        )
        connections = (
            await self.db.scalars(
                query.order_by(TelephonyConnection.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return PaginatedResponse(
            items=[await self._response(item) for item in connections],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def get(
        self, connection_id: uuid.UUID, current_user: CurrentUser
    ) -> PhoneConnectionResponse:
        connection = await self._get(connection_id, self._company_id(current_user))
        return await self._response(connection)

    async def create(
        self, data: PhoneConnectionCreate, current_user: CurrentUser
    ) -> PhoneConnectionResponse:
        company_id = self._company_id(current_user)
        if data.agent_id:
            agent = await self.db.scalar(
                select(Agent).where(
                    Agent.id == data.agent_id, Agent.company_id == company_id
                )
            )
            if not agent:
                raise NotFoundError("Agent not found")

        exists = await self.db.scalar(
            select(PhoneNumber.id).where(
                PhoneNumber.phone_number == data.phone_number,
                PhoneNumber.extension == data.extension,
            )
        )
        if exists:
            raise ConflictError("Phone number and extension are already connected")

        credentials: dict[str, str] = {}
        safe_configuration: dict = {}
        if data.provider == PhoneProvider.TWILIO and data.twilio:
            credentials = data.twilio.model_dump()
            safe_configuration = {
                "phone_number_sid": data.twilio.phone_number_sid,
                "twilio_account": f"{data.twilio.account_sid[:6]}...{data.twilio.account_sid[-4:]}",
                "transport": "tcp",
            }
        elif data.sip:
            username = data.sip.auth_username or f"mw-{secrets.token_hex(8)}"
            password = data.sip.auth_password or secrets.token_urlsafe(24)
            credentials = {"auth_username": username, "auth_password": password}
            safe_configuration = {
                "allowed_addresses": data.sip.allowed_addresses,
                "transport": data.sip.transport,
                "authentication": "digest",
            }

        connection = TelephonyConnection(
            company_id=company_id,
            name=data.name,
            provider=data.provider,
            connection_type=TelephonyConnectionType.SIP_TRUNK,
            status=TelephonyConnectionStatus.PENDING,
            configuration=safe_configuration,
            credentials_encrypted=encrypt_credential(json.dumps(credentials)),
        )
        self.db.add(connection)
        try:
            await self.db.flush()
            phone = PhoneNumber(
                company_id=company_id,
                agent_id=data.agent_id,
                connection_id=connection.id,
                phone_number=data.phone_number,
                extension=data.extension,
                provider=data.provider.value,
                connection_status=ConnectionStatus.PENDING,
                is_enabled=False,
            )
            self.db.add(phone)
            await self.db.flush()
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictError("Phone number and extension are already connected") from exc
        return await self._response(connection)

    def _credentials(self, connection: TelephonyConnection) -> dict[str, str]:
        if not connection.credentials_encrypted:
            return {}
        return json.loads(decrypt_credential(connection.credentials_encrypted))

    async def provision(
        self, connection_id: uuid.UUID, current_user: CurrentUser
    ) -> PhoneConnectionProvisionResponse:
        company_id = self._company_id(current_user)
        connection = await self._get(connection_id, company_id)
        if connection.status not in (
            TelephonyConnectionStatus.PENDING,
            TelephonyConnectionStatus.ERROR,
            TelephonyConnectionStatus.DISCONNECTED,
        ):
            raise ConflictError("Phone connection has already been provisioned")
        phone = await self.db.scalar(
            select(PhoneNumber).where(PhoneNumber.connection_id == connection.id)
        )
        if not phone:
            raise NotFoundError("Phone number mapping not found")

        connection.status = TelephonyConnectionStatus.PROVISIONING
        connection.last_error = None
        await self.db.commit()
        livekit = LiveKitProvisioner()
        credentials = self._credentials(connection)
        livekit_resources = None
        external_trunk_id = None
        try:
            livekit_resources = await livekit.provision(
                connection_id=str(connection.id),
                company_id=str(company_id),
                name=connection.name or f"{connection.provider.value} {phone.phone_number}",
                phone_number=phone.phone_number,
                auth_username=(
                    credentials.get("auth_username")
                    if connection.provider != PhoneProvider.TWILIO
                    else None
                ),
                auth_password=(
                    credentials.get("auth_password")
                    if connection.provider != PhoneProvider.TWILIO
                    else None
                ),
                allowed_addresses=(connection.configuration or {}).get(
                    "allowed_addresses", []
                ),
            )
            if connection.provider == PhoneProvider.TWILIO:
                external_trunk_id = await TwilioElasticSipClient(
                    credentials["account_sid"], credentials["auth_token"]
                ).provision(
                    connection_id=str(connection.id),
                    name=connection.name or f"Mozaic {phone.phone_number}",
                    phone_number_sid=credentials["phone_number_sid"],
                )

            connection.livekit_trunk_id = livekit_resources.trunk_id
            connection.dispatch_rule_id = livekit_resources.dispatch_rule_id
            connection.external_trunk_id = external_trunk_id
            connection.status = TelephonyConnectionStatus.TESTING
            phone.livekit_trunk_id = livekit_resources.trunk_id
            phone.dispatch_rule_id = livekit_resources.dispatch_rule_id
            phone.sip_trunk_id = external_trunk_id
            phone.connection_status = ConnectionStatus.PENDING
            phone.is_enabled = True
            await self.db.commit()

            setup: dict = {
                "sip_uri": f"sip:{settings.LIVEKIT_SIP_ENDPOINT}",
                "transport": (connection.configuration or {}).get("transport", "tcp"),
                "verification": "Place an inbound test call to activate the connection.",
            }
            if connection.provider != PhoneProvider.TWILIO:
                setup.update(
                    username=credentials.get("auth_username"),
                    password=credentials.get("auth_password"),
                )
            else:
                setup["twilio_trunk_sid"] = external_trunk_id
                setup["configured_automatically"] = True
            return PhoneConnectionProvisionResponse(
                connection=await self._response(connection), provider_setup=setup
            )
        except Exception as exc:
            if external_trunk_id and connection.provider == PhoneProvider.TWILIO:
                try:
                    await TwilioElasticSipClient(
                        credentials["account_sid"], credentials["auth_token"]
                    ).delete(external_trunk_id)
                except Exception:
                    logger.warning("Could not roll back Twilio trunk", exc_info=True)
            if livekit_resources:
                await livekit.delete(
                    livekit_resources.trunk_id, livekit_resources.dispatch_rule_id
                )
            connection.status = TelephonyConnectionStatus.ERROR
            connection.last_error = f"{type(exc).__name__}: {str(exc)[:500]}"
            phone.connection_status = ConnectionStatus.ERROR
            phone.is_enabled = False
            await self.db.commit()
            raise ValidationError(
                f"Phone connection provisioning failed: {str(exc)[:300]}"
            ) from exc

    async def test(
        self, connection_id: uuid.UUID, current_user: CurrentUser
    ) -> PhoneConnectionTestResponse:
        connection = await self._get(connection_id, self._company_id(current_user))
        if not connection.livekit_trunk_id:
            return PhoneConnectionTestResponse(
                success=False,
                status=connection.status,
                message="Connection has not been provisioned",
            )
        exists = await LiveKitProvisioner().exists(connection.livekit_trunk_id)
        return PhoneConnectionTestResponse(
            success=exists,
            status=connection.status,
            message=(
                "LiveKit trunk exists; place an inbound call for end-to-end verification"
                if exists
                else "LiveKit trunk was not found"
            ),
        )

    async def disconnect(
        self, connection_id: uuid.UUID, current_user: CurrentUser
    ) -> PhoneConnectionResponse:
        connection = await self._get(connection_id, self._company_id(current_user))
        credentials = self._credentials(connection)
        await LiveKitProvisioner().delete(
            connection.livekit_trunk_id, connection.dispatch_rule_id
        )
        if connection.provider == PhoneProvider.TWILIO and connection.external_trunk_id:
            await TwilioElasticSipClient(
                credentials["account_sid"], credentials["auth_token"]
            ).delete(connection.external_trunk_id)
        phone = await self.db.scalar(
            select(PhoneNumber).where(PhoneNumber.connection_id == connection.id)
        )
        if phone:
            phone.is_enabled = False
            phone.connection_status = ConnectionStatus.DISCONNECTED
            phone.livekit_trunk_id = None
            phone.dispatch_rule_id = None
            phone.sip_trunk_id = None
        connection.status = TelephonyConnectionStatus.DISCONNECTED
        connection.livekit_trunk_id = None
        connection.dispatch_rule_id = None
        connection.external_trunk_id = None
        await self.db.commit()
        return await self._response(connection)
