import math
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.schemas import PaginatedResponse
from app.modules.admin.schemas import (
    ClientOverviewResponse,
    PlanResponse,
    SubscriptionUpdate,
)
from app.modules.agents.models import Agent
from app.modules.billing.models import Plan, Subscription
from app.modules.calls.models import Call
from app.modules.companies.models import Company, CompanyStatus
from app.modules.integrations.models import Integration


class AdminClientService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _month_bounds() -> tuple[datetime, datetime]:
        now = datetime.now(timezone.utc)
        start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        if now.month == 12:
            end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
        return start, end

    async def _counts(self, model, company_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not company_ids:
            return {}
        rows = (
            await self.db.execute(
                select(model.company_id, func.count(model.id))
                .where(model.company_id.in_(company_ids))
                .group_by(model.company_id)
            )
        ).all()
        return {company_id: int(count) for company_id, count in rows}

    async def _monthly_usage(self, company_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        if not company_ids:
            return {}
        start, end = self._month_bounds()
        rows = (
            await self.db.execute(
                select(Call.company_id, func.coalesce(func.sum(Call.duration_seconds), 0))
                .where(
                    Call.company_id.in_(company_ids),
                    Call.started_at >= start,
                    Call.started_at < end,
                )
                .group_by(Call.company_id)
            )
        ).all()
        return {company_id: int(seconds) for company_id, seconds in rows}

    async def _subscriptions(
        self, company_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, tuple[Subscription, Plan]]:
        if not company_ids:
            return {}
        rows = (
            await self.db.execute(
                select(Subscription, Plan)
                .join(Plan, Plan.id == Subscription.plan_id)
                .where(Subscription.company_id.in_(company_ids))
            )
        ).all()
        return {subscription.company_id: (subscription, plan) for subscription, plan in rows}

    async def _build_items(self, companies: list[Company]) -> list[ClientOverviewResponse]:
        company_ids = [company.id for company in companies]
        agent_counts = await self._counts(Agent, company_ids)
        integration_counts = await self._counts(Integration, company_ids)
        usage_seconds = await self._monthly_usage(company_ids)
        subscriptions = await self._subscriptions(company_ids)
        items = []
        for company in companies:
            subscription_and_plan = subscriptions.get(company.id)
            subscription, plan = (
                subscription_and_plan if subscription_and_plan else (None, None)
            )
            minutes_used = round(usage_seconds.get(company.id, 0) / 60, 2)
            minutes_remaining = None
            if plan and plan.monthly_minutes is not None:
                minutes_remaining = round(max(plan.monthly_minutes - minutes_used, 0), 2)
            items.append(
                ClientOverviewResponse(
                    id=company.id,
                    name=company.name,
                    email=company.email,
                    business_type=company.business_type,
                    status=company.status,
                    package=PlanResponse.model_validate(plan) if plan else None,
                    subscription_status=subscription.status if subscription else None,
                    current_period_start=(
                        subscription.current_period_start if subscription else None
                    ),
                    current_period_end=subscription.current_period_end if subscription else None,
                    agent_count=agent_counts.get(company.id, 0),
                    monthly_minutes_used=minutes_used,
                    monthly_minutes_remaining=minutes_remaining,
                    integration_count=integration_counts.get(company.id, 0),
                    created_at=company.created_at,
                )
            )
        return items

    async def list_clients(
        self,
        page: int,
        page_size: int,
        search: str | None = None,
        status: CompanyStatus | None = None,
        plan_id: uuid.UUID | None = None,
    ) -> PaginatedResponse[ClientOverviewResponse]:
        filters = []
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(or_(Company.name.ilike(pattern), Company.email.ilike(pattern)))
        if status:
            filters.append(Company.status == status)
        query = select(Company)
        count_query = select(func.count(Company.id))
        if plan_id:
            query = query.join(Subscription).where(Subscription.plan_id == plan_id)
            count_query = count_query.join(Subscription).where(
                Subscription.plan_id == plan_id
            )
        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)
        total = int((await self.db.scalar(count_query)) or 0)
        companies = list(
            (
                await self.db.scalars(
                    query.order_by(Company.created_at.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        )
        return PaginatedResponse(
            items=await self._build_items(companies),
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def get_client(self, company_id: uuid.UUID) -> ClientOverviewResponse:
        company = await self.db.scalar(select(Company).where(Company.id == company_id))
        if not company:
            raise NotFoundError("Company not found")
        return (await self._build_items([company]))[0]

    async def list_plans(self) -> list[PlanResponse]:
        plans = (
            await self.db.scalars(select(Plan).order_by(Plan.monthly_minutes, Plan.name))
        ).all()
        return [PlanResponse.model_validate(plan) for plan in plans]

    async def update_subscription(
        self, company_id: uuid.UUID, data: SubscriptionUpdate
    ) -> ClientOverviewResponse:
        company = await self.db.scalar(select(Company).where(Company.id == company_id))
        if not company:
            raise NotFoundError("Company not found")
        plan = await self.db.scalar(select(Plan).where(Plan.id == data.plan_id))
        if not plan:
            raise NotFoundError("Plan not found")
        if not plan.is_active:
            raise ValidationError("Inactive plan cannot be assigned")

        period_start = data.current_period_start or self._month_bounds()[0]
        period_end = data.current_period_end or self._month_bounds()[1]
        if period_end <= period_start:
            raise ValidationError("current_period_end must be after current_period_start")

        subscription = await self.db.scalar(
            select(Subscription).where(Subscription.company_id == company_id)
        )
        if subscription:
            subscription.plan_id = plan.id
            subscription.status = data.status
            subscription.current_period_start = period_start
            subscription.current_period_end = period_end
        else:
            self.db.add(
                Subscription(
                    company_id=company.id,
                    plan_id=plan.id,
                    status=data.status,
                    current_period_start=period_start,
                    current_period_end=period_end,
                )
            )
        await self.db.commit()
        return await self.get_client(company_id)

