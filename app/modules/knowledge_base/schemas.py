import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.modules.knowledge_base.models import KBItemStatus, DocumentProcessingStatus


class KBItemCreate(BaseModel):
    question: str
    answer: str
    category: Optional[str] = None
    agent_id: Optional[uuid.UUID] = None
    status: KBItemStatus = KBItemStatus.ACTIVE


class KBItemUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None
    agent_id: Optional[uuid.UUID] = None
    status: Optional[KBItemStatus] = None


class KBItemResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    agent_id: Optional[uuid.UUID]
    question: str
    answer: str
    category: Optional[str]
    status: KBItemStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KBDocumentCreate(BaseModel):
    file_name: str
    file_type: Optional[str] = None
    file_url: Optional[str] = None
    agent_id: Optional[uuid.UUID] = None


class KBDocumentResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    agent_id: Optional[uuid.UUID]
    file_name: str
    file_type: Optional[str]
    file_url: Optional[str]
    content_type: Optional[str]
    size_bytes: Optional[int]
    processing_status: DocumentProcessingStatus
    error_message: Optional[str]
    processed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KBTemplateItem(BaseModel):
    question: str
    answer: str
    category: str


class KBTemplateResponse(BaseModel):
    business_type: str
    name: str
    description: str
    items: list[KBTemplateItem]


class KBTemplateApply(BaseModel):
    agent_id: Optional[uuid.UUID] = None


class KBTemplateApplyResponse(BaseModel):
    business_type: str
    created: int
    skipped: int
    knowledge_version: int


class KnowledgeSnapshotEntry(BaseModel):
    id: str
    source: str
    title: str
    content: str
    category: Optional[str] = None


class KnowledgeSnapshotResponse(BaseModel):
    company_id: str
    agent_id: str
    version: int = Field(ge=1)
    entries: list[KnowledgeSnapshotEntry]
