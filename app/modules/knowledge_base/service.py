import uuid
import math
import re
from io import BytesIO
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.exceptions import IntegrationError, NotFoundError, PermissionDeniedError, ValidationError
from app.core.dependencies import CurrentUser
from app.core.storage import ObjectStorage
from app.modules.agents.models import Agent
from app.modules.companies.models import Company
from app.modules.knowledge_base.models import (
    DocumentProcessingStatus,
    KBItemStatus,
    KnowledgeBaseItem,
    KnowledgeDocument,
)
from app.modules.knowledge_base.repository import KBItemRepository, KBDocumentRepository
from app.modules.knowledge_base.schemas import (
    KBItemCreate, KBItemUpdate, KBItemResponse,
    KBDocumentCreate, KBDocumentResponse, KBTemplateApplyResponse,
)
from app.core.schemas import PaginatedResponse
from app.modules.knowledge_base.templates import get_knowledge_template
from app.modules.knowledge_base.versioning import bump_knowledge_version


ALLOWED_DOCUMENT_TYPES = {"pdf", "txt", "docx", "md", "csv"}


def _queue_document(document: KnowledgeDocument) -> None:
    try:
        from app.workers.knowledge_tasks import process_knowledge_document

        process_knowledge_document.delay(str(document.id))
    except Exception as exc:
        raise IntegrationError("Knowledge document processing could not be queued") from exc


class KBItemService:
    def __init__(self, db: AsyncSession):
        self.repo = KBItemRepository(db)
        self.db = db

    def _get_company_id(self, current_user: CurrentUser) -> uuid.UUID:
        if not current_user.company_id:
            raise PermissionDeniedError("No company context")
        return uuid.UUID(current_user.company_id)

    async def _validate_agent(self, agent_id: uuid.UUID, company_id: uuid.UUID) -> None:
        agent = await self.db.scalar(
            select(Agent).where(
                Agent.id == agent_id,
                Agent.company_id == company_id,
            )
        )
        if not agent:
            raise NotFoundError("Agent not found")

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
        if data.agent_id:
            await self._validate_agent(data.agent_id, company_id)
        item_data = data.model_dump()
        item_data["company_id"] = company_id
        item = await self.repo.create(item_data)
        await bump_knowledge_version(self.db, company_id)
        await self.db.commit()
        return KBItemResponse.model_validate(item)

    async def update_item(self, item_id: uuid.UUID, data: KBItemUpdate, current_user: CurrentUser) -> KBItemResponse:
        if not current_user.is_company_admin and not current_user.is_super_admin:
            raise PermissionDeniedError()
        company_id = self._get_company_id(current_user)
        item = await self.repo.get_by_id_and_company(item_id, company_id)
        if not item:
            raise NotFoundError("Knowledge base item not found")
        updates = data.model_dump(exclude_unset=True)
        if updates.get("agent_id"):
            await self._validate_agent(updates["agent_id"], company_id)
        item = await self.repo.update(item, updates)
        await bump_knowledge_version(self.db, company_id)
        await self.db.commit()
        return KBItemResponse.model_validate(item)

    async def delete_item(self, item_id: uuid.UUID, current_user: CurrentUser) -> None:
        if not current_user.is_company_admin and not current_user.is_super_admin:
            raise PermissionDeniedError()
        company_id = self._get_company_id(current_user)
        item = await self.repo.get_by_id_and_company(item_id, company_id)
        if not item:
            raise NotFoundError("Knowledge base item not found")
        await self.repo.delete(item)
        await bump_knowledge_version(self.db, company_id)
        await self.db.commit()

    async def apply_template(
        self,
        business_type: str,
        agent_id: Optional[uuid.UUID],
        current_user: CurrentUser,
    ) -> KBTemplateApplyResponse:
        company_id = self._get_company_id(current_user)
        if agent_id:
            await self._validate_agent(agent_id, company_id)
        template = get_knowledge_template(business_type)
        if not template:
            raise NotFoundError("Knowledge base template not found")
        scope_filter = (
            KnowledgeBaseItem.agent_id == agent_id
            if agent_id
            else KnowledgeBaseItem.agent_id.is_(None)
        )
        existing = set(
            await self.db.scalars(
                select(KnowledgeBaseItem.question).where(
                    KnowledgeBaseItem.company_id == company_id,
                    scope_filter,
                )
            )
        )
        created = 0
        for template_item in template.items:
            if template_item.question in existing:
                continue
            self.db.add(
                KnowledgeBaseItem(
                    company_id=company_id,
                    agent_id=agent_id,
                    question=template_item.question,
                    answer=template_item.answer,
                    category=template_item.category,
                    status=KBItemStatus.ACTIVE,
                )
            )
            created += 1
        company = await self.db.get(Company, company_id)
        version = company.knowledge_version if company else 1
        if created:
            version = await bump_knowledge_version(self.db, company_id)
            await self.db.commit()
        return KBTemplateApplyResponse(
            business_type=template.business_type,
            created=created,
            skipped=len(template.items) - created,
            knowledge_version=version,
        )


class KBDocumentService:
    def __init__(self, db: AsyncSession, storage: ObjectStorage | None = None):
        self.repo = KBDocumentRepository(db)
        self.db = db
        self.storage = storage

    def _get_company_id(self, current_user: CurrentUser) -> uuid.UUID:
        if not current_user.company_id:
            raise PermissionDeniedError("No company context")
        return uuid.UUID(current_user.company_id)

    async def _validate_agent(self, agent_id: uuid.UUID, company_id: uuid.UUID) -> None:
        agent = await self.db.scalar(
            select(Agent).where(
                Agent.id == agent_id,
                Agent.company_id == company_id,
            )
        )
        if not agent:
            raise NotFoundError("Agent not found")

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
        if data.agent_id:
            await self._validate_agent(data.agent_id, company_id)
        file_type = (data.file_type or "").lower().lstrip(".")
        if file_type not in ALLOWED_DOCUMENT_TYPES:
            raise ValidationError(
                f"File type not supported. Allowed: {', '.join(sorted(ALLOWED_DOCUMENT_TYPES))}"
            )
        if not data.file_url:
            raise ValidationError("file_url is required; use /documents/upload for direct uploads")
        doc_data = data.model_dump()
        doc_data["file_type"] = file_type
        doc_data["company_id"] = company_id
        doc_data["processing_status"] = DocumentProcessingStatus.PENDING
        doc = await self.repo.create(doc_data)
        try:
            _queue_document(doc)
        except IntegrationError:
            doc.processing_status = DocumentProcessingStatus.FAILED
            doc.error_message = "Processing queue is unavailable"
            await self.db.commit()
            raise
        return KBDocumentResponse.model_validate(doc)

    async def create_uploaded_document(
        self,
        *,
        file_name: str,
        content_type: str | None,
        content: bytes,
        agent_id: Optional[uuid.UUID],
        current_user: CurrentUser,
    ) -> KBDocumentResponse:
        if not self.storage:
            raise RuntimeError("Object storage is required for document uploads")
        company_id = self._get_company_id(current_user)
        if agent_id:
            await self._validate_agent(agent_id, company_id)
        if not content or len(content) > settings.MAX_KNOWLEDGE_UPLOAD_BYTES:
            raise ValidationError("Document is empty or exceeds the configured upload limit")
        file_type = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        if file_type not in ALLOWED_DOCUMENT_TYPES:
            raise ValidationError(
                f"File type not supported. Allowed: {', '.join(sorted(ALLOWED_DOCUMENT_TYPES))}"
            )
        document_id = uuid.uuid4()
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", file_name).strip("._") or f"document.{file_type}"
        storage_key = f"knowledge/{company_id}/{document_id}/{safe_name}"
        file_url = await self.storage.upload(
            BytesIO(content),
            key=storage_key,
            content_type=content_type or "application/octet-stream",
        )
        document = KnowledgeDocument(
            id=document_id,
            company_id=company_id,
            agent_id=agent_id,
            file_name=file_name,
            file_type=file_type,
            file_url=file_url,
            storage_key=storage_key,
            content_type=content_type,
            size_bytes=len(content),
            processing_status=DocumentProcessingStatus.PENDING,
        )
        self.db.add(document)
        try:
            await self.db.commit()
            await self.db.refresh(document)
        except Exception:
            await self.db.rollback()
            await self.storage.delete(key=storage_key)
            raise
        try:
            _queue_document(document)
        except IntegrationError:
            document.processing_status = DocumentProcessingStatus.FAILED
            document.error_message = "Processing queue is unavailable; retry when it is restored"
            await self.db.commit()
            raise
        return KBDocumentResponse.model_validate(document)

    async def get_document(
        self, doc_id: uuid.UUID, current_user: CurrentUser
    ) -> KBDocumentResponse:
        company_id = self._get_company_id(current_user)
        document = await self.repo.get_by_id_and_company(doc_id, company_id)
        if not document:
            raise NotFoundError("Document not found")
        return KBDocumentResponse.model_validate(document)

    async def retry_document(
        self, doc_id: uuid.UUID, current_user: CurrentUser
    ) -> KBDocumentResponse:
        company_id = self._get_company_id(current_user)
        document = await self.repo.get_by_id_and_company(doc_id, company_id)
        if not document:
            raise NotFoundError("Document not found")
        document.processing_status = DocumentProcessingStatus.PENDING
        document.error_message = None
        await self.db.commit()
        _queue_document(document)
        return KBDocumentResponse.model_validate(document)

    async def delete_document(self, doc_id: uuid.UUID, current_user: CurrentUser) -> None:
        if not current_user.is_company_admin and not current_user.is_super_admin:
            raise PermissionDeniedError()
        company_id = self._get_company_id(current_user)
        doc = await self.repo.get_by_id_and_company(doc_id, company_id)
        if not doc:
            raise NotFoundError("Document not found")
        storage_key = doc.storage_key
        await self.repo.delete(doc)
        await bump_knowledge_version(self.db, company_id)
        await self.db.commit()
        if storage_key and self.storage:
            await self.storage.delete(key=storage_key)
