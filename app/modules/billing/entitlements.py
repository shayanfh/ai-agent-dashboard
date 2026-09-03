import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntitlementError
from app.modules.agents.models import Agent
from app.modules.billing.models import Plan, Subscription, SubscriptionStatus
from app.modules.calls.models import Call
from app.modules.integrations.models import Integration


@dataclass(frozen=True)
class EntitlementContext:
    subscription: Subscription
    plan: Plan
    used_seconds: int | None = None


class EntitlementService:
    """Single source of truth for paid-feature access and plan limits."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    async def require_active_subscription(
        self, company_id: uuid.UUID, *, lock: bool = False
    ) -> EntitlementContext:
        query = (
            select(Subscription, Plan)
            .join(Plan, Plan.id == Subscription.plan_id)
            .where(Subscription.company_id == company_id)
        )
        if lock:
            query = query.with_for_update()
        row = (await self.db.execute(query)).one_or_none()
        if not row:
            raise EntitlementError(
                "SUBSCRIPTION_REQUIRED",
                "An active subscription is required for this operation.",
            )
        subscription, plan = row
        if subscription.status not in {
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.TRIAL,
        }:
            raise EntitlementError(
                "SUBSCRIPTION_INACTIVE",
                "The company subscription is not active.",
                {"status": subscription.status.value},
            )
        if not plan.is_active:
            raise EntitlementError(
                "PLAN_UNAVAILABLE",
                "The subscribed plan is no longer available.",
                {"plan_id": str(plan.id), "plan_slug": plan.slug},
            )
        now = datetime.now(timezone.utc)
        period_start = self._utc(subscription.current_period_start)
        period_end = self._utc(subscription.current_period_end)
        if now < period_start or now >= period_end:
            raise EntitlementError(
                "SUBSCRIPTION_PERIOD_INACTIVE",
                "The current subscription period is not active.",
                {
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                },
            )
        return EntitlementContext(subscription=subscription, plan=plan)

    async def require_resource_capacity(
        self,
        company_id: uuid.UUID,
        resource: Literal["agents", "integrations"],
    ) -> EntitlementContext:
        # Locking the company's unique subscription row serializes competing creates.
        context = await self.require_active_subscription(company_id, lock=True)
        model, limit = (
            (Agent, context.plan.max_agents)
            if resource == "agents"
            else (Integration, context.plan.max_integrations)
        )
        if limit is None:
            return context
        used = int(
            await self.db.scalar(
                select(func.count(model.id)).where(model.company_id == company_id)
            )
            or 0
        )
        if used >= limit:
            raise EntitlementError(
                "PLAN_LIMIT_REACHED",
                f"The plan limit for {resource} has been reached.",
                {"resource": resource, "used": used, "limit": limit},
                status_code=409,
            )
        return context

    async def require_minutes_available(
        self, company_id: uuid.UUID, *, lock: bool = False
    ) -> EntitlementContext:
        context = await self.require_active_subscription(company_id, lock=lock)
        used_seconds = int(
            await self.db.scalar(
                select(func.coalesce(func.sum(Call.duration_seconds), 0)).where(
                    Call.company_id == company_id,
                    Call.started_at >= context.subscription.current_period_start,
                    Call.started_at < context.subscription.current_period_end,
                )
            )
            or 0
        )
        limit_minutes = context.plan.monthly_minutes
        if limit_minutes is not None and used_seconds >= limit_minutes * 60:
            raise EntitlementError(
                "MONTHLY_MINUTES_EXHAUSTED",
                "The monthly call-minute allowance has been exhausted.",
                {
                    "used_seconds": used_seconds,
                    "limit_seconds": limit_minutes * 60,
                    "used_minutes": round(used_seconds / 60, 2),
                    "limit_minutes": limit_minutes,
                },
            )
        return EntitlementContext(
            subscription=context.subscription,
            plan=context.plan,
            used_seconds=used_seconds,
        )
