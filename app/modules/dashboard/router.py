from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user, CurrentUser
from app.modules.dashboard.service import DashboardService
from app.modules.dashboard.schemas import DashboardSummary, CallVolumeResponse, OutcomesResponse

router = APIRouter()


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService(db)
    return await service.get_summary(current_user)


@router.get("/call-volume", response_model=CallVolumeResponse)
async def get_call_volume(
    days: int = Query(7, ge=1, le=90),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService(db)
    return await service.get_call_volume(current_user, days)


@router.get("/outcomes", response_model=OutcomesResponse)
async def get_outcomes(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = DashboardService(db)
    return await service.get_outcomes(current_user)
