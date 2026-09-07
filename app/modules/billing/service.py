import logging
import math
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
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
from app.modules.agents.models import Agent
from app.modules.billing.models import (
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentStatus,
    Plan,
    Subscription,
    SubscriptionStatus,
)
from app.modules.billing.schemas import (
    AdminInvoiceCreate,
    AdminPlanCreate,
    AdminPlanUpdate,
    BillingUsageResponse,
    InvoiceResponse,
    PaymentRecordRequest,
    PaymentResponse,
    PlanChangeResponse,
    PlanResponse,
    SubscriptionResponse,
)
from app.modules.billing.stripe_gateway import StripeGateway
from app.modules.calls.models import Call, CallSource
from app.modules.companies.models import Company
from app.modules.integrations.models import Integration


logger = logging.getLogger(__name__)


class BillingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _company_id(current_user: CurrentUser) -> uuid.UUID:
        if not current_user.company_id:
            raise PermissionDeniedError("No company context")
        return uuid.UUID(current_user.company_id)

    @staticmethod
    def _invoice_number() -> str:
        now = datetime.now(timezone.utc)
        return f"INV-{now:%Y%m}-{uuid.uuid4().hex[:12].upper()}"

    async def list_plans(self) -> list[PlanResponse]:
        plans = list(
            await self.db.scalars(
                select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.price_monthly_minor)
            )
        )
        return [PlanResponse.model_validate(plan) for plan in plans]

    async def _subscription(self, company_id: uuid.UUID) -> tuple[Subscription, Plan]:
        row = (
            await self.db.execute(
                select(Subscription, Plan)
                .join(Plan, Plan.id == Subscription.plan_id)
                .where(Subscription.company_id == company_id)
            )
        ).one_or_none()
        if not row:
            raise NotFoundError("Subscription not found")
        return row

    async def _subscription_response(
        self, subscription: Subscription, plan: Plan
    ) -> SubscriptionResponse:
        pending_plan = (
            await self.db.get(Plan, subscription.pending_plan_id)
            if subscription.pending_plan_id
            else None
        )
        return SubscriptionResponse(
            id=subscription.id,
            company_id=subscription.company_id,
            status=subscription.status,
            plan=PlanResponse.model_validate(plan),
            pending_plan=(
                PlanResponse.model_validate(pending_plan) if pending_plan else None
            ),
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            cancel_at_period_end=subscription.cancel_at_period_end,
            cancelled_at=subscription.cancelled_at,
        )

    async def get_subscription(self, current_user: CurrentUser) -> SubscriptionResponse:
        subscription, plan = await self._subscription(self._company_id(current_user))
        return await self._subscription_response(subscription, plan)

    async def get_usage(self, current_user: CurrentUser) -> BillingUsageResponse:
        company_id = self._company_id(current_user)
        subscription, plan = await self._subscription(company_id)
        seconds = int(
            (
                await self.db.scalar(
                    select(func.coalesce(func.sum(Call.duration_seconds), 0)).where(
                        Call.company_id == company_id,
                        Call.started_at >= subscription.current_period_start,
                        Call.started_at < subscription.current_period_end,
                    )
                )
            )
            or 0
        )
        web_test_seconds = int(
            (
                await self.db.scalar(
                    select(func.coalesce(func.sum(Call.duration_seconds), 0)).where(
                        Call.company_id == company_id,
                        Call.source == CallSource.WEB_TEST,
                        Call.started_at >= subscription.current_period_start,
                        Call.started_at < subscription.current_period_end,
                    )
                )
            )
            or 0
        )
        agent_count = int(
            (await self.db.scalar(select(func.count(Agent.id)).where(Agent.company_id == company_id)))
            or 0
        )
        integration_count = int(
            (
                await self.db.scalar(
                    select(func.count(Integration.id)).where(Integration.company_id == company_id)
                )
            )
            or 0
        )
        minutes_used = round(seconds / 60, 2)
        minutes_remaining = (
            round(max(plan.monthly_minutes - minutes_used, 0), 2)
            if plan.monthly_minutes is not None
            else None
        )
        return BillingUsageResponse(
            period_start=subscription.current_period_start,
            period_end=subscription.current_period_end,
            minutes_used=minutes_used,
            minutes_included=plan.monthly_minutes,
            minutes_remaining=minutes_remaining,
            telephony_minutes_used=round((seconds - web_test_seconds) / 60, 2),
            web_test_minutes_used=round(web_test_seconds / 60, 2),
            web_test_max_duration_seconds_per_call=settings.WEB_TEST_CALL_MAX_DURATION_SECONDS,
            agent_count=agent_count,
            agent_limit=plan.max_agents,
            integration_count=integration_count,
            integration_limit=plan.max_integrations,
        )

    async def list_invoices(
        self, current_user: CurrentUser, page: int, page_size: int
    ) -> PaginatedResponse[InvoiceResponse]:
        company_id = self._company_id(current_user)
        query = select(Invoice).where(Invoice.company_id == company_id)
        total = int(
            (await self.db.scalar(select(func.count()).select_from(query.subquery()))) or 0
        )
        invoices = list(
            await self.db.scalars(
                query.order_by(Invoice.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return PaginatedResponse(
            items=[InvoiceResponse.model_validate(invoice) for invoice in invoices],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def get_invoice(
        self, invoice_id: uuid.UUID, current_user: CurrentUser
    ) -> InvoiceResponse:
        invoice = await self.db.scalar(
            select(Invoice).where(
                Invoice.id == invoice_id,
                Invoice.company_id == self._company_id(current_user),
            )
        )
        if not invoice:
            raise NotFoundError("Invoice not found")
        return InvoiceResponse.model_validate(invoice)

    async def list_payments(
        self, current_user: CurrentUser, page: int, page_size: int
    ) -> PaginatedResponse[PaymentResponse]:
        company_id = self._company_id(current_user)
        query = select(Payment).where(Payment.company_id == company_id)
        total = int(
            (await self.db.scalar(select(func.count()).select_from(query.subquery()))) or 0
        )
        payments = list(
            await self.db.scalars(
                query.order_by(Payment.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return PaginatedResponse(
            items=[PaymentResponse.model_validate(payment) for payment in payments],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def change_plan(
        self, plan_id: uuid.UUID, current_user: CurrentUser
    ) -> PlanChangeResponse:
        company_id = self._company_id(current_user)
        subscription, current_plan = await self._subscription(company_id)
        plan = await self.db.scalar(
            select(Plan).where(Plan.id == plan_id, Plan.is_active.is_(True))
        )
        if not plan:
            raise NotFoundError("Plan not found")
        if plan.id == subscription.plan_id:
            raise ConflictError("Subscription already uses this plan")
        existing = None
        if subscription.pending_plan_id:
            existing = await self.db.scalar(
                select(Invoice.id).where(
                    Invoice.subscription_id == subscription.id,
                    Invoice.status == InvoiceStatus.OPEN,
                )
            )
        if subscription.pending_plan_id or existing:
            raise ConflictError("An unpaid plan-change invoice already exists")

        if plan.price_monthly_minor == 0:
            subscription.plan_id = plan.id
            subscription.pending_plan_id = None
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.cancel_at_period_end = False
            subscription.cancelled_at = None
            await self.db.commit()
            return PlanChangeResponse(
                subscription=await self._subscription_response(subscription, plan),
                invoice=None,
                requires_payment=False,
            )

        invoice = Invoice(
            company_id=company_id,
            subscription_id=subscription.id,
            number=self._invoice_number(),
            status=InvoiceStatus.OPEN,
            currency=plan.currency,
            subtotal_minor=plan.price_monthly_minor,
            tax_minor=0,
            total_minor=plan.price_monthly_minor,
            amount_paid_minor=0,
            amount_due_minor=plan.price_monthly_minor,
            description=f"Plan change: {current_plan.name} to {plan.name}",
            period_start=subscription.current_period_end,
            metadata_={"change_type": "plan_change", "plan_id": str(plan.id)},
        )
        subscription.pending_plan_id = plan.id
        self.db.add(invoice)
        await self.db.commit()
        await self.db.refresh(invoice)
        return PlanChangeResponse(
            subscription=await self._subscription_response(subscription, current_plan),
            invoice=InvoiceResponse.model_validate(invoice),
            requires_payment=True,
        )

    async def set_cancel_at_period_end(
        self, current_user: CurrentUser, value: bool
    ) -> SubscriptionResponse:
        subscription, plan = await self._subscription(self._company_id(current_user))
        if subscription.status in (SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED):
            raise ConflictError("Subscription is no longer active")
        subscription.cancel_at_period_end = value
        subscription.cancelled_at = datetime.now(timezone.utc) if value else None
        await self.db.commit()
        return await self._subscription_response(subscription, plan)


class AdminBillingService(BillingService):
    def __init__(
        self, db: AsyncSession, stripe_gateway: StripeGateway | None = None
    ) -> None:
        super().__init__(db)
        self.stripe_gateway = stripe_gateway or StripeGateway()

    async def _create_stripe_product(self, plan: Plan) -> None:
        product = await self.stripe_gateway.create_product(
            name=plan.name,
            plan_id=str(plan.id),
            plan_slug=plan.slug,
            active=plan.is_active,
        )
        if not product.get("id"):
            raise ValidationError("Stripe returned an invalid Product")
        plan.stripe_product_id = str(product["id"])

    async def _create_stripe_price(
        self, plan: Plan, *, previous_price_id: str | None = None
    ) -> None:
        if not plan.stripe_product_id:
            raise ValidationError("Stripe Product is missing for this plan")
        price = await self.stripe_gateway.create_recurring_price(
            product_id=plan.stripe_product_id,
            unit_amount=plan.price_monthly_minor,
            currency=plan.currency,
            plan_id=str(plan.id),
            plan_slug=plan.slug,
            previous_price_id=previous_price_id,
        )
        if not price.get("id"):
            raise ValidationError("Stripe returned an invalid recurring Price")
        plan.stripe_price_id = str(price["id"])

    async def create_plan(self, data: AdminPlanCreate) -> PlanResponse:
        if await self.db.scalar(select(Plan.id).where(Plan.slug == data.slug)):
            raise ConflictError("Plan slug already exists")
        if data.price_monthly_minor == 0 and data.stripe_price_id:
            raise ValidationError("Free plans cannot have a Stripe Price")

        plan = Plan(id=uuid.uuid4(), **data.model_dump())
        if plan.price_monthly_minor > 0 and not plan.stripe_price_id:
            await self._create_stripe_product(plan)
            await self._create_stripe_price(plan)
        self.db.add(plan)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictError("Plan slug already exists") from exc
        await self.db.refresh(plan)
        return PlanResponse.model_validate(plan)

    async def update_plan(
        self, plan_id: uuid.UUID, data: AdminPlanUpdate
    ) -> PlanResponse:
        plan = await self.db.get(Plan, plan_id)
        if not plan:
            raise NotFoundError("Plan not found")
        values = data.model_dump(exclude_unset=True)
        old_price_id = plan.stripe_price_id
        old_amount = plan.price_monthly_minor
        old_currency = plan.currency
        explicit_price = "stripe_price_id" in values
        for key, value in values.items():
            setattr(plan, key, value)

        if plan.price_monthly_minor == 0:
            if plan.stripe_price_id and explicit_price:
                raise ValidationError("Free plans cannot have a Stripe Price")
            plan.stripe_price_id = None
            if plan.stripe_product_id:
                await self.stripe_gateway.update_product(
                    product_id=plan.stripe_product_id,
                    name=plan.name,
                    active=False,
                )
        else:
            product_created = False
            if not plan.stripe_product_id and not (
                explicit_price and plan.stripe_price_id
            ):
                await self._create_stripe_product(plan)
                product_created = True
            elif plan.stripe_product_id and (
                "name" in values
                or "is_active" in values
                or old_amount == 0
            ):
                await self.stripe_gateway.update_product(
                    product_id=plan.stripe_product_id,
                    name=plan.name,
                    active=plan.is_active,
                )

            price_terms_changed = (
                plan.price_monthly_minor != old_amount
                or plan.currency != old_currency
            )
            if not explicit_price and (
                not plan.stripe_price_id or price_terms_changed or product_created
            ):
                await self._create_stripe_price(
                    plan, previous_price_id=old_price_id
                )

        await self.db.commit()
        if old_price_id and old_price_id != plan.stripe_price_id:
            try:
                await self.stripe_gateway.archive_price(price_id=old_price_id)
            except Exception:
                # The local plan must continue pointing at its newly committed
                # Price. A later retry can safely archive the old one.
                logger.exception(
                    "Could not archive replaced Stripe Price %s", old_price_id
                )
        return PlanResponse.model_validate(plan)

    async def delete_plan(self, plan_id: uuid.UUID) -> None:
        plan = await self.db.get(Plan, plan_id)
        if not plan:
            raise NotFoundError("Plan not found")

        subscription_id = await self.db.scalar(
            select(Subscription.id)
            .where(
                or_(
                    Subscription.plan_id == plan_id,
                    Subscription.pending_plan_id == plan_id,
                )
            )
            .limit(1)
        )
        if subscription_id:
            raise ConflictError("Plan is currently used by a subscription")

        stripe_price_id = plan.stripe_price_id
        stripe_product_id = plan.stripe_product_id
        plan_name = plan.name
        await self.db.delete(plan)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictError("Plan cannot be deleted because it is in use") from exc

        if stripe_price_id:
            try:
                await self.stripe_gateway.archive_price(price_id=stripe_price_id)
            except Exception:
                logger.exception(
                    "Could not archive Stripe Price %s for deleted plan %s",
                    stripe_price_id,
                    plan_id,
                )
        if stripe_product_id:
            try:
                await self.stripe_gateway.update_product(
                    product_id=stripe_product_id,
                    name=plan_name,
                    active=False,
                )
            except Exception:
                logger.exception(
                    "Could not deactivate Stripe Product %s for deleted plan %s",
                    stripe_product_id,
                    plan_id,
                )

    async def create_invoice(self, data: AdminInvoiceCreate) -> InvoiceResponse:
        company = await self.db.get(Company, data.company_id)
        if not company:
            raise NotFoundError("Company not found")
        subscription = await self.db.scalar(
            select(Subscription).where(Subscription.company_id == data.company_id)
        )
        total = data.amount_minor + data.tax_minor
        invoice = Invoice(
            company_id=data.company_id,
            subscription_id=subscription.id if subscription else None,
            number=self._invoice_number(),
            status=InvoiceStatus.OPEN,
            currency=data.currency,
            subtotal_minor=data.amount_minor,
            tax_minor=data.tax_minor,
            total_minor=total,
            amount_paid_minor=0,
            amount_due_minor=total,
            description=data.description,
            due_at=data.due_at,
            metadata_=data.metadata,
        )
        self.db.add(invoice)
        await self.db.commit()
        await self.db.refresh(invoice)
        return InvoiceResponse.model_validate(invoice)

    async def list_all_invoices(
        self, page: int, page_size: int, company_id: uuid.UUID | None
    ) -> PaginatedResponse[InvoiceResponse]:
        query = select(Invoice)
        if company_id:
            query = query.where(Invoice.company_id == company_id)
        total = int(
            (await self.db.scalar(select(func.count()).select_from(query.subquery()))) or 0
        )
        invoices = list(
            await self.db.scalars(
                query.order_by(Invoice.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return PaginatedResponse(
            items=[InvoiceResponse.model_validate(invoice) for invoice in invoices],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def get_any_invoice(self, invoice_id: uuid.UUID) -> InvoiceResponse:
        invoice = await self.db.get(Invoice, invoice_id)
        if not invoice:
            raise NotFoundError("Invoice not found")
        return InvoiceResponse.model_validate(invoice)

    async def list_all_payments(
        self, page: int, page_size: int, company_id: uuid.UUID | None
    ) -> PaginatedResponse[PaymentResponse]:
        query = select(Payment)
        if company_id:
            query = query.where(Payment.company_id == company_id)
        total = int(
            (await self.db.scalar(select(func.count()).select_from(query.subquery()))) or 0
        )
        payments = list(
            await self.db.scalars(
                query.order_by(Payment.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return PaginatedResponse(
            items=[PaymentResponse.model_validate(payment) for payment in payments],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def record_payment(
        self, invoice_id: uuid.UUID, data: PaymentRecordRequest
    ) -> PaymentResponse:
        invoice = await self.db.scalar(
            select(Invoice).where(Invoice.id == invoice_id).with_for_update()
        )
        if not invoice:
            raise NotFoundError("Invoice not found")
        if invoice.status != InvoiceStatus.OPEN:
            raise ConflictError("Only open invoices can receive payments")
        if data.amount_minor > invoice.amount_due_minor:
            raise ValidationError("Payment exceeds the invoice amount due")
        if data.external_reference:
            existing = await self.db.scalar(
                select(Payment).where(
                    Payment.external_reference == data.external_reference
                )
            )
            if existing:
                if (
                    existing.invoice_id == invoice.id
                    and existing.amount_minor == data.amount_minor
                    and existing.status == PaymentStatus.SUCCEEDED
                ):
                    return PaymentResponse.model_validate(existing)
                raise ConflictError("Payment reference belongs to another payment")

        now = datetime.now(timezone.utc)
        payment = Payment(
            company_id=invoice.company_id,
            invoice_id=invoice.id,
            status=PaymentStatus.SUCCEEDED,
            amount_minor=data.amount_minor,
            currency=invoice.currency,
            provider=data.provider,
            external_reference=data.external_reference,
            paid_at=now,
            metadata_=data.metadata,
        )
        invoice.amount_paid_minor += data.amount_minor
        invoice.amount_due_minor -= data.amount_minor
        if invoice.amount_due_minor == 0:
            invoice.status = InvoiceStatus.PAID
            invoice.paid_at = now
            await self._activate_paid_plan_change(invoice, now)
        self.db.add(payment)
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictError("Payment reference already exists") from exc
        await self.db.refresh(payment)
        return PaymentResponse.model_validate(payment)

    async def _activate_paid_plan_change(
        self, invoice: Invoice, now: datetime
    ) -> None:
        metadata = invoice.metadata_ or {}
        if metadata.get("change_type") != "plan_change" or not invoice.subscription_id:
            return
        try:
            plan_id = uuid.UUID(metadata["plan_id"])
        except (KeyError, ValueError) as exc:
            raise ValidationError("Invoice has invalid plan-change metadata") from exc
        subscription = await self.db.get(Subscription, invoice.subscription_id)
        plan = await self.db.get(Plan, plan_id)
        if not subscription or not plan:
            raise ValidationError("Plan-change target no longer exists")
        old_period_start = subscription.current_period_start
        old_period_end = subscription.current_period_end
        subscription.plan_id = plan.id
        subscription.pending_plan_id = None
        subscription.status = SubscriptionStatus.ACTIVE
        # Preserve the configured period length instead of assuming calendar months.
        period_length = old_period_end - old_period_start
        if period_length.total_seconds() <= 0:
            from datetime import timedelta

            period_length = timedelta(days=30)
        subscription.current_period_start = now
        subscription.current_period_end = now + period_length
        subscription.cancel_at_period_end = False
        subscription.cancelled_at = None

    async def void_invoice(self, invoice_id: uuid.UUID) -> InvoiceResponse:
        invoice = await self.db.get(Invoice, invoice_id)
        if not invoice:
            raise NotFoundError("Invoice not found")
        if invoice.status != InvoiceStatus.OPEN:
            raise ConflictError("Only open invoices can be voided")
        if invoice.amount_paid_minor:
            raise ConflictError("An invoice with payments cannot be voided")
        invoice.status = InvoiceStatus.VOID
        invoice.voided_at = datetime.now(timezone.utc)
        invoice.amount_due_minor = 0
        if invoice.subscription_id:
            subscription = await self.db.get(Subscription, invoice.subscription_id)
            if subscription and (invoice.metadata_ or {}).get("change_type") == "plan_change":
                subscription.pending_plan_id = None
        await self.db.commit()
        return InvoiceResponse.model_validate(invoice)
