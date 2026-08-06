# ruff: noqa: B008
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser, require_super_admin
from app.core.schemas import PaginatedResponse
from app.modules.billing.schemas import (
    AdminInvoiceCreate,
    AdminPlanCreate,
    AdminPlanUpdate,
    InvoiceResponse,
    PaymentRecordRequest,
    PaymentResponse,
    PlanResponse,
)
from app.modules.billing.service import AdminBillingService

router = APIRouter()


@router.post("/plans", response_model=PlanResponse, status_code=201)
async def create_plan(
    data: AdminPlanCreate,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await AdminBillingService(db).create_plan(data)


@router.patch("/plans/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: uuid.UUID,
    data: AdminPlanUpdate,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await AdminBillingService(db).update_plan(plan_id, data)


@router.get("/invoices", response_model=PaginatedResponse[InvoiceResponse])
async def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    company_id: uuid.UUID | None = None,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await AdminBillingService(db).list_all_invoices(
        page, page_size, company_id
    )


@router.post("/invoices", response_model=InvoiceResponse, status_code=201)
async def create_invoice(
    data: AdminInvoiceCreate,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await AdminBillingService(db).create_invoice(data)


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await AdminBillingService(db).get_any_invoice(invoice_id)


@router.get("/payments", response_model=PaginatedResponse[PaymentResponse])
async def list_payments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    company_id: uuid.UUID | None = None,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await AdminBillingService(db).list_all_payments(
        page, page_size, company_id
    )


@router.post(
    "/invoices/{invoice_id}/payments", response_model=PaymentResponse, status_code=201
)
async def record_payment(
    invoice_id: uuid.UUID,
    data: PaymentRecordRequest,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await AdminBillingService(db).record_payment(invoice_id, data)


@router.post("/invoices/{invoice_id}/void", response_model=InvoiceResponse)
async def void_invoice(
    invoice_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await AdminBillingService(db).void_invoice(invoice_id)
