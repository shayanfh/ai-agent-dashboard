import pytest

from app.core.exceptions import IntegrationError
from app.modules.billing import stripe_gateway as gateway_module
from app.modules.billing.stripe_gateway import StripeGateway


@pytest.mark.asyncio
async def test_product_response_from_stripe_sdk_v15_is_converted(monkeypatch):
    class ProductResponse:
        def to_dict(self):
            return {"id": "prod_sdk_v15"}

    def create_product(**kwargs):
        return ProductResponse()

    monkeypatch.setattr(gateway_module.stripe.Product, "create", create_product)

    product = await StripeGateway("sk_test_fake").create_product(
        name="Starter",
        plan_id="11111111-1111-1111-1111-111111111111",
        plan_slug="starter",
        active=True,
    )

    assert product == {"id": "prod_sdk_v15"}


@pytest.mark.asyncio
async def test_product_creation_uses_plan_id_for_idempotency(monkeypatch):
    captured = {}

    def create_product(**kwargs):
        captured.update(kwargs)
        return {"id": "prod_test"}

    monkeypatch.setattr(gateway_module.stripe.Product, "create", create_product)

    product = await StripeGateway("sk_test_fake").create_product(
        name="Starter",
        plan_id="11111111-1111-1111-1111-111111111111",
        plan_slug="starter",
        active=True,
    )

    assert product["id"] == "prod_test"
    assert captured["idempotency_key"] == (
        "plan-product:11111111-1111-1111-1111-111111111111"
    )


@pytest.mark.asyncio
async def test_product_creation_exposes_safe_stripe_error_details(monkeypatch):
    class FakeStripeError(Exception):
        user_message = "The API key lacks write access to Products."
        code = "permission_denied"
        request_id = "req_test"

    def create_product(**kwargs):
        raise FakeStripeError("raw provider error")

    monkeypatch.setattr(gateway_module.stripe.Product, "create", create_product)

    with pytest.raises(IntegrationError) as raised:
        await StripeGateway("sk_test_fake").create_product(
            name="Starter",
            plan_id="11111111-1111-1111-1111-111111111111",
            plan_slug="starter",
            active=True,
        )

    assert raised.value.detail["message"] == "Stripe product creation failed"
    assert raised.value.detail["details"] == {
        "provider_message": "The API key lacks write access to Products.",
        "stripe_code": "permission_denied",
        "stripe_request_id": "req_test",
    }


@pytest.mark.asyncio
async def test_checkout_creation_exposes_safe_stripe_error_details(monkeypatch):
    class FakeStripeError(Exception):
        user_message = "No such customer: 'cus_live_old'"
        code = "resource_missing"
        request_id = "req_checkout_test"

    def create_checkout(**kwargs):
        raise FakeStripeError("raw provider error")

    monkeypatch.setattr(
        gateway_module.stripe.checkout.Session, "create", create_checkout
    )

    with pytest.raises(IntegrationError) as raised:
        await StripeGateway("sk_test_fake").create_checkout_session(
            customer_id="cus_live_old",
            price_id="price_test_new",
            company_id="11111111-1111-1111-1111-111111111111",
            plan_id="22222222-2222-2222-2222-222222222222",
            invoice_id="33333333-3333-3333-3333-333333333333",
            success_url="https://example.com/billing?checkout=success",
            cancel_url="https://example.com/billing?checkout=cancel",
        )

    assert raised.value.detail["message"] == "Stripe Checkout session creation failed"
    assert raised.value.detail["details"] == {
        "provider_message": "No such customer: 'cus_live_old'",
        "stripe_code": "resource_missing",
        "stripe_request_id": "req_checkout_test",
    }
