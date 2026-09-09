import logging

from app.workers.async_utils import run_async
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="sync_request_to_erpnext", bind=True, max_retries=3)
def sync_request_to_erpnext(self, request_id: str, company_id: str) -> dict:
    """Sync a completed call request to ERPNext."""
    logger.info(f"Syncing request {request_id} to ERPNext for company {company_id}")
    try:
        async def _sync():
            from app.core.database import AsyncSessionLocal
            from app.modules.requests.models import Request
            from app.modules.integrations.repository import IntegrationRepository
            from app.modules.integrations.providers.erpnext.service import ERPNextService
            from sqlalchemy import select
            import uuid

            async with AsyncSessionLocal() as db:
                # Load request
                req_result = await db.execute(
                    select(Request).where(Request.id == uuid.UUID(request_id))
                )
                request = req_result.scalar_one_or_none()
                if not request:
                    logger.warning(f"Request {request_id} not found")
                    return {"status": "not_found"}

                # Find connected ERPNext integration
                repo = IntegrationRepository(db)
                integration = await repo.get_connected_erpnext(uuid.UUID(company_id))
                if not integration:
                    logger.info(f"No connected ERPNext integration for company {company_id}")
                    return {"status": "no_integration"}

                # Sync to ERPNext
                erpnext_svc = ERPNextService(db)
                doc_name = await erpnext_svc.sync_request(integration, request)

                if doc_name:
                    request.external_reference = doc_name
                    await db.commit()

                return {"status": "success", "erpnext_doc": doc_name}

        return run_async(_sync)

    except Exception as exc:
        logger.error(f"ERPNext sync failed for request {request_id}: {exc}")
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(
    name="app.workers.integration_tasks.send_booking_confirmation",
    bind=True,
    max_retries=3,
)
def send_booking_confirmation(self, request_id: str, company_id: str) -> dict:
    """Send a WhatsApp confirmation for a newly created booking request."""

    async def _send():
        import uuid

        from app.core.database import AsyncSessionLocal
        from app.modules.integrations.providers.ultramsg.service import UltraMsgService
        from app.modules.integrations.repository import IntegrationRepository
        from app.modules.requests.models import Request, RequestType
        from app.modules.calls.models import Call, CallOutcome

        async with AsyncSessionLocal() as db:
            request = await db.get(Request, uuid.UUID(request_id))
            if not request or request.company_id != uuid.UUID(company_id):
                return {"status": "not_found"}
            if request.request_type not in {
                RequestType.CAR_BOOKING,
                RequestType.TABLE_RESERVATION,
            }:
                call = await db.get(Call, request.call_id) if request.call_id else None
                if not call or call.outcome != CallOutcome.BOOKING_CREATED:
                    return {"status": "not_booking"}
            if not request.customer_phone:
                return {"status": "missing_customer_phone"}

            integration = await IntegrationRepository(db).get_connected_whatsapp(
                uuid.UUID(company_id)
            )
            if not integration:
                return {"status": "no_integration"}
            if not (integration.configuration or {}).get(
                "send_booking_confirmation", True
            ):
                return {"status": "disabled"}

            result = await UltraMsgService(db).send_booking_confirmation(
                integration, request
            )
            return {
                "status": "success",
                "message_id": result.get("id")
                or result.get("messageId")
                or result.get("message_id"),
            }

    try:
        return run_async(_send)
    except Exception as exc:
        logger.exception(
            "WhatsApp booking confirmation failed for request %s", request_id
        )
        raise self.retry(exc=exc, countdown=120)
