import uuid
import math
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.dependencies import CurrentUser
from app.modules.knowledge_base.models import KBItemStatus, DocumentProcessingStatus
from app.modules.knowledge_base.repository import KBItemRepository, KBDocumentRepository
from app.modules.knowledge_base.schemas import (
    KBItemCreate, KBItemUpdate, KBItemResponse,
    KBDocumentCreate, KBDocumentResponse,
)
from app.core.schemas import PaginatedResponse


class KBItemService:
    def __init__(self, db: AsyncSession):
        self.repo = KBItemRepository(db)

    def _get_company_id(self, current_user: CurrentUser) -> uuid.UUID:
        if not current_user.company_id:
            raise PermissionDeniedError("No company context")
        return uuid.UUID(current_user.company_id)

    async def list_items(
        self,
        current_user: CurrentUser,
        page: int = 1,
        page_size: int = 20,
        agent_id: Optional[uuid.UUID] = None,
        status: Optional[KBItemStatus] = None,
        category: Optional[str] = None,
    ) -> PaginatedResponse[KBItemResponse]:
        company_id = self._get_company_id(current_user)
        items, total = await self.repo.get_by_company(company_id, page, page_size, agent_id, status, category)
        return PaginatedResponse(
            items=[KBItemResponse.model_validate(i) for i in items],
            total=total, page=page, page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def get_item(self, item_id: uuid.UUID, current_user: CurrentUser) -> KBItemResponse:
        company_id = self._get_company_id(current_user)
        item = await self.repo.get_by_id_and_company(item_id, company_id)
        if not item:
            raise NotFoundError("Knowledge base item not found")
        return KBItemResponse.model_validate(item)

    async def create_item(self, data: KBItemCreate, current_user: CurrentUser) -> KBItemResponse:
        if not current_user.is_company_admin and not current_user.is_super_admin:
            raise PermissionDeniedError()
        company_id = self._get_company_id(current_user)
        item_data = data.model_dump()
        item_data["company_id"] = company_id
        item = await self.repo.create(item_data)
        return KBItemResponse.model_validate(item)

    async def update_item(self, item_id: uuid.UUID, data: KBItemUpdate, current_user: CurrentUser) -> KBItemResponse:
        if not current_user.is_company_admin and not current_user.is_super_admin:
            raise PermissionDeniedError()
        company_id = self._get_company_id(current_user)
        item = await self.repo.get_by_id_and_company(item_id, company_id)
        if not item:
            raise NotFoundError("Knowledge base item not found")
        item = await self.repo.update(item, data.model_dump(exclude_none=True))
        return KBItemResponse.model_validate(item)

    async def delete_item(self, item_id: uuid.UUID, current_user: CurrentUser) -> None:
        if not current_user.is_company_admin and not current_user.is_super_admin:
            raise PermissionDeniedError()
        company_id = self._get_company_id(current_user)
        item = await self.repo.get_by_id_and_company(item_id, company_id)
        if not item:
            raise NotFoundError("Knowledge base item not found")
        await self.repo.delete(item)


class KBDocumentService:
    def __init__(self, db: AsyncSession):
        self.repo = KBDocumentRepository(db)
        self.db = db

    def _get_company_id(self, current_user: CurrentUser) -> uuid.UUID:
        if not current_user.company_id:
            raise PermissionDeniedError("No company context")
        return uuid.UUID(current_user.company_id)

    async def list_documents(
        self, current_user: CurrentUser, page: int = 1, page_size: int = 20
    ) -> PaginatedResponse[KBDocumentResponse]:
        company_id = self._get_company_id(current_user)
        docs, total = await self.repo.get_by_company(company_id, page, page_size)
        return PaginatedResponse(
            items=[KBDocumentResponse.model_validate(d) for d in docs],
            total=total, page=page, page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def create_document(self, data: KBDocumentCreate, current_user: CurrentUser) -> KBDocumentResponse:
        if not current_user.is_company_admin and not current_user.is_super_admin:
            raise PermissionDeniedError()
        company_id = self._get_company_id(current_user)
        allowed_types = {"pdf", "txt", "docx", "md", "csv"}
        if data.file_type and data.file_type.lower().lstrip(".") not in allowed_types:
            from app.core.exceptions import ValidationError
            raise ValidationError(f"File type not supported. Allowed: {', '.join(allowed_types)}")
        doc_data = data.model_dump()
        doc_data["company_id"] = company_id
        doc_data["processing_status"] = DocumentProcessingStatus.PENDING
        doc = await self.repo.create(doc_data)
        # Queue document processing task
        try:
            from app.workers.call_tasks import process_knowledge_document
            process_knowledge_document.delay(str(doc.id))
        except Exception:
            pass
        return KBDocumentResponse.model_validate(doc)

    async def delete_document(self, doc_id: uuid.UUID, current_user: CurrentUser) -> None:
        if not current_user.is_company_admin and not current_user.is_super_admin:
            raise PermissionDeniedError()
        company_id = self._get_company_id(current_user)
        doc = await self.repo.get_by_id_and_company(doc_id, company_id)
        if not doc:
            raise NotFoundError("Document not found")
        await self.repo.delete(doc)
