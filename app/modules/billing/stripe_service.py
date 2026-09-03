import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import CurrentUser
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.billing.models import (
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentStatus,
    Plan,
    StripeEvent,
    Subscription,
    SubscriptionStatus,
)
from app.modules.billing.schemas import (
    StripeCheckoutResponse,
    StripePortalResponse,
)
from app.modules.billing.service import BillingService
from app.modules.billing.stripe_gateway import StripeGateway
from app.modules.companies.models import Company
from app.modules.users.models import User


def _unix_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _stripe_id(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        identifier = value.get("id")
        return str(identifier) if identifier else None
    return None


def _subscription_id_from_invoice(data: dict) -> str | None:
    direct = _stripe_id(data.get("subscription"))
    if direct:
        return direct
    parent = data.get("parent") or {}
    details = parent.get("subscription_details") or {}
    return _stripe_id(details.get("subscription"))


def _subscription_metadata_from_invoice(data: dict) -> dict:
    parent = data.get("parent") or {}
    details = parent.get("subscription_details") or {}
    return details.get("metadata") or {}


class StripeBillingService(BillingService):
    def __init__(self, db: AsyncSession, gateway: StripeGateway) -> None:
        super().__init__(db)
        self.gateway = gateway

    @staticmethod
    def _success_url() -> str:
        return settings.STRIPE_CHECKOUT_SUCCESS_URL or (
            f"{settings.FRONTEND_URL.rstrip('/')}/billing?checkout=success"
            "&session_id={CHECKOUT_SESSION_ID}"
        )

    @staticmethod
    def _cancel_url() -> str:
        return settings.STRIPE_CHECKOUT_CANCEL_URL or (
            f"{settings.FRONTEND_URL.rstrip('/')}/billing?checkout=cancel"
        )

    async def create_checkout(
        self, plan_id: uuid.UUID, current_user: CurrentUser
    ) -> StripeCheckoutResponse:
        company_id = self._company_id(current_user)
        subscription = await self.db.scalar(
            select(Subscription)
            .where(Subscription.company_id == company_id)
            .with_for_update()
        )
        if not subscription:
            raise NotFoundError("Subscription not found")
        plan = await self.db.scalar(
            select(Plan).where(Plan.id == plan_id, Plan.is_active.is_(True))
        )
        if not plan:
            raise NotFoundError("Plan not found")
        if plan.id == subscription.plan_id:
            raise ConflictError("Subscription already uses this plan")
        if plan.price_monthly_minor <= 0:
            raise ValidationError("Free plans do not require Stripe Checkout")
        if not plan.stripe_price_id:
            raise ValidationError("This plan is not configured for Stripe")
        if subscription.stripe_subscription_id and subscription.status not in (
            SubscriptionStatus.CANCELLED,
            SubscriptionStatus.EXPIRED,
        ):
            raise ConflictError(
                "This company already has a Stripe subscription; use the billing portal"
            )

        invoice = None
        if subscription.pending_plan_id:
            invoice = await self.db.scalar(
                select(Invoice).where(
                    Invoice.subscription_id == subscription.id,
                    Invoice.status == InvoiceStatus.OPEN,
                )
            )
            if subscription.pending_plan_id != plan.id or not invoice:
                raise ConflictError("Another unpaid plan change already exists")
        if not invoice:
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
                description=f"Stripe subscription: {plan.name}",
                period_start=subscription.current_period_end,
                metadata_={"change_type": "plan_change", "plan_id": str(plan.id)},
            )
            subscription.pending_plan_id = plan.id
            self.db.add(invoice)
            await self.db.flush()

        company = await self.db.get(Company, company_id)
        if not company:
            raise NotFoundError("Company not found")
        if not company.stripe_customer_id:
            user = await self.db.get(User, uuid.UUID(current_user.user_id))
            customer = await self.gateway.create_customer(
                email=company.email or (user.email if user else None),
                name=company.name,
                company_id=str(company.id),
            )
            if not customer.get("id"):
                raise ValidationError("Stripe returned an invalid customer")
            company.stripe_customer_id = customer["id"]
            await self.db.commit()

        session = await self.gateway.create_checkout_session(
            customer_id=company.stripe_customer_id,
            price_id=plan.stripe_price_id,
            company_id=str(company.id),
            plan_id=str(plan.id),
            invoice_id=str(invoice.id),
            success_url=self._success_url(),
            cancel_url=self._cancel_url(),
        )
        if not session.get("id") or not session.get("url"):
            raise ValidationError("Stripe returned an invalid Checkout session")
        invoice.stripe_checkout_session_id = session["id"]
        await self.db.commit()
        return StripeCheckoutResponse(
            session_id=session["id"], checkout_url=session["url"]
        )

    async def create_portal(self, current_user: CurrentUser) -> StripePortalResponse:
        company = await self.db.get(Company, self._company_id(current_user))
        if not company:
            raise NotFoundError("Company not found")
        if not company.stripe_customer_id:
            raise ConflictError("This company does not have a Stripe customer")
        session = await self.gateway.create_portal_session(
            customer_id=company.stripe_customer_id,
            return_url=f"{settings.FRONTEND_URL.rstrip('/')}/billing",
        )
        if not session.get("url"):
            raise ValidationError("Stripe returned an invalid Portal session")
        return StripePortalResponse(portal_url=session["url"])

    async def set_stripe_cancellation(
        self, current_user: CurrentUser, value: bool
    ):
        subscription, _ = await self._subscription(self._company_id(current_user))
        if subscription.status in (
            SubscriptionStatus.CANCELLED,
            SubscriptionStatus.EXPIRED,
        ):
            raise ConflictError("Subscription is no longer active")
        if subscription.stripe_subscription_id:
            await self.gateway.update_subscription_cancellation(
                subscription_id=subscription.stripe_subscription_id,
                cancel_at_period_end=value,
            )
        return await self.set_cancel_at_period_end(current_user, value)

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
        period_length = subscription.current_period_end - subscription.current_period_start
        if period_length.total_seconds() <= 0:
            period_length = timedelta(days=30)
        subscription.plan_id = plan.id
        subscription.pending_plan_id = None
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.current_period_start = now
        subscription.current_period_end = now + period_length
        subscription.cancel_at_period_end = False
        subscription.cancelled_at = None

    async def process_webhook(self, event: dict) -> None:
        event_id = event.get("id")
        event_type = event.get("type")
        if not event_id or not event_type:
            raise ValidationError("Invalid Stripe event")
        if await self.db.get(StripeEvent, event_id):
            return

        # Reserve the event ID in the same transaction as its side effects. If
        # handling fails, both the reservation and changes roll back, allowing
        # Stripe to retry safely.
        self.db.add(StripeEvent(id=event_id, event_type=event_type))
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            return

        data = ((event.get("data") or {}).get("object") or {})
        if event_type in (
            "checkout.session.completed",
            "checkout.session.async_payment_succeeded",
        ):
            await self._checkout_completed(data)
        elif event_type == "invoice.paid":
            await self._invoice_paid(data)
        elif event_type == "invoice.payment_failed":
            await self._invoice_payment_failed(data)
        elif event_type == "customer.subscription.updated":
            await self._subscription_updated(data)
        elif event_type == "customer.subscription.deleted":
            await self._subscription_deleted(data)

        await self.db.commit()

    async def _checkout_completed(self, data: dict) -> None:
        if data.get("payment_status") not in ("paid", "no_payment_required"):
            return
        metadata = data.get("metadata") or {}
        try:
            company_id = uuid.UUID(metadata["company_id"])
            plan_id = uuid.UUID(metadata["plan_id"])
            invoice_id = uuid.UUID(metadata["local_invoice_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("Stripe Checkout metadata is invalid") from exc

        invoice = await self.db.scalar(
            select(Invoice).where(Invoice.id == invoice_id).with_for_update()
        )
        subscription = await self.db.scalar(
            select(Subscription)
            .where(Subscription.company_id == company_id)
            .with_for_update()
        )
        company = await self.db.get(Company, company_id)
        if not invoice or not subscription or not company:
            raise NotFoundError("Stripe Checkout target not found")
        invoice_plan_id = (invoice.metadata_ or {}).get("plan_id")
        if (
            invoice.company_id != company_id
            or invoice.subscription_id != subscription.id
            or invoice_plan_id != str(plan_id)
        ):
            raise ValidationError("Stripe Checkout metadata does not match the invoice")

        amount_total = int(data.get("amount_total") or 0)
        currency = str(data.get("currency") or "").upper()
        if invoice.status == InvoiceStatus.OPEN:
            if amount_total != invoice.amount_due_minor or currency != invoice.currency.upper():
                raise ValidationError("Stripe payment does not match the invoice")
            now = datetime.now(timezone.utc)
            invoice.amount_paid_minor = invoice.total_minor
            invoice.amount_due_minor = 0
            invoice.status = InvoiceStatus.PAID
            invoice.paid_at = now
            reference = _stripe_id(data.get("payment_intent")) or f"checkout:{data['id']}"
            existing_payment = await self.db.scalar(
                select(Payment).where(Payment.external_reference == reference)
            )
            if not existing_payment and amount_total > 0:
                self.db.add(
                    Payment(
                        company_id=company_id,
                        invoice_id=invoice.id,
                        status=PaymentStatus.SUCCEEDED,
                        amount_minor=amount_total,
                        currency=invoice.currency,
                        provider="stripe",
                        external_reference=reference,
                        paid_at=now,
                        metadata_={"checkout_session_id": data["id"]},
                    )
                )
            await self._activate_paid_plan_change(invoice, now)

        company.stripe_customer_id = _stripe_id(data.get("customer")) or company.stripe_customer_id
        subscription.stripe_subscription_id = (
            _stripe_id(data.get("subscription")) or subscription.stripe_subscription_id
        )
        invoice.stripe_checkout_session_id = data.get("id")
        invoice.stripe_invoice_id = _stripe_id(data.get("invoice"))

    async def _invoice_paid(self, data: dict) -> None:
        stripe_subscription_id = _subscription_id_from_invoice(data)
        if not stripe_subscription_id:
            return
        subscription = await self.db.scalar(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_subscription_id
            )
        )
        if not subscription:
            metadata = _subscription_metadata_from_invoice(data)
            company_id = metadata.get("company_id")
            if company_id:
                try:
                    subscription = await self.db.scalar(
                        select(Subscription).where(
                            Subscription.company_id == uuid.UUID(company_id)
                        )
                    )
                except ValueError:
                    return
        if not subscription:
            return
        subscription.stripe_subscription_id = stripe_subscription_id
        subscription.status = SubscriptionStatus.ACTIVE
        period = None
        lines = ((data.get("lines") or {}).get("data") or [])
        if lines:
            period = lines[0].get("period") or {}
        if period:
            subscription.current_period_start = (
                _unix_datetime(period.get("start")) or subscription.current_period_start
            )
            subscription.current_period_end = (
                _unix_datetime(period.get("end")) or subscription.current_period_end
            )

        stripe_invoice_id = data.get("id")
        if not stripe_invoice_id:
            return
        invoice = await self.db.scalar(
            select(Invoice).where(Invoice.stripe_invoice_id == stripe_invoice_id)
        )
        metadata = _subscription_metadata_from_invoice(data)
        if not invoice and metadata.get("local_invoice_id"):
            try:
                invoice = await self.db.get(
                    Invoice, uuid.UUID(metadata["local_invoice_id"])
                )
            except ValueError:
                invoice = None
        amount_paid = int(data.get("amount_paid") or 0)
        currency = str(data.get("currency") or "USD").upper()
        transitioned_to_paid = False
        if invoice and invoice.status == InvoiceStatus.OPEN:
            if amount_paid != invoice.amount_due_minor or currency != invoice.currency.upper():
                raise ValidationError("Stripe invoice payment does not match local invoice")
            invoice.amount_paid_minor = invoice.total_minor
            invoice.amount_due_minor = 0
            invoice.status = InvoiceStatus.PAID
            status_transitions = data.get("status_transitions") or {}
            invoice.paid_at = _unix_datetime(
                status_transitions.get("paid_at")
            ) or datetime.now(timezone.utc)
            invoice.stripe_invoice_id = stripe_invoice_id
            await self._activate_paid_plan_change(invoice, invoice.paid_at)
            transitioned_to_paid = True
        elif not invoice and amount_paid > 0:
            status_transitions = data.get("status_transitions") or {}
            paid_at = _unix_datetime(status_transitions.get("paid_at")) or datetime.now(
                timezone.utc
            )
            invoice = Invoice(
                company_id=subscription.company_id,
                subscription_id=subscription.id,
                number=f"STRIPE-{stripe_invoice_id}",
                status=InvoiceStatus.PAID,
                currency=currency,
                subtotal_minor=amount_paid,
                tax_minor=0,
                total_minor=amount_paid,
                amount_paid_minor=amount_paid,
                amount_due_minor=0,
                description="Stripe subscription renewal",
                period_start=_unix_datetime((period or {}).get("start")),
                period_end=_unix_datetime((period or {}).get("end")),
                paid_at=paid_at,
                stripe_invoice_id=stripe_invoice_id,
                metadata_={"stripe": True},
            )
            self.db.add(invoice)
            await self.db.flush()
            transitioned_to_paid = True
        if transitioned_to_paid and amount_paid > 0:
            reference = f"stripe-invoice:{stripe_invoice_id}"
            existing_payment = await self.db.scalar(
                select(Payment).where(Payment.external_reference == reference)
            )
            if not existing_payment:
                self.db.add(
                    Payment(
                        company_id=subscription.company_id,
                        invoice_id=invoice.id,
                        status=PaymentStatus.SUCCEEDED,
                        amount_minor=amount_paid,
                        currency=currency,
                        provider="stripe",
                        external_reference=reference,
                        paid_at=invoice.paid_at,
                        metadata_={"stripe_invoice_id": stripe_invoice_id},
                    )
                )

    async def _invoice_payment_failed(self, data: dict) -> None:
        stripe_subscription_id = _subscription_id_from_invoice(data)
        if not stripe_subscription_id:
            return
        subscription = await self.db.scalar(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_subscription_id
            )
        )
        if subscription:
            subscription.status = SubscriptionStatus.PAST_DUE

    async def _subscription_updated(self, data: dict) -> None:
        stripe_subscription_id = data.get("id")
        subscription = await self.db.scalar(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_subscription_id
            )
        )
        if not subscription:
            return
        status_map = {
            "trialing": SubscriptionStatus.TRIAL,
            "active": SubscriptionStatus.ACTIVE,
            "past_due": SubscriptionStatus.PAST_DUE,
            "unpaid": SubscriptionStatus.PAST_DUE,
            "canceled": SubscriptionStatus.CANCELLED,
            "paused": SubscriptionStatus.EXPIRED,
        }
        if data.get("status") in status_map:
            subscription.status = status_map[data["status"]]
        subscription.cancel_at_period_end = bool(data.get("cancel_at_period_end"))
        subscription.cancelled_at = _unix_datetime(data.get("canceled_at"))
        start = _unix_datetime(data.get("current_period_start"))
        end = _unix_datetime(data.get("current_period_end"))
        items = ((data.get("items") or {}).get("data") or [])
        if items:
            start = start or _unix_datetime(items[0].get("current_period_start"))
            end = end or _unix_datetime(items[0].get("current_period_end"))
            pricing = items[0].get("pricing") or {}
            price_details = pricing.get("price_details") or {}
            price_id = (
                _stripe_id(items[0].get("price"))
                or _stripe_id(items[0].get("plan"))
                or _stripe_id(price_details.get("price"))
            )
            if price_id:
                plan = await self.db.scalar(
                    select(Plan).where(Plan.stripe_price_id == price_id)
                )
                if plan:
                    subscription.plan_id = plan.id
                    subscription.pending_plan_id = None
        subscription.current_period_start = start or subscription.current_period_start
        subscription.current_period_end = end or subscription.current_period_end

    async def _subscription_deleted(self, data: dict) -> None:
        subscription = await self.db.scalar(
            select(Subscription).where(
                Subscription.stripe_subscription_id == data.get("id")
            )
        )
        if subscription:
            subscription.status = SubscriptionStatus.CANCELLED
            subscription.cancel_at_period_end = False
            subscription.cancelled_at = (
                _unix_datetime(data.get("canceled_at")) or datetime.now(timezone.utc)
            )
