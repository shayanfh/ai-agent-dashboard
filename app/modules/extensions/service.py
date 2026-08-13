import math
import secrets
import uuid
from urllib.parse import urlparse

from sqlalchemy import func, select
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
from app.modules.extensions.models import Extension, ExtensionStatus
from app.modules.extensions.schemas import (
    ExtensionCreate,
    ExtensionCredentialsResponse,
    ExtensionResponse,
    ExtensionUpdate,
    SipCredentials,
)
from app.modules.phone_connections.providers import AsteriskProvisionerClient


class ExtensionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _company_id(current_user: CurrentUser) -> uuid.UUID:
        if not current_user.company_id:
            raise PermissionDeniedError("No company context")
        return uuid.UUID(current_user.company_id)

    async def _get(self, extension_id: uuid.UUID, company_id: uuid.UUID) -> Extension:
        extension = await self.db.scalar(
            select(Extension).where(
                Extension.id == extension_id,
                Extension.company_id == company_id,
            )
        )
        if not extension:
            raise NotFoundError("Extension not found")
        return extension

    @staticmethod
    def _server_details() -> tuple[str, int]:
        value = settings.ASTERISK_PUBLIC_SIP_URI.removeprefix("sip:")
        host_port = value.partition(";")[0]
        parsed = urlparse(f"//{host_port}")
        if not parsed.hostname:
            raise ValidationError("Asterisk public SIP URI is not configured")
        return parsed.hostname, parsed.port or 5061

    @staticmethod
    def _username(company_id: uuid.UUID, extension: str) -> str:
        return f"c{company_id.hex[:12]}e{extension}"

    @staticmethod
    def route(company_id: uuid.UUID, extension: str) -> str:
        return f"x{company_id.hex}e{extension}"

    @classmethod
    def transfer_uri(cls, company_id: uuid.UUID, extension: str) -> str:
        value = settings.ASTERISK_PUBLIC_SIP_URI.removeprefix("sip:")
        host, separator, parameters = value.partition(";")
        suffix = f";{parameters}" if separator else ""
        return f"sip:{cls.route(company_id, extension)}@{host}{suffix}"

    def _payload(self, item: Extension, password: str) -> dict:
        return {
            "company_id": str(item.company_id),
            "extension": item.extension,
            "display_name": item.display_name,
            "sip_username": item.sip_username,
            "sip_password": password,
            "transport": item.transport,
            "enabled": item.is_enabled,
        }

    def _credentials(self, item: Extension, password: str) -> SipCredentials:
        host, port = self._server_details()
        return SipCredentials(
            server=host,
            port=port,
            transport=item.transport,
            username=item.sip_username,
            password=password,
            extension=item.extension,
        )

    async def list(
        self, current_user: CurrentUser, page: int, page_size: int
    ) -> PaginatedResponse[ExtensionResponse]:
        company_id = self._company_id(current_user)
        query = select(Extension).where(Extension.company_id == company_id)
        total = int(
            (await self.db.scalar(select(func.count()).select_from(query.subquery())))
            or 0
        )
        items = (
            await self.db.scalars(
                query.order_by(Extension.extension)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return PaginatedResponse(
            items=[ExtensionResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def get(
        self, extension_id: uuid.UUID, current_user: CurrentUser
    ) -> ExtensionResponse:
        item = await self._get(extension_id, self._company_id(current_user))
        return ExtensionResponse.model_validate(item)

    async def create(
        self, data: ExtensionCreate, current_user: CurrentUser
    ) -> ExtensionCredentialsResponse:
        company_id = self._company_id(current_user)
        password = secrets.token_urlsafe(24)
        item = Extension(
            company_id=company_id,
            extension=data.extension,
            display_name=data.display_name,
            employee_name=data.employee_name,
            sip_username=self._username(company_id, data.extension),
            sip_password_encrypted=encrypt_credential(password),
            transport=data.transport,
            status=ExtensionStatus.PROVISIONING,
            is_enabled=True,
        )
        self.db.add(item)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictError("Extension already exists for this company") from exc
        resource_id: str | None = None
        try:
            resource = await AsteriskProvisionerClient().provision_extension(
                str(item.id), self._payload(item, password)
            )
            resource_id = resource.resource_id
            item.asterisk_resource_id = resource_id
            item.status = ExtensionStatus.ACTIVE
            await self.db.commit()
            await self.db.refresh(item)
        except Exception as exc:
            await self.db.rollback()
            if resource_id:
                await AsteriskProvisionerClient().delete_extension(resource_id)
            raise ValidationError(
                f"Extension provisioning failed: {str(exc)[:300]}"
            ) from exc
        return ExtensionCredentialsResponse(
            extension=ExtensionResponse.model_validate(item),
            credentials=self._credentials(item, password),
        )

    async def update(
        self,
        extension_id: uuid.UUID,
        data: ExtensionUpdate,
        current_user: CurrentUser,
    ) -> ExtensionResponse:
        item = await self._get(extension_id, self._company_id(current_user))
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(item, key, value)
        password = decrypt_credential(item.sip_password_encrypted)
        await AsteriskProvisionerClient().provision_extension(
            str(item.id), self._payload(item, password)
        )
        await self.db.commit()
        await self.db.refresh(item)
        return ExtensionResponse.model_validate(item)

    async def set_enabled(
        self, extension_id: uuid.UUID, enabled: bool, current_user: CurrentUser
    ) -> ExtensionResponse:
        item = await self._get(extension_id, self._company_id(current_user))
        item.is_enabled = enabled
        item.status = ExtensionStatus.ACTIVE if enabled else ExtensionStatus.DISABLED
        password = decrypt_credential(item.sip_password_encrypted)
        await AsteriskProvisionerClient().provision_extension(
            str(item.id), self._payload(item, password)
        )
        await self.db.commit()
        await self.db.refresh(item)
        return ExtensionResponse.model_validate(item)

    async def rotate_password(
        self, extension_id: uuid.UUID, current_user: CurrentUser
    ) -> ExtensionCredentialsResponse:
        item = await self._get(extension_id, self._company_id(current_user))
        password = secrets.token_urlsafe(24)
        await AsteriskProvisionerClient().provision_extension(
            str(item.id), self._payload(item, password)
        )
        item.sip_password_encrypted = encrypt_credential(password)
        await self.db.commit()
        await self.db.refresh(item)
        return ExtensionCredentialsResponse(
            extension=ExtensionResponse.model_validate(item),
            credentials=self._credentials(item, password),
        )

    async def delete(self, extension_id: uuid.UUID, current_user: CurrentUser) -> None:
        item = await self._get(extension_id, self._company_id(current_user))
        await AsteriskProvisionerClient().delete_extension(item.asterisk_resource_id)
        await self.db.delete(item)
        await self.db.commit()
