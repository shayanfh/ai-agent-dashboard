import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.modules.billing.models import SubscriptionStatus
from app.modules.companies.models import CompanyStatus


class PlanResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    monthly_minutes: Optional[int]
    max_agents: Optional[int]
    max_integrations: Optional[int]
    is_active: bool

    model_config = {"from_attributes": True}


class ClientOverviewResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: Optional[str]
    business_type: Optional[str]
    status: CompanyStatus
    package: Optional[PlanResponse]
    subscription_status: Optional[SubscriptionStatus]
    current_period_start: Optional[datetime]
    current_period_end: Optional[datetime]
    agent_count: int
    monthly_minutes_used: float
    monthly_minutes_remaining: Optional[float]
    integration_count: int
    created_at: datetime


class SubscriptionUpdate(BaseModel):
    plan_id: uuid.UUID
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None

