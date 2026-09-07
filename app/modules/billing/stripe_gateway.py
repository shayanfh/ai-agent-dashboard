import asyncio
import logging
from typing import Any

import stripe

from app.core.config import settings
from app.core.exceptions import IntegrationError


logger = logging.getLogger(__name__)


class StripeConfigurationError(IntegrationError):
    pass


class StripeWebhookError(ValueError):
    pass


def _as_dict(value: Any) -> dict:
    if hasattr(value, "to_dict_recursive"):
        return value.to_dict_recursive()
    return dict(value)


def _stripe_integration_error(message: str, exc: Exception) -> IntegrationError:
    """Keep credentials private while exposing Stripe's actionable error fields."""
    logger.exception("%s", message)
    details = {}
    provider_message = getattr(exc, "user_message", None)
    error_code = getattr(exc, "code", None)
    request_id = getattr(exc, "request_id", None)
    if provider_message:
        details["provider_message"] = str(provider_message)
    if error_code:
        details["stripe_code"] = str(error_code)
    if request_id:
        details["stripe_request_id"] = str(request_id)
    return IntegrationError(message, details or None)


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
            raise _stripe_integration_error(
                "Stripe customer creation failed", exc
            ) from exc

    async def create_product(
        self, *, name: str, plan_id: str, plan_slug: str, active: bool
    ) -> dict:
        self._require_key()
        try:
            product = await asyncio.to_thread(
                stripe.Product.create,
                name=name,
                active=active,
                metadata={"plan_id": plan_id, "plan_slug": plan_slug},
                api_key=self.api_key,
                idempotency_key=f"plan-product:{plan_id}",
            )
            return _as_dict(product)
        except Exception as exc:
            raise _stripe_integration_error(
                "Stripe product creation failed", exc
            ) from exc

    async def update_product(
        self, *, product_id: str, name: str, active: bool
    ) -> dict:
        self._require_key()
        try:
            product = await asyncio.to_thread(
                stripe.Product.modify,
                product_id,
                name=name,
                active=active,
                api_key=self.api_key,
                idempotency_key=f"plan-product-update:{product_id}:{name}:{active}",
            )
            return _as_dict(product)
        except Exception as exc:
            raise _stripe_integration_error(
                "Stripe product update failed", exc
            ) from exc

    async def create_recurring_price(
        self,
        *,
        product_id: str,
        unit_amount: int,
        currency: str,
        plan_id: str,
        plan_slug: str,
        previous_price_id: str | None,
    ) -> dict:
        self._require_key()
        try:
            price = await asyncio.to_thread(
                stripe.Price.create,
                product=product_id,
                unit_amount=unit_amount,
                currency=currency.lower(),
                recurring={"interval": "month"},
                metadata={"plan_id": plan_id, "plan_slug": plan_slug},
                api_key=self.api_key,
                idempotency_key=(
                    f"plan-price:{plan_id}:{previous_price_id or 'initial'}:"
                    f"{currency.lower()}:{unit_amount}"
                ),
            )
            return _as_dict(price)
        except Exception as exc:
            raise _stripe_integration_error(
                "Stripe recurring price creation failed", exc
            ) from exc

    async def archive_price(self, *, price_id: str) -> None:
        self._require_key()
        try:
            await asyncio.to_thread(
                stripe.Price.modify,
                price_id,
                active=False,
                api_key=self.api_key,
                idempotency_key=f"plan-price-archive:{price_id}",
            )
        except Exception as exc:
            raise _stripe_integration_error(
                "Stripe price archival failed", exc
            ) from exc

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
