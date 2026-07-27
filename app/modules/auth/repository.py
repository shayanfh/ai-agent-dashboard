from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timezone
from app.modules.users.models import User


class AuthRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        from uuid import UUID
        result = await self.db.execute(select(User).where(User.id == UUID(user_id)))
        return result.scalar_one_or_none()

    async def update_last_login(self, user_id: str) -> None:
        from uuid import UUID
        await self.db.execute(
            update(User)
            .where(User.id == UUID(user_id))
            .values(last_login_at=datetime.now(timezone.utc))
        )
        await self.db.commit()
