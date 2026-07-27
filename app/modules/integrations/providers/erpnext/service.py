import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import decrypt_credential
from app.modules.integrations.models import Integration, IntegrationLog, IntegrationStatus
from app.modules.integrations.providers.erpnext.client import ERPNextClient
from app.modules.integrations.providers.erpnext.mappings import (
    map_request_to_erpnext, get_config_value, DEFAULT_FIELD_MAPPING
)

logger = logging.getLogger(__name__)


class ERPNextService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _build_client(self, integration: Integration) -> ERPNextClient:
        api_key = decrypt_credential(integration.api_key_encrypted) if integration.api_key_encrypted else ""
        api_secret = decrypt_credential(integration.api_secret_encrypted) if integration.api_secret_encrypted else ""
        return ERPNextClient(
            base_url=integration.base_url,
            api_key=api_key,
            api_secret=api_secret,
        )

    async def test_connection(self, integration: Integration) -> dict:
        client = self._build_client(integration)
        result = await client.test_connection()
        await self._save_log(
            integration_id=integration.id,
            company_id=integration.company_id,
            event_type="test_connection",
            status="success" if result.get("success") else "error",
            response_payload=result,
        )
        return result

    async def sync_request(self, integration: Integration, request) -> Optional[str]:
        """Sync a Request to ERPNext. Returns external document name or None."""
        config = integration.configuration or {}
        customer_doctype = get_config_value(config, "customer_doctype", "Customer")
        request_doctype = get_config_value(config, "request_doctype", "Booking Request")
        field_mapping = get_config_value(config, "field_mapping", DEFAULT_FIELD_MAPPING)

        client = self._build_client(integration)

        # Build request data dict from the ORM object
        request_data = {
            "customer_name": request.customer_name,
            "customer_phone": request.customer_phone,
            "request_type": request.request_type.value if hasattr(request.request_type, "value") else request.request_type,
        }
        if request.request_data:
            request_data.update(request.request_data)

        try:
            # Find or create customer
            customer_name_val = None
            if request.customer_phone:
                customer = await client.find_customer(customer_doctype, request.customer_phone)
                if customer:
                    customer_name_val = customer.get("name")
                else:
                    new_customer = await client.create_document(customer_doctype, {
                        "customer_name": request.customer_name or request.customer_phone,
                        "mobile_no": request.customer_phone,
                        "customer_type": "Individual",
                        "customer_group": get_config_value(config, "customer_group", "All Customer Groups"),
                        "territory": get_config_value(config, "territory", "All Territories"),
                    })
                    customer_name_val = new_customer.get("name")

            # Map and create request document
            mapped_data = map_request_to_erpnext(request_data, field_mapping)
            if customer_name_val:
                mapped_data["customer"] = customer_name_val

            doc = await client.create_document(request_doctype, mapped_data)
            doc_name = doc.get("name")

            await self._save_log(
                integration_id=integration.id,
                company_id=integration.company_id,
                event_type="sync_request",
                status="success",
                request_payload=request_data,
                response_payload=doc,
            )
            return doc_name

        except Exception as e:
            logger.error(f"ERPNext sync failed: {e}")
            await self._save_log(
                integration_id=integration.id,
                company_id=integration.company_id,
                event_type="sync_request",
                status="error",
                request_payload=request_data,
                error_message=str(e),
            )
            raise

    async def _save_log(
        self,
        integration_id,
        company_id,
        event_type: str,
        status: str,
        request_payload: dict = None,
        response_payload: dict = None,
        error_message: str = None,
    ) -> None:
        log = IntegrationLog(
            integration_id=integration_id,
            company_id=company_id,
            event_type=event_type,
            status=status,
            request_payload=request_payload,
            response_payload=response_payload,
            error_message=error_message,
        )
        self.db.add(log)
        await self.db.commit()
