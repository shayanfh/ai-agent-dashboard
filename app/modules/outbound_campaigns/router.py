# ruff: noqa: B008
import io
import uuid

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import (
    CurrentUser,
    get_current_user,
    require_company_admin,
    verify_internal_api_key,
)
from app.core.schemas import PaginatedResponse
from app.modules.outbound_campaigns.models import CampaignStatus
from app.modules.outbound_campaigns.schemas import (
    AudioGenerateRequest,
    AudioPlaybackResponse,
    AudioResponse,
    CampaignCreate,
    CampaignResponse,
    CampaignScheduleRequest,
    CampaignTestCallRequest,
    CampaignUpdate,
    CampaignValidationResponse,
    DoNotCallCreate,
    DoNotCallResponse,
    ImportResponse,
    OutboundEventRequest,
    RecipientResponse,
    SingleOutboundCallRequest,
)
from app.modules.outbound_campaigns.service import OutboundCampaignService

router = APIRouter()
internal_router = APIRouter()


@router.get("", response_model=PaginatedResponse[CampaignResponse])
async def list_campaigns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundCampaignService(db).list(current_user, page, page_size)


@router.post("", response_model=CampaignResponse, status_code=201)
async def create_campaign(
    data: CampaignCreate,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundCampaignService(db).create(data, current_user)


@router.post("/single-call", response_model=CampaignResponse, status_code=202)
async def single_call(
    data: SingleOutboundCallRequest,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundCampaignService(db).single_call(data, current_user)


@router.get("/do-not-call", response_model=list[DoNotCallResponse])
async def list_dnc(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundCampaignService(db).list_dnc(current_user)


@router.post("/do-not-call", response_model=DoNotCallResponse, status_code=201)
async def add_dnc(
    data: DoNotCallCreate,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundCampaignService(db).add_dnc(data, current_user)


@router.delete("/do-not-call/{entry_id}", status_code=204)
async def delete_dnc(
    entry_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    await OutboundCampaignService(db).delete_dnc(entry_id, current_user)
    return Response(status_code=204)


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundCampaignService(db).get(campaign_id, current_user)


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: uuid.UUID,
    data: CampaignUpdate,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundCampaignService(db).update(campaign_id, data, current_user)


@router.post("/{campaign_id}/contacts/import", response_model=ImportResponse)
async def import_contacts(
    campaign_id: uuid.UUID,
    file: UploadFile = File(...),
    replace: bool = Query(False),
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    return await OutboundCampaignService(db).import_contacts(
        campaign_id, file.filename or "contacts.csv", content, current_user, replace
    )


@router.get(
    "/{campaign_id}/recipients", response_model=PaginatedResponse[RecipientResponse]
)
async def list_recipients(
    campaign_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundCampaignService(db).recipients(
        campaign_id, current_user, page, page_size
    )


@router.post("/{campaign_id}/validate", response_model=CampaignValidationResponse)
async def validate_campaign(
    campaign_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundCampaignService(db).validate(campaign_id, current_user)


@router.post("/{campaign_id}/audio", response_model=AudioResponse)
async def generate_audio(
    campaign_id: uuid.UUID,
    data: AudioGenerateRequest | None = None,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundCampaignService(db).generate_audio(
        campaign_id, current_user, data
    )


@router.get("/{campaign_id}/audio", response_model=AudioPlaybackResponse)
async def get_campaign_audio(
    campaign_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundCampaignService(db).get_audio_url(
        campaign_id, current_user
    )


@router.post(
    "/{campaign_id}/test-call", response_model=CampaignResponse, status_code=202
)
async def test_campaign_call(
    campaign_id: uuid.UUID,
    data: CampaignTestCallRequest,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundCampaignService(db).test_call(campaign_id, data, current_user)


@router.post("/{campaign_id}/schedule", response_model=CampaignResponse)
async def schedule_campaign(
    campaign_id: uuid.UUID,
    data: CampaignScheduleRequest,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundCampaignService(db).schedule(campaign_id, data, current_user)


@router.post("/{campaign_id}/start", response_model=CampaignResponse, status_code=202)
async def start_campaign(
    campaign_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundCampaignService(db).start(campaign_id, current_user)


@router.post("/{campaign_id}/pause", response_model=CampaignResponse)
async def pause_campaign(
    campaign_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundCampaignService(db).set_status(
        campaign_id, CampaignStatus.PAUSED, current_user
    )


@router.post("/{campaign_id}/resume", response_model=CampaignResponse, status_code=202)
async def resume_campaign(
    campaign_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundCampaignService(db).set_status(
        campaign_id, CampaignStatus.RUNNING, current_user
    )


@router.post("/{campaign_id}/cancel", response_model=CampaignResponse)
async def cancel_campaign(
    campaign_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await OutboundCampaignService(db).set_status(
        campaign_id, CampaignStatus.CANCELLED, current_user
    )


@router.get("/{campaign_id}/results/export")
async def export_results(
    campaign_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    content = await OutboundCampaignService(db).export_results(
        campaign_id, current_user
    )
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="campaign-{campaign_id}.xlsx"'
        },
    )


@internal_router.post("/outbound/events", status_code=status.HTTP_204_NO_CONTENT)
async def outbound_event(
    data: OutboundEventRequest,
    _: None = Depends(verify_internal_api_key),
    db: AsyncSession = Depends(get_db),
):
    await OutboundCampaignService(db).apply_event(data)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
