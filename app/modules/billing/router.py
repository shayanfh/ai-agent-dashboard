# ruff: noqa: B008
import uuid

from fastapi import APIRouter, Depends, Query
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
    SubscriptionResponse,
)
from app.modules.billing.service import BillingService

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
):
    return await BillingService(db).set_cancel_at_period_end(current_user, True)


@router.post("/subscription/resume", response_model=SubscriptionResponse)
async def resume_subscription(
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await BillingService(db).set_cancel_at_period_end(current_user, False)
