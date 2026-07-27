import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user, CurrentUser
from app.modules.requests.models import RequestStatus, RequestType
from app.modules.requests.schemas import RequestCreate, RequestUpdate, RequestResponse
from app.modules.requests.service import RequestService
from app.core.schemas import PaginatedResponse

router = APIRouter()


@router.get("", response_model=PaginatedResponse[RequestResponse])
async def list_requests(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[RequestStatus] = None,
    request_type: Optional[RequestType] = None,
    agent_id: Optional[uuid.UUID] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    search: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RequestService(db)
    return await service.list_requests(
        current_user, page, page_size, status, request_type, agent_id, date_from, date_to, search
    )


@router.post("", response_model=RequestResponse, status_code=201)
async def create_request(
    data: RequestCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RequestService(db)
    return await service.create_request(data, current_user)


@router.get("/{req_id}", response_model=RequestResponse)
async def get_request(
    req_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RequestService(db)
    return await service.get_request(req_id, current_user)


@router.patch("/{req_id}", response_model=RequestResponse)
async def update_request(
    req_id: uuid.UUID,
    data: RequestUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RequestService(db)
    return await service.update_request(req_id, data, current_user)
