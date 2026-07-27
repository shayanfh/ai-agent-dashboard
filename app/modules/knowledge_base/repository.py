import uuid
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.modules.knowledge_base.models import KnowledgeBaseItem, KnowledgeDocument, KBItemStatus


class KBItemRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_company(
        self,
        company_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        agent_id: Optional[uuid.UUID] = None,
        status: Optional[KBItemStatus] = None,
        category: Optional[str] = None,
    ) -> tuple[List[KnowledgeBaseItem], int]:
        offset = (page - 1) * page_size
        query = select(KnowledgeBaseItem).where(KnowledgeBaseItem.company_id == company_id)
        if agent_id:
            query = query.where(KnowledgeBaseItem.agent_id == agent_id)
        if status:
            query = query.where(KnowledgeBaseItem.status == status)
        if category:
            query = query.where(KnowledgeBaseItem.category == category)
        count_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar_one()
        result = await self.db.execute(
            query.order_by(KnowledgeBaseItem.created_at.desc()).offset(offset).limit(page_size)
        )
        return result.scalars().all(), total

    async def get_by_id_and_company(self, item_id: uuid.UUID, company_id: uuid.UUID) -> Optional[KnowledgeBaseItem]:
        result = await self.db.execute(
            select(KnowledgeBaseItem).where(
                KnowledgeBaseItem.id == item_id,
                KnowledgeBaseItem.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> KnowledgeBaseItem:
        item = KnowledgeBaseItem(**data)
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def update(self, item: KnowledgeBaseItem, data: dict) -> KnowledgeBaseItem:
        for k, v in data.items():
            setattr(item, k, v)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def delete(self, item: KnowledgeBaseItem) -> None:
        await self.db.delete(item)
        await self.db.commit()


class KBDocumentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_company(
        self, company_id: uuid.UUID, page: int = 1, page_size: int = 20
    ) -> tuple[List[KnowledgeDocument], int]:
        offset = (page - 1) * page_size
        query = select(KnowledgeDocument).where(KnowledgeDocument.company_id == company_id)
        count_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar_one()
        result = await self.db.execute(
            query.order_by(KnowledgeDocument.created_at.desc()).offset(offset).limit(page_size)
        )
        return result.scalars().all(), total

    async def get_by_id_and_company(self, doc_id: uuid.UUID, company_id: uuid.UUID) -> Optional[KnowledgeDocument]:
        result = await self.db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id == doc_id,
                KnowledgeDocument.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> KnowledgeDocument:
        doc = KnowledgeDocument(**data)
        self.db.add(doc)
        await self.db.commit()
        await self.db.refresh(doc)
        return doc

    async def delete(self, doc: KnowledgeDocument) -> None:
        await self.db.delete(doc)
        await self.db.commit()
