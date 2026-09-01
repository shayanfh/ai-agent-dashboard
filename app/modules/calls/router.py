import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import CurrentUser, get_current_user
from app.core.schemas import PaginatedResponse
from app.core.storage import ObjectStorage, get_object_storage
from app.modules.calls.models import CallOutcome, CallSource, CallStatus
from app.modules.calls.schemas import (
    CallCompleteRequest,
    CallCreate,
    CallDetailResponse,
    CallMessageCreate,
    CallMessageResponse,
    CallResponse,
    CallUpdate,
)
from app.modules.calls.service import CallService

router = APIRouter()


@router.get("", response_model=PaginatedResponse[CallResponse])
async def list_calls(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    agent_id: Optional[uuid.UUID] = None,
    status: Optional[CallStatus] = None,
    outcome: Optional[CallOutcome] = None,
    caller_number: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    was_transferred: Optional[bool] = None,
    source: Optional[CallSource] = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = CallService(db)
    return await service.list_calls(
        current_user, page, page_size, agent_id, status, outcome,
        caller_number, date_from, date_to, was_transferred, source,
    )


@router.post("", response_model=CallResponse, status_code=201)
async def create_call(
    data: CallCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = CallService(db)
    return await service.create_call(data, current_user)


@router.get("/{call_id}", response_model=CallDetailResponse)
async def get_call(
    call_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = CallService(db)
    return await service.get_call(call_id, current_user)


@router.get("/{call_id}/recording-url")
async def get_call_recording_url(
    call_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
):
    call = await CallService(db).get_call(call_id, current_user)
    if not call.recording_url:
        raise HTTPException(status_code=404, detail="Call recording is not available")
    recording = (call.metadata_ or {}).get("recording", {})
    object_key = recording.get("object_key")
    if object_key:
        url = await storage.presigned_download_url(
            key=object_key,
            expires_in=settings.RECORDING_PRESIGNED_URL_EXPIRE_SECONDS,
        )
        return {
            "url": url,
            "expires_in_seconds": settings.RECORDING_PRESIGNED_URL_EXPIRE_SECONDS,
        }
    return {"url": call.recording_url, "expires_in_seconds": None}


@router.patch("/{call_id}", response_model=CallResponse)
async def update_call(
    call_id: uuid.UUID,
    data: CallUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = CallService(db)
    return await service.update_call(call_id, data, current_user)


@router.post("/{call_id}/messages", response_model=CallMessageResponse, status_code=201)
async def add_message(
    call_id: uuid.UUID,
    data: CallMessageCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = CallService(db)
    return await service.add_message(call_id, data, current_user)


@router.post("/{call_id}/complete")
async def complete_call(
    call_id: uuid.UUID,
    data: CallCompleteRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = CallService(db)
    return await service.complete_call(call_id, data, current_user)
