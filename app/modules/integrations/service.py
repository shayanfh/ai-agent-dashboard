import uuid
import math
import logging
import re
from string import Formatter
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.core.dependencies import CurrentUser
from app.core.security import encrypt_credential
from app.modules.integrations.models import IntegrationStatus, IntegrationType
from app.modules.integrations.repository import IntegrationRepository
from app.modules.integrations.schemas import (
    IntegrationCreate, IntegrationUpdate, IntegrationResponse,
    IntegrationLogResponse, TestConnectionResponse,
    WhatsAppMessageResponse, WhatsAppMessageSend,
)
from app.core.schemas import PaginatedResponse
from app.modules.billing.entitlements import EntitlementService

logger = logging.getLogger(__name__)


class IntegrationService:
    def __init__(self, db: AsyncSession):
        self.repo = IntegrationRepository(db)
        self.db = db
        self.entitlements = EntitlementService(db)

    def _get_company_id(self, current_user: CurrentUser) -> uuid.UUID:
        if not current_user.company_id:
            raise PermissionDeniedError("No company context")
        return uuid.UUID(current_user.company_id)

    def _require_admin(self, current_user: CurrentUser):
        if not current_user.is_company_admin and not current_user.is_super_admin:
            raise PermissionDeniedError()

    @staticmethod
    def _validate_whatsapp_configuration(
        configuration: dict | None, *, has_token: bool
    ) -> dict:
        config = dict(configuration or {})
        provider = str(config.get("provider", "ultramsg")).lower()
        if provider != "ultramsg":
            raise ValidationError("Only the ultramsg WhatsApp provider is supported")
        instance_id = str(config.get("instance_id", "")).strip()
        if not instance_id:
            raise ValidationError("configuration.instance_id is required for UltraMsg")
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,100}", instance_id):
            raise ValidationError("configuration.instance_id is invalid")
        if not has_token:
            raise ValidationError("api_key must contain the UltraMsg token")
        if "send_booking_confirmation" in config and not isinstance(
            config["send_booking_confirmation"], bool
        ):
            raise ValidationError("send_booking_confirmation must be a boolean")
        template = config.get("booking_message_template")
        if template is not None and (
            not isinstance(template, str) or not template.strip() or len(template) > 4096
        ):
            raise ValidationError(
                "booking_message_template must contain 1 to 4096 characters"
            )
        if isinstance(template, str):
            try:
                fields = [field for _, field, _, _ in Formatter().parse(template) if field]
            except ValueError as exc:
                raise ValidationError("booking_message_template is invalid") from exc
            if any(
                not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field)
                for field in fields
            ):
                raise ValidationError(
                    "Template placeholders must be simple field names"
                )
        config["provider"] = "ultramsg"
        config["instance_id"] = instance_id
        config.setdefault("send_booking_confirmation", True)
        return config

    async def list_integrations(self, current_user: CurrentUser, page: int = 1, page_size: int = 20) -> PaginatedResponse[IntegrationResponse]:
        self._require_admin(current_user)
        company_id = self._get_company_id(current_user)
        items, total = await self.repo.get_by_company(company_id, page, page_size)
        return PaginatedResponse(
            items=[IntegrationResponse.model_validate(i) for i in items],
            total=total, page=page, page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def get_integration(self, integration_id: uuid.UUID, current_user: CurrentUser) -> IntegrationResponse:
        self._require_admin(current_user)
        company_id = self._get_company_id(current_user)
        integration = await self.repo.get_by_id_and_company(integration_id, company_id)
        if not integration:
            raise NotFoundError("Integration not found")
        return IntegrationResponse.model_validate(integration)

    async def create_integration(self, data: IntegrationCreate, current_user: CurrentUser) -> IntegrationResponse:
        self._require_admin(current_user)
        company_id = self._get_company_id(current_user)
        await self.entitlements.require_resource_capacity(company_id, "integrations")
        configuration = data.configuration
        if data.integration_type == IntegrationType.WHATSAPP:
            configuration = self._validate_whatsapp_configuration(
                data.configuration, has_token=bool(data.api_key)
            )
        create_data = {
            "company_id": company_id,
            "integration_type": data.integration_type,
            "name": data.name,
            "base_url": data.base_url,
            "configuration": configuration,
            "status": IntegrationStatus.PENDING,
        }
        if data.api_key:
            create_data["api_key_encrypted"] = encrypt_credential(data.api_key)
        if data.api_secret:
            create_data["api_secret_encrypted"] = encrypt_credential(data.api_secret)
        integration = await self.repo.create(create_data)
        return IntegrationResponse.model_validate(integration)

    async def update_integration(self, integration_id: uuid.UUID, data: IntegrationUpdate, current_user: CurrentUser) -> IntegrationResponse:
        self._require_admin(current_user)
        company_id = self._get_company_id(current_user)
        integration = await self.repo.get_by_id_and_company(integration_id, company_id)
        if not integration:
            raise NotFoundError("Integration not found")
        update_data = data.model_dump(exclude_none=True, exclude={"api_key", "api_secret"})
        if integration.integration_type == IntegrationType.WHATSAPP:
            if data.status is not None:
                raise ValidationError(
                    "Use the connect or disconnect endpoint to change WhatsApp status"
                )
        if integration.integration_type == IntegrationType.WHATSAPP and data.configuration is not None:
            previous_instance_id = str(
                (integration.configuration or {}).get("instance_id", "")
            )
            merged_configuration = {
                **(integration.configuration or {}),
                **data.configuration,
            }
            update_data["configuration"] = self._validate_whatsapp_configuration(
                merged_configuration,
                has_token=bool(data.api_key or integration.api_key_encrypted),
            )
            if update_data["configuration"]["instance_id"] != previous_instance_id:
                update_data["status"] = IntegrationStatus.PENDING
        if integration.integration_type == IntegrationType.WHATSAPP and data.api_key:
            update_data["status"] = IntegrationStatus.PENDING
        if data.api_key:
            update_data["api_key_encrypted"] = encrypt_credential(data.api_key)
        if data.api_secret:
            update_data["api_secret_encrypted"] = encrypt_credential(data.api_secret)
        integration = await self.repo.update(integration, update_data)
        return IntegrationResponse.model_validate(integration)

    async def delete_integration(self, integration_id: uuid.UUID, current_user: CurrentUser) -> None:
        self._require_admin(current_user)
        company_id = self._get_company_id(current_user)
        integration = await self.repo.get_by_id_and_company(integration_id, company_id)
        if not integration:
            raise NotFoundError("Integration not found")
        await self.repo.delete(integration)

    async def test_connection(self, integration_id: uuid.UUID, current_user: CurrentUser) -> TestConnectionResponse:
        self._require_admin(current_user)
        company_id = self._get_company_id(current_user)
        integration = await self.repo.get_by_id_and_company(integration_id, company_id)
        if not integration:
            raise NotFoundError("Integration not found")
        if integration.integration_type == IntegrationType.ERPNEXT:
            from app.modules.integrations.providers.erpnext.service import ERPNextService
            erpnext_svc = ERPNextService(self.db)
            result = await erpnext_svc.test_connection(integration)
            return TestConnectionResponse(
                success=result.get("success", False),
                message="Connection successful" if result.get("success") else result.get("error", "Failed"),
                details=result,
            )
        if integration.integration_type == IntegrationType.WHATSAPP:
            from app.modules.integrations.providers.ultramsg.service import UltraMsgService

            result = await UltraMsgService(self.db).test_connection(integration)
            return TestConnectionResponse(
                success=result.get("success", False),
                message=(
                    "Connection successful"
                    if result.get("success")
                    else result.get("error", "UltraMsg connection failed")
                ),
                details=result,
            )
        return TestConnectionResponse(success=False, message="Test not implemented for this integration type")

    async def connect(self, integration_id: uuid.UUID, current_user: CurrentUser) -> IntegrationResponse:
        self._require_admin(current_user)
        company_id = self._get_company_id(current_user)
        integration = await self.repo.get_by_id_and_company(integration_id, company_id)
        if not integration:
            raise NotFoundError("Integration not found")
        if integration.integration_type == IntegrationType.WHATSAPP:
            from app.modules.integrations.providers.ultramsg.service import UltraMsgService

            result = await UltraMsgService(self.db).test_connection(integration)
            if not result.get("success"):
                await self.repo.update(
                    integration,
                    {
                        "status": IntegrationStatus.ERROR,
                        "last_error": result.get("error", "UltraMsg connection failed"),
                    },
                )
                raise ValidationError(
                    "UltraMsg instance is not ready", details=result
                )
        integration = await self.repo.update(integration, {"status": IntegrationStatus.CONNECTED})
        return IntegrationResponse.model_validate(integration)

    async def disconnect(self, integration_id: uuid.UUID, current_user: CurrentUser) -> IntegrationResponse:
        self._require_admin(current_user)
        company_id = self._get_company_id(current_user)
        integration = await self.repo.get_by_id_and_company(integration_id, company_id)
        if not integration:
            raise NotFoundError("Integration not found")
        integration = await self.repo.update(integration, {"status": IntegrationStatus.DISCONNECTED})
        return IntegrationResponse.model_validate(integration)

    async def send_whatsapp_message(
        self,
        integration_id: uuid.UUID,
        data: WhatsAppMessageSend,
        current_user: CurrentUser,
    ) -> WhatsAppMessageResponse:
        self._require_admin(current_user)
        company_id = self._get_company_id(current_user)
        integration = await self.repo.get_by_id_and_company(integration_id, company_id)
        if not integration:
            raise NotFoundError("Integration not found")
        if integration.integration_type != IntegrationType.WHATSAPP:
            raise ValidationError("This endpoint requires a WhatsApp integration")
        if integration.status != IntegrationStatus.CONNECTED:
            raise ConflictError("WhatsApp integration is not connected")

        from app.modules.integrations.providers.ultramsg.service import UltraMsgService

        result = await UltraMsgService(self.db).send_message(
            integration, to=data.to.strip(), body=data.body
        )
        message_id = result.get("id") or result.get("messageId") or result.get("message_id")
        provider_status = result.get("status") or result.get("sent")
        return WhatsAppMessageResponse(
            success=True,
            message_id=str(message_id) if message_id else None,
            status=str(provider_status) if provider_status is not None else None,
            details=result,
        )

    async def get_logs(self, integration_id: uuid.UUID, current_user: CurrentUser, page: int = 1, page_size: int = 20) -> PaginatedResponse[IntegrationLogResponse]:
        self._require_admin(current_user)
        company_id = self._get_company_id(current_user)
        integration = await self.repo.get_by_id_and_company(integration_id, company_id)
        if not integration:
            raise NotFoundError("Integration not found")
        logs, total = await self.repo.get_logs(integration_id, page, page_size)
        return PaginatedResponse(
            items=[IntegrationLogResponse.model_validate(l) for l in logs],
            total=total, page=page, page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )
