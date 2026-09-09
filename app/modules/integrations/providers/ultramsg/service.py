from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.core.security import decrypt_credential
from app.modules.integrations.models import Integration, IntegrationLog
from app.modules.integrations.providers.ultramsg.client import UltraMsgClient


DEFAULT_BOOKING_MESSAGE = (
    "Hello {customer_name}, your reservation request has been received successfully. "
    "Reference: {request_id}."
)


class _SafeTemplateValues(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class UltraMsgService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _instance_id(integration: Integration) -> str:
        return str((integration.configuration or {}).get("instance_id", "")).strip()

    def _build_client(self, integration: Integration) -> UltraMsgClient:
        token = (
            decrypt_credential(integration.api_key_encrypted)
            if integration.api_key_encrypted
            else ""
        )
        return UltraMsgClient(self._instance_id(integration), token)

    async def test_connection(self, integration: Integration) -> dict[str, Any]:
        result = await self._build_client(integration).test_connection()
        await self._save_log(
            integration,
            event_type="test_connection",
            status="success" if result.get("success") else "error",
            response_payload=result,
            error_message=result.get("error"),
        )
        return result

    async def send_message(
        self,
        integration: Integration,
        *,
        to: str,
        body: str,
        event_type: str = "send_message",
        context: dict | None = None,
    ) -> dict[str, Any]:
        request_payload = {"to": to, "body": body, **(context or {})}
        try:
            result = await self._build_client(integration).send_text(to, body)
            await self._save_log(
                integration,
                event_type=event_type,
                status="success",
                request_payload=request_payload,
                response_payload=result,
            )
            return result
        except Exception as exc:
            await self._save_log(
                integration,
                event_type=event_type,
                status="error",
                request_payload=request_payload,
                error_message=str(exc),
            )
            raise

    async def send_booking_confirmation(
        self, integration: Integration, request
    ) -> dict[str, Any]:
        config = integration.configuration or {}
        template = config.get("booking_message_template") or DEFAULT_BOOKING_MESSAGE
        values = _SafeTemplateValues(request.request_data or {})
        values.update(
            customer_name=request.customer_name or "Customer",
            customer_phone=request.customer_phone or "",
            request_type=request.request_type.value,
            request_id=str(request.id),
        )
        try:
            body = str(template).format_map(values)
        except (AttributeError, IndexError, KeyError, ValueError) as exc:
            raise ValidationError("Invalid WhatsApp booking message template") from exc
        if not body.strip() or len(body) > 4096:
            raise ValidationError(
                "Rendered WhatsApp booking message must contain 1 to 4096 characters"
            )
        return await self.send_message(
            integration,
            to=request.customer_phone.strip(),
            body=body,
            event_type="booking_confirmation",
            context={"request_id": str(request.id)},
        )

    async def _save_log(
        self,
        integration: Integration,
        *,
        event_type: str,
        status: str,
        request_payload: dict | None = None,
        response_payload: dict | None = None,
        error_message: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        integration.last_sync_at = now
        integration.last_error = error_message
        self.db.add(
            IntegrationLog(
                integration_id=integration.id,
                company_id=integration.company_id,
                event_type=event_type,
                status=status,
                request_payload=request_payload,
                response_payload=response_payload,
                error_message=error_message,
            )
        )
        await self.db.commit()
