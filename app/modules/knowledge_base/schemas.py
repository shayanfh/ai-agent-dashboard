import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
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
    processing_status: DocumentProcessingStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
