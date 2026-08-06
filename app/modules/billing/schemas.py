import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.modules.billing.models import InvoiceStatus, PaymentStatus, SubscriptionStatus


class PlanResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    monthly_minutes: int | None
    max_agents: int | None
    max_integrations: int | None
    price_monthly_minor: int
    currency: str
    is_active: bool

    model_config = {"from_attributes": True}


class SubscriptionResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    status: SubscriptionStatus
    plan: PlanResponse
    pending_plan: PlanResponse | None = None
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    cancelled_at: datetime | None


class BillingUsageResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    minutes_used: float
    minutes_included: int | None
    minutes_remaining: float | None
    agent_count: int
    agent_limit: int | None
    integration_count: int
    integration_limit: int | None


class InvoiceResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    subscription_id: uuid.UUID | None
    number: str
    status: InvoiceStatus
    currency: str
    subtotal_minor: int
    tax_minor: int
    total_minor: int
    amount_paid_minor: int
    amount_due_minor: int
    description: str | None
    period_start: datetime | None
    period_end: datetime | None
    due_at: datetime | None
    paid_at: datetime | None
    voided_at: datetime | None
    metadata: dict | None = Field(validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaymentResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    invoice_id: uuid.UUID | None
    status: PaymentStatus
    amount_minor: int
    currency: str
    provider: str
    external_reference: str | None
    failure_reason: str | None
    paid_at: datetime | None
    metadata: dict | None = Field(validation_alias="metadata_")
    created_at: datetime

    model_config = {"from_attributes": True}


class PlanChangeRequest(BaseModel):
    plan_id: uuid.UUID


class PlanChangeResponse(BaseModel):
    subscription: SubscriptionResponse
    invoice: InvoiceResponse | None
    requires_payment: bool


class AdminPlanCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    monthly_minutes: int | None = Field(default=None, ge=0)
    max_agents: int | None = Field(default=None, ge=0)
    max_integrations: int | None = Field(default=None, ge=0)
    price_monthly_minor: int = Field(default=0, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    is_active: bool = True

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class AdminPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    monthly_minutes: int | None = Field(default=None, ge=0)
    max_agents: int | None = Field(default=None, ge=0)
    max_integrations: int | None = Field(default=None, ge=0)
    price_monthly_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    is_active: bool | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class AdminInvoiceCreate(BaseModel):
    company_id: uuid.UUID
    amount_minor: int = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    tax_minor: int = Field(default=0, ge=0)
    description: str | None = Field(default=None, max_length=2000)
    due_at: datetime | None = None
    metadata: dict | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class PaymentRecordRequest(BaseModel):
    amount_minor: int = Field(gt=0)
    provider: str = Field(default="manual", min_length=2, max_length=50)
    external_reference: str | None = Field(default=None, max_length=255)
    metadata: dict | None = None
