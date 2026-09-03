import asyncio
from typing import Any

import stripe

from app.core.config import settings
from app.core.exceptions import IntegrationError


class StripeConfigurationError(IntegrationError):
    pass


class StripeWebhookError(ValueError):
    pass


def _as_dict(value: Any) -> dict:
    if hasattr(value, "to_dict_recursive"):
        return value.to_dict_recursive()
    return dict(value)


class StripeGateway:
    """Small async boundary around Stripe's synchronous Python SDK."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.STRIPE_SECRET_KEY

    def _require_key(self) -> None:
        if not self.api_key:
            raise StripeConfigurationError("Stripe is not configured")

    async def create_customer(
        self, *, email: str | None, name: str, company_id: str
    ) -> dict:
        self._require_key()
        try:
            customer = await asyncio.to_thread(
                stripe.Customer.create,
                email=email,
                name=name,
                metadata={"company_id": company_id},
                api_key=self.api_key,
                idempotency_key=f"company-customer:{company_id}",
            )
            return _as_dict(customer)
        except Exception as exc:
            raise IntegrationError("Stripe customer creation failed") from exc

    async def create_checkout_session(
        self,
        *,
        customer_id: str,
        price_id: str,
        company_id: str,
        plan_id: str,
        invoice_id: str,
        success_url: str,
        cancel_url: str,
    ) -> dict:
        self._require_key()
        metadata = {
            "company_id": company_id,
            "plan_id": plan_id,
            "local_invoice_id": invoice_id,
        }
        try:
            session = await asyncio.to_thread(
                stripe.checkout.Session.create,
                mode="subscription",
                customer=customer_id,
                client_reference_id=company_id,
                line_items=[{"price": price_id, "quantity": 1}],
                metadata=metadata,
                subscription_data={"metadata": metadata},
                success_url=success_url,
                cancel_url=cancel_url,
                api_key=self.api_key,
                idempotency_key=f"subscription-checkout:{invoice_id}",
            )
            return _as_dict(session)
        except Exception as exc:
            raise IntegrationError("Stripe Checkout session creation failed") from exc

    async def create_portal_session(self, *, customer_id: str, return_url: str) -> dict:
        self._require_key()
        try:
            session = await asyncio.to_thread(
                stripe.billing_portal.Session.create,
                customer=customer_id,
                return_url=return_url,
                api_key=self.api_key,
            )
            return _as_dict(session)
        except Exception as exc:
            raise IntegrationError("Stripe Customer Portal session creation failed") from exc

    async def update_subscription_cancellation(
        self, *, subscription_id: str, cancel_at_period_end: bool
    ) -> None:
        self._require_key()
        try:
            await asyncio.to_thread(
                stripe.Subscription.modify,
                subscription_id,
                cancel_at_period_end=cancel_at_period_end,
                api_key=self.api_key,
            )
        except Exception as exc:
            raise IntegrationError("Stripe subscription update failed") from exc

    @staticmethod
    def construct_webhook_event(payload: bytes, signature: str) -> dict:
        if not settings.STRIPE_WEBHOOK_SECRET:
            raise StripeWebhookError("Stripe webhook is not configured")
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, settings.STRIPE_WEBHOOK_SECRET
            )
            return _as_dict(event)
        except (ValueError, stripe.SignatureVerificationError) as exc:
            raise StripeWebhookError("Invalid Stripe webhook signature") from exc


def get_stripe_gateway() -> StripeGateway:
    return StripeGateway()
