import json
import logging
import math
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
    SipConnectionMode,
    TelephonyConnection,
    TelephonyConnectionStatus,
    TelephonyConnectionType,
)
from app.modules.phone_connections.providers import (
    AsteriskProvisionerClient,
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
            asterisk_resource_id=connection.asterisk_resource_id,
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
                "transport": "tls",
            }
        elif data.sip:
            credentials = {
                key: value
                for key, value in {
                    "auth_username": data.sip.auth_username,
                    "auth_password": data.sip.auth_password,
                }.items()
                if value
            }
            safe_configuration = {
                "sip_mode": data.sip.mode.value,
                "server_uri": data.sip.server_uri,
                "server_port": data.sip.server_port,
                "allowed_addresses": data.sip.allowed_addresses,
                "transport": data.sip.transport,
                "realm": data.sip.realm,
                "outbound_proxy": data.sip.outbound_proxy,
                "authentication": (
                    "provider_registration"
                    if data.sip.mode == SipConnectionMode.REGISTRATION
                    else "source_ip"
                ),
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
        asterisk = None
        credentials = self._credentials(connection)
        asterisk_resource = None
        external_trunk_id = None
        try:
            asterisk = AsteriskProvisionerClient()
            configuration = connection.configuration or {}
            sip_mode = configuration.get("sip_mode") or "ip_trunk"
            asterisk_mode = (
                "twilio" if connection.provider == PhoneProvider.TWILIO else sip_mode
            )
            asterisk_resource = await asterisk.provision(
                str(connection.id),
                {
                    "company_id": str(company_id),
                    "name": connection.name
                    or f"{connection.provider.value} {phone.phone_number}",
                    "provider": connection.provider.value,
                    "mode": asterisk_mode,
                    "phone_number": phone.phone_number,
                    "extension": phone.extension,
                    "transport": configuration.get("transport", "tcp"),
                    "server_uri": configuration.get("server_uri"),
                    "server_port": configuration.get("server_port"),
                    "allowed_addresses": configuration.get("allowed_addresses", []),
                    "auth_username": credentials.get("auth_username"),
                    "auth_password": credentials.get("auth_password"),
                    "realm": configuration.get("realm"),
                    "outbound_proxy": configuration.get("outbound_proxy"),
                    "public_sip_uri": settings.ASTERISK_PUBLIC_SIP_URI,
                },
            )
            if connection.provider == PhoneProvider.TWILIO:
                external_trunk_id = await TwilioElasticSipClient(
                    credentials["account_sid"], credentials["auth_token"]
                ).provision(
                    connection_id=str(connection.id),
                    name=connection.name or f"Mozaic {phone.phone_number}",
                    phone_number_sid=credentials["phone_number_sid"],
                    target_sip_uri=settings.ASTERISK_PUBLIC_SIP_URI,
                )

            connection.livekit_trunk_id = None
            connection.dispatch_rule_id = None
            connection.external_trunk_id = external_trunk_id
            connection.asterisk_resource_id = asterisk_resource.resource_id
            if asterisk_mode == SipConnectionMode.IP_TRUNK.value:
                connection.status = TelephonyConnectionStatus.AWAITING_PROVIDER_SETUP
            elif asterisk_mode == SipConnectionMode.REGISTRATION.value:
                connection.status = TelephonyConnectionStatus.REGISTERING
            else:
                connection.status = TelephonyConnectionStatus.TESTING
            phone.livekit_trunk_id = None
            phone.dispatch_rule_id = None
            phone.sip_trunk_id = external_trunk_id
            phone.connection_status = ConnectionStatus.PENDING
            phone.is_enabled = True
            await self.db.commit()

            setup: dict = {
                **asterisk_resource.provider_setup,
                "gateway": "asterisk",
                "transport": configuration.get("transport", "tcp"),
                "verification": "Place an inbound test call to activate the connection.",
            }
            if connection.provider == PhoneProvider.TWILIO:
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
            if asterisk and asterisk_resource:
                try:
                    await asterisk.delete(asterisk_resource.resource_id)
                except Exception:
                    logger.warning("Could not roll back Asterisk resource", exc_info=True)
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
        if not connection.asterisk_resource_id:
            return PhoneConnectionTestResponse(
                success=False,
                status=connection.status,
                message="Connection has not been provisioned",
            )
        resource = await AsteriskProvisionerClient().status(
            connection.asterisk_resource_id
        )
        success = resource.state in {"ready", "registered", "configured"}
        return PhoneConnectionTestResponse(
            success=success,
            status=connection.status,
            message=(
                "Asterisk route is ready; place an inbound call for end-to-end verification"
                if success
                else f"Asterisk connection state: {resource.state}"
            ),
        )

    async def disconnect(
        self, connection_id: uuid.UUID, current_user: CurrentUser
    ) -> PhoneConnectionResponse:
        connection = await self._get(connection_id, self._company_id(current_user))
        credentials = self._credentials(connection)
        if connection.provider == PhoneProvider.TWILIO and connection.external_trunk_id:
            await TwilioElasticSipClient(
                credentials["account_sid"], credentials["auth_token"]
            ).delete(connection.external_trunk_id)
        if connection.asterisk_resource_id:
            await AsteriskProvisionerClient().delete(connection.asterisk_resource_id)
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
        connection.asterisk_resource_id = None
        await self.db.commit()
        return await self._response(connection)

    async def delete(
        self, connection_id: uuid.UUID, current_user: CurrentUser
    ) -> None:
        company_id = self._company_id(current_user)
        connection = await self._get(connection_id, company_id)

        # Always run the provider cleanup first. If it fails, no database row is
        # deleted, so the operation can safely be retried.
        await self.disconnect(connection_id, current_user)
        connection = await self._get(connection_id, company_id)
        phone = await self.db.scalar(
            select(PhoneNumber).where(PhoneNumber.connection_id == connection.id)
        )
        if phone:
            await self.db.delete(phone)
            await self.db.flush()
        await self.db.delete(connection)
        await self.db.commit()
