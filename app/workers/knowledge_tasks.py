import asyncio
import ipaddress
import socket
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.storage import get_object_storage
from app.modules.knowledge_base.models import (
    DocumentProcessingStatus,
    KnowledgeChunk,
    KnowledgeDocument,
)
from app.modules.knowledge_base.processor import chunk_text, extract_text
from app.modules.knowledge_base.versioning import bump_knowledge_version
from app.workers.celery_app import celery_app


async def _validate_public_https_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("External documents require a public HTTPS URL")
    addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, 443)
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("External document URL resolves to a private address")


async def _download_document(document: KnowledgeDocument) -> bytes:
    if document.storage_key:
        return await get_object_storage().download(key=document.storage_key)
    if not document.file_url:
        raise ValueError("Document has no uploaded file or external URL")
    await _validate_public_https_url(document.file_url)
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        response = await client.get(document.file_url)
        response.raise_for_status()
        if len(response.content) > settings.MAX_KNOWLEDGE_UPLOAD_BYTES:
            raise ValueError("Document exceeds the configured upload limit")
        return response.content


async def _mark_failed(document_id: uuid.UUID, message: str) -> None:
    async with AsyncSessionLocal() as db:
        document = await db.get(KnowledgeDocument, document_id)
        if document:
            document.processing_status = DocumentProcessingStatus.FAILED
            document.error_message = message[:1000]
            await db.commit()


async def _process(document_id: uuid.UUID) -> dict[str, object]:
    async with AsyncSessionLocal() as db:
        document = await db.scalar(
            select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
        )
        if not document:
            return {"status": "not_found", "document_id": str(document_id)}
        document.processing_status = DocumentProcessingStatus.PROCESSING
        document.error_message = None
        await db.commit()

        content = await _download_document(document)
        if len(content) > settings.MAX_KNOWLEDGE_UPLOAD_BYTES:
            raise ValueError("Document exceeds the configured upload limit")
        text = extract_text(content, document.file_type or "")
        chunks = chunk_text(
            text,
            size=settings.KNOWLEDGE_CHUNK_SIZE_CHARS,
            overlap=settings.KNOWLEDGE_CHUNK_OVERLAP_CHARS,
        )
        await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))
        db.add_all(
            [
                KnowledgeChunk(
                    document_id=document.id,
                    company_id=document.company_id,
                    agent_id=document.agent_id,
                    chunk_index=index,
                    content=chunk,
                    character_count=len(chunk),
                )
                for index, chunk in enumerate(chunks)
            ]
        )
        document.processing_status = DocumentProcessingStatus.COMPLETED
        document.error_message = None
        document.processed_at = datetime.now(timezone.utc)
        version = await bump_knowledge_version(db, document.company_id)
        await db.commit()
        return {
            "status": "completed",
            "document_id": str(document.id),
            "chunks": len(chunks),
            "knowledge_version": version,
        }


@celery_app.task(
    name="app.workers.knowledge_tasks.process_document",
    bind=True,
    max_retries=3,
)
def process_knowledge_document(self, document_id: str) -> dict[str, object]:
    parsed_id = uuid.UUID(document_id)
    try:
        return asyncio.run(_process(parsed_id))
    except Exception as exc:
        asyncio.run(_mark_failed(parsed_id, str(exc)))
        raise self.retry(exc=exc, countdown=min(60 * (self.request.retries + 1), 300))
