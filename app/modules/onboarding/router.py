from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser, get_current_user
from app.modules.onboarding.schemas import (
    CompanyOnboardingUpdate,
    OnboardingCompleteResponse,
    OnboardingStatusResponse,
)
from app.modules.onboarding.service import OnboardingService

router = APIRouter()


@router.get("/status", response_model=OnboardingStatusResponse)
async def onboarding_status(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await OnboardingService(db).status(current_user)


@router.patch("/company", response_model=OnboardingStatusResponse)
async def update_onboarding_company(
    data: CompanyOnboardingUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await OnboardingService(db).update_company(data, current_user)


@router.post("/complete", response_model=OnboardingCompleteResponse)
async def complete_onboarding(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await OnboardingService(db).complete(current_user)
