from typing import Optional
from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_calls: int
    calls_today: int
    answered_calls: int
    missed_calls: int
    failed_calls: int
    average_call_duration_seconds: Optional[float]
    requests_created: int
    transferred_calls: int
    total_minutes_used: float


class CallVolumePoint(BaseModel):
    date: str
    total_calls: int
    answered_calls: int
    missed_calls: int


class CallVolumeResponse(BaseModel):
    data: list[CallVolumePoint]
    period_days: int


class OutcomeCount(BaseModel):
    outcome: str
    count: int


class OutcomesResponse(BaseModel):
    data: list[OutcomeCount]
