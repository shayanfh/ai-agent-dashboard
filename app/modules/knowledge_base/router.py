import uuid
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.config import settings
from app.core.storage import ObjectStorage, get_object_storage
from app.core.dependencies import get_current_user, CurrentUser, require_company_admin
from app.modules.knowledge_base.models import KBItemStatus
from app.modules.knowledge_base.schemas import (
    KBItemCreate, KBItemUpdate, KBItemResponse,
    KBDocumentCreate, KBDocumentResponse,
    KBTemplateApply, KBTemplateApplyResponse, KBTemplateResponse,
)
from app.modules.knowledge_base.service import KBItemService, KBDocumentService
from app.core.schemas import PaginatedResponse
from app.modules.knowledge_base.templates import KNOWLEDGE_BASE_TEMPLATES

router = APIRouter()


@router.get("/templates", response_model=list[KBTemplateResponse])
async def list_templates():
    return KNOWLEDGE_BASE_TEMPLATES


@router.post(
    "/templates/{business_type}/apply",
    response_model=KBTemplateApplyResponse,
)
async def apply_template(
    business_type: str,
    data: KBTemplateApply,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await KBItemService(db).apply_template(
        business_type, data.agent_id, current_user
    )


@router.get("/items", response_model=PaginatedResponse[KBItemResponse])
async def list_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    agent_id: Optional[uuid.UUID] = None,
    status: Optional[KBItemStatus] = None,
    category: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = KBItemService(db)
    return await service.list_items(current_user, page, page_size, agent_id, status, category)


@router.post("/items", response_model=KBItemResponse, status_code=201)
async def create_item(
    data: KBItemCreate,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = KBItemService(db)
    return await service.create_item(data, current_user)


@router.get("/items/{item_id}", response_model=KBItemResponse)
async def get_item(
    item_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = KBItemService(db)
    return await service.get_item(item_id, current_user)


@router.patch("/items/{item_id}", response_model=KBItemResponse)
async def update_item(
    item_id: uuid.UUID,
    data: KBItemUpdate,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = KBItemService(db)
    return await service.update_item(item_id, data, current_user)


@router.delete("/items/{item_id}", status_code=204)
async def delete_item(
    item_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = KBItemService(db)
    await service.delete_item(item_id, current_user)


@router.get("/documents", response_model=PaginatedResponse[KBDocumentResponse])
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = KBDocumentService(db)
    return await service.list_documents(current_user, page, page_size)


@router.post("/documents", response_model=KBDocumentResponse, status_code=201)
async def create_document(
    data: KBDocumentCreate,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = KBDocumentService(db)
    return await service.create_document(data, current_user)


@router.post("/documents/upload", response_model=KBDocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    agent_id: Optional[uuid.UUID] = Form(None),
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
):
    content = await file.read(settings.MAX_KNOWLEDGE_UPLOAD_BYTES + 1)
    return await KBDocumentService(db, storage).create_uploaded_document(
        file_name=file.filename or "document",
        content_type=file.content_type,
        content=content,
        agent_id=agent_id,
        current_user=current_user,
    )


@router.get("/documents/{doc_id}", response_model=KBDocumentResponse)
async def get_document(
    doc_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await KBDocumentService(db).get_document(doc_id, current_user)


@router.post("/documents/{doc_id}/retry", response_model=KBDocumentResponse)
async def retry_document(
    doc_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    return await KBDocumentService(db).retry_document(doc_id, current_user)


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
    storage: ObjectStorage = Depends(get_object_storage),
):
    service = KBDocumentService(db, storage)
    await service.delete_document(doc_id, current_user)
