import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast, Date
from app.core.dependencies import CurrentUser
from app.core.exceptions import PermissionDeniedError
from app.modules.calls.models import Call, CallStatus, CallOutcome
from app.modules.requests.models import Request
from app.modules.dashboard.schemas import (
    DashboardSummary, CallVolumeResponse, CallVolumePoint,
    OutcomesResponse, OutcomeCount,
)


class DashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _get_company_id(self, current_user: CurrentUser) -> uuid.UUID:
        if not current_user.company_id:
            raise PermissionDeniedError("No company context")
        return uuid.UUID(current_user.company_id)

    async def get_summary(self, current_user: CurrentUser) -> DashboardSummary:
        company_id = self._get_company_id(current_user)
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Total calls
        total_calls_result = await self.db.execute(
            select(func.count()).select_from(Call).where(Call.company_id == company_id)
        )
        total_calls = total_calls_result.scalar_one()

        # Calls today
        calls_today_result = await self.db.execute(
            select(func.count()).select_from(Call).where(
                Call.company_id == company_id,
                Call.started_at >= today_start,
            )
        )
        calls_today = calls_today_result.scalar_one()

        # Answered calls
        answered_result = await self.db.execute(
            select(func.count()).select_from(Call).where(
                Call.company_id == company_id,
                Call.status.in_([CallStatus.ANSWERED, CallStatus.IN_PROGRESS, CallStatus.COMPLETED, CallStatus.TRANSFERRED]),
            )
        )
        answered_calls = answered_result.scalar_one()

        # Missed calls
        missed_result = await self.db.execute(
            select(func.count()).select_from(Call).where(
                Call.company_id == company_id,
                Call.status == CallStatus.MISSED,
            )
        )
        missed_calls = missed_result.scalar_one()

        # Failed calls
        failed_result = await self.db.execute(
            select(func.count()).select_from(Call).where(
                Call.company_id == company_id,
                Call.status == CallStatus.FAILED,
            )
        )
        failed_calls = failed_result.scalar_one()

        # Average duration
        avg_result = await self.db.execute(
            select(func.avg(Call.duration_seconds)).where(
                Call.company_id == company_id,
                Call.duration_seconds.isnot(None),
            )
        )
        avg_duration = avg_result.scalar_one()

        # Total minutes
        sum_result = await self.db.execute(
            select(func.sum(Call.duration_seconds)).where(
                Call.company_id == company_id,
                Call.duration_seconds.isnot(None),
            )
        )
        total_seconds = sum_result.scalar_one() or 0

        # Requests created
        req_result = await self.db.execute(
            select(func.count()).select_from(Request).where(Request.company_id == company_id)
        )
        requests_created = req_result.scalar_one()

        # Transferred calls
        transferred_result = await self.db.execute(
            select(func.count()).select_from(Call).where(
                Call.company_id == company_id,
                Call.was_transferred == True,
            )
        )
        transferred_calls = transferred_result.scalar_one()

        return DashboardSummary(
            total_calls=total_calls,
            calls_today=calls_today,
            answered_calls=answered_calls,
            missed_calls=missed_calls,
            failed_calls=failed_calls,
            average_call_duration_seconds=float(avg_duration) if avg_duration else None,
            requests_created=requests_created,
            transferred_calls=transferred_calls,
            total_minutes_used=round(total_seconds / 60, 2),
        )

    async def get_call_volume(self, current_user: CurrentUser, days: int = 7) -> CallVolumeResponse:
        company_id = self._get_company_id(current_user)
        since = datetime.now(timezone.utc) - timedelta(days=days)

        date_col = cast(Call.started_at, Date).label("date")
        result = await self.db.execute(
            select(
                date_col,
                func.count().label("total"),
                func.count().filter(
                    Call.status.in_([CallStatus.ANSWERED, CallStatus.COMPLETED, CallStatus.IN_PROGRESS, CallStatus.TRANSFERRED])
                ).label("answered"),
                func.count().filter(Call.status == CallStatus.MISSED).label("missed"),
            )
            .where(Call.company_id == company_id, Call.started_at >= since)
            .group_by(date_col)
            .order_by(date_col)
        )
        rows = result.all()
        data = [
            CallVolumePoint(
                date=str(row.date),
                total_calls=row.total,
                answered_calls=row.answered,
                missed_calls=row.missed,
            )
            for row in rows
        ]
        return CallVolumeResponse(data=data, period_days=days)

    async def get_outcomes(self, current_user: CurrentUser) -> OutcomesResponse:
        company_id = self._get_company_id(current_user)
        result = await self.db.execute(
            select(Call.outcome, func.count().label("count"))
            .where(Call.company_id == company_id, Call.outcome.isnot(None))
            .group_by(Call.outcome)
            .order_by(func.count().desc())
        )
        rows = result.all()
        data = [
            OutcomeCount(outcome=row.outcome.value if hasattr(row.outcome, "value") else str(row.outcome), count=row.count)
            for row in rows
        ]
        return OutcomesResponse(data=data)
