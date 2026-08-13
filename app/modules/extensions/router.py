# ruff: noqa: B008
import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser, get_current_user, require_company_admin
from app.core.schemas import PaginatedResponse
from app.modules.extensions.schemas import (
    ExtensionCreate,
    ExtensionCredentialsResponse,
    ExtensionResponse,
    ExtensionUpdate,
)
from app.modules.extensions.service import ExtensionService

router = APIRouter()


@router.get("", response_model=PaginatedResponse[ExtensionResponse])
async def list_extensions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ExtensionService(db).list(current_user, page, page_size)


@router.post("", response_model=ExtensionCredentialsResponse, status_code=201)
async def create_extension(
    data: ExtensionCreate,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await ExtensionService(db).create(data, current_user)


@router.get("/{extension_id}", response_model=ExtensionResponse)
async def get_extension(
    extension_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ExtensionService(db).get(extension_id, current_user)


@router.patch("/{extension_id}", response_model=ExtensionResponse)
async def update_extension(
    extension_id: uuid.UUID,
    data: ExtensionUpdate,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await ExtensionService(db).update(extension_id, data, current_user)


@router.post(
    "/{extension_id}/rotate-password",
    response_model=ExtensionCredentialsResponse,
)
async def rotate_extension_password(
    extension_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await ExtensionService(db).rotate_password(extension_id, current_user)


@router.post("/{extension_id}/enable", response_model=ExtensionResponse)
async def enable_extension(
    extension_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await ExtensionService(db).set_enabled(extension_id, True, current_user)


@router.post("/{extension_id}/disable", response_model=ExtensionResponse)
async def disable_extension(
    extension_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await ExtensionService(db).set_enabled(extension_id, False, current_user)


@router.delete("/{extension_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_extension(
    extension_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await ExtensionService(db).delete(extension_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
