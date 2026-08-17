import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.models import Company


async def bump_knowledge_version(db: AsyncSession, company_id: uuid.UUID) -> int:
    result = await db.execute(
        update(Company)
        .where(Company.id == company_id)
        .values(knowledge_version=Company.knowledge_version + 1)
        .returning(Company.knowledge_version)
    )
    return int(result.scalar_one())
