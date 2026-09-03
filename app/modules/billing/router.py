# ruff: noqa: B008
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser, require_any_role, require_company_admin
from app.core.schemas import PaginatedResponse
from app.modules.billing.schemas import (
    BillingUsageResponse,
    InvoiceResponse,
    PaymentResponse,
    PlanChangeRequest,
    PlanChangeResponse,
    PlanResponse,
    StripeCheckoutRequest,
    StripeCheckoutResponse,
    StripePortalResponse,
    SubscriptionResponse,
)
from app.modules.billing.service import BillingService
from app.modules.billing.stripe_gateway import (
    StripeGateway,
    StripeWebhookError,
    get_stripe_gateway,
)
from app.modules.billing.stripe_service import StripeBillingService

router = APIRouter()


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(db: AsyncSession = Depends(get_db)):
    return await BillingService(db).list_plans()


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    current_user: CurrentUser = Depends(require_any_role),
    db: AsyncSession = Depends(get_db),
):
    return await BillingService(db).get_subscription(current_user)


@router.get("/usage", response_model=BillingUsageResponse)
async def get_usage(
    current_user: CurrentUser = Depends(require_any_role),
    db: AsyncSession = Depends(get_db),
):
    return await BillingService(db).get_usage(current_user)


@router.get("/invoices", response_model=PaginatedResponse[InvoiceResponse])
async def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_any_role),
    db: AsyncSession = Depends(get_db),
):
    return await BillingService(db).list_invoices(current_user, page, page_size)


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_any_role),
    db: AsyncSession = Depends(get_db),
):
    return await BillingService(db).get_invoice(invoice_id, current_user)


@router.get("/payments", response_model=PaginatedResponse[PaymentResponse])
async def list_payments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(require_any_role),
    db: AsyncSession = Depends(get_db),
):
    return await BillingService(db).list_payments(current_user, page, page_size)


@router.post("/subscription/change", response_model=PlanChangeResponse)
async def change_plan(
    data: PlanChangeRequest,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await BillingService(db).change_plan(data.plan_id, current_user)


@router.post("/subscription/cancel", response_model=SubscriptionResponse)
async def cancel_subscription(
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
    gateway: StripeGateway = Depends(get_stripe_gateway),
):
    return await StripeBillingService(db, gateway).set_stripe_cancellation(
        current_user, True
    )


@router.post("/subscription/resume", response_model=SubscriptionResponse)
async def resume_subscription(
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
    gateway: StripeGateway = Depends(get_stripe_gateway),
):
    return await StripeBillingService(db, gateway).set_stripe_cancellation(
        current_user, False
    )


@router.post("/stripe/checkout-session", response_model=StripeCheckoutResponse)
async def create_stripe_checkout_session(
    data: StripeCheckoutRequest,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
    gateway: StripeGateway = Depends(get_stripe_gateway),
):
    return await StripeBillingService(db, gateway).create_checkout(
        data.plan_id, current_user
    )


@router.post("/stripe/portal-session", response_model=StripePortalResponse)
async def create_stripe_portal_session(
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
    gateway: StripeGateway = Depends(get_stripe_gateway),
):
    return await StripeBillingService(db, gateway).create_portal(current_user)


@router.post("/stripe/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
    gateway: StripeGateway = Depends(get_stripe_gateway),
):
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")
    payload = await request.body()
    try:
        event = gateway.construct_webhook_event(payload, stripe_signature)
    except StripeWebhookError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await StripeBillingService(db, gateway).process_webhook(event)
    return {"received": True}
