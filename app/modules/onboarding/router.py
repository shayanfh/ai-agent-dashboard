from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser, get_current_user, require_company_admin
from app.core.rate_limit import enforce_rate_limit
from app.modules.onboarding.schemas import (
    CompanyOnboardingUpdate,
    OnboardingCompleteResponse,
    OnboardingStatusResponse,
    WebsiteAnalysisRequest,
    WebsiteAnalysisResponse,
)
from app.modules.onboarding.service import OnboardingService
from app.modules.onboarding.website_analysis import WebsiteAnalyzer

router = APIRouter()


@router.post("/analyze-website", response_model=WebsiteAnalysisResponse)
async def analyze_onboarding_website(
    data: WebsiteAnalysisRequest,
    current_user: CurrentUser = Depends(require_company_admin),
):
    await enforce_rate_limit(
        f"onboarding-website:{current_user.company_id or current_user.user_id}",
        limit=5,
        window_seconds=3600,
    )
    return await WebsiteAnalyzer().analyze(str(data.website_url))


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
