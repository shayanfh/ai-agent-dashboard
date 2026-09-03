import uuid
import math
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.dependencies import CurrentUser
from app.core.security import encrypt_credential
from app.modules.integrations.models import IntegrationStatus, IntegrationType
from app.modules.integrations.repository import IntegrationRepository
from app.modules.integrations.schemas import (
    IntegrationCreate, IntegrationUpdate, IntegrationResponse,
    IntegrationLogResponse, TestConnectionResponse,
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
        create_data = {
            "company_id": company_id,
            "integration_type": data.integration_type,
            "name": data.name,
            "base_url": data.base_url,
            "configuration": data.configuration,
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
        return TestConnectionResponse(success=False, message="Test not implemented for this integration type")

    async def connect(self, integration_id: uuid.UUID, current_user: CurrentUser) -> IntegrationResponse:
        self._require_admin(current_user)
        company_id = self._get_company_id(current_user)
        integration = await self.repo.get_by_id_and_company(integration_id, company_id)
        if not integration:
            raise NotFoundError("Integration not found")
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
