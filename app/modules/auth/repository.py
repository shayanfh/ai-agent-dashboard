from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timezone
from app.modules.users.models import User
from app.modules.auth.models import AuthToken, AuthTokenType


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

    async def get_token(self, token_hash: str, token_type: AuthTokenType) -> Optional[AuthToken]:
        result = await self.db.execute(
            select(AuthToken).where(
                AuthToken.token_hash == token_hash,
                AuthToken.token_type == token_type,
            )
        )
        return result.scalar_one_or_none()

    async def invalidate_unused_tokens(
        self,
        user_id,
        token_type: AuthTokenType,
        used_at: datetime,
    ) -> None:
        await self.db.execute(
            update(AuthToken)
            .where(
                AuthToken.user_id == user_id,
                AuthToken.token_type == token_type,
                AuthToken.used_at.is_(None),
            )
            .values(used_at=used_at)
        )
