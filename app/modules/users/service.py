import uuid
import math
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import NotFoundError, PermissionDeniedError, ConflictError
from app.core.dependencies import CurrentUser
from app.core.security import hash_password
from app.core.permissions import UserRole
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserCreate, UserUpdate, UserResponse
from app.core.schemas import PaginatedResponse


class UserService:
    def __init__(self, db: AsyncSession):
        self.repo = UserRepository(db)

    def _check_company_access(self, current_user: CurrentUser, company_id: uuid.UUID):
        if not current_user.is_super_admin:
            if str(current_user.company_id) != str(company_id):
                raise PermissionDeniedError()

    async def list_users(
        self, current_user: CurrentUser, page: int = 1, page_size: int = 20
    ) -> PaginatedResponse[UserResponse]:
        if current_user.is_super_admin:
            raise PermissionDeniedError("Use company-scoped user list")
        company_id = uuid.UUID(current_user.company_id)
        users, total = await self.repo.get_by_company(company_id, page, page_size)
        return PaginatedResponse(
            items=[UserResponse.model_validate(u) for u in users],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def get_user(self, user_id: uuid.UUID, current_user: CurrentUser) -> UserResponse:
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")
        if not current_user.is_super_admin:
            if str(user.company_id) != str(current_user.company_id):
                raise PermissionDeniedError()
        return UserResponse.model_validate(user)

    async def create_user(self, data: UserCreate, current_user: CurrentUser) -> UserResponse:
        if not current_user.is_super_admin and not current_user.is_company_admin:
            raise PermissionDeniedError()
        company_id = data.company_id or (uuid.UUID(current_user.company_id) if current_user.company_id else None)
        if not current_user.is_super_admin:
            if str(company_id) != str(current_user.company_id):
                raise PermissionDeniedError()
            if data.role == UserRole.SUPER_ADMIN:
                raise PermissionDeniedError("Cannot create super admin")
        existing = await self.repo.get_by_email(data.email)
        if existing:
            raise ConflictError("Email already registered")
        user_data = {
            "full_name": data.full_name,
            "email": data.email,
            "hashed_password": hash_password(data.password),
            "role": data.role,
            "company_id": company_id,
        }
        user = await self.repo.create(user_data)
        return UserResponse.model_validate(user)

    async def update_user(
        self, user_id: uuid.UUID, data: UserUpdate, current_user: CurrentUser
    ) -> UserResponse:
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")
        if not current_user.is_super_admin:
            if str(user.company_id) != str(current_user.company_id):
                raise PermissionDeniedError()
        update_data = data.model_dump(exclude_none=True)
        if "password" in update_data:
            update_data["hashed_password"] = hash_password(update_data.pop("password"))
        user = await self.repo.update(user, update_data)
        return UserResponse.model_validate(user)

    async def delete_user(self, user_id: uuid.UUID, current_user: CurrentUser) -> None:
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")
        if not current_user.is_super_admin:
            if str(user.company_id) != str(current_user.company_id):
                raise PermissionDeniedError()
            if not current_user.is_company_admin:
                raise PermissionDeniedError()
        await self.repo.delete(user)
