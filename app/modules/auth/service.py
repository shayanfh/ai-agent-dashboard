import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    EmailNotVerifiedError,
    ValidationError,
)
from app.core.security import (
    verify_password,
    hash_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_secure_token,
    hash_auth_token,
    normalize_email,
    validate_password_strength,
)
from app.core.permissions import UserRole
from app.modules.auth.models import AuthToken, AuthTokenType
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import (
    LoginRequest,
    SignupRequest,
    SignupResponse,
    TokenResponse,
    UserMeResponse,
    VerifyEmailResponse,
)
from app.modules.companies.models import Company, CompanyStatus
from app.modules.users.models import User
from jose import JWTError

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.repo = AuthRepository(db)
        self.db = db

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _queue_email(self, user: User, template_name: str, token: str | None = None) -> None:
        try:
            from app.workers.notification_tasks import send_email

            send_email.apply_async(
                args=[user.email, template_name, user.full_name, token],
                retry=False,
            )
        except Exception as exc:
            logger.warning("Could not queue %s email for %s: %s", template_name, user.id, exc)

    async def _issue_login_tokens(self, user: User) -> TokenResponse:
        access_token = create_access_token(
            user_id=str(user.id),
            company_id=str(user.company_id) if user.company_id else None,
            role=user.role.value,
        )
        refresh_token = create_refresh_token(user_id=str(user.id))
        self.db.add(
            AuthToken(
                user_id=user.id,
                token_type=AuthTokenType.REFRESH_TOKEN,
                token_hash=hash_auth_token(refresh_token),
                expires_at=datetime.now(timezone.utc)
                + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            )
        )
        await self.db.commit()
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    async def signup(self, data: SignupRequest) -> SignupResponse:
        email = normalize_email(str(data.email))
        validate_password_strength(data.password)
        if await self.repo.get_user_by_email(email):
            raise ConflictError("An account with this email already exists")

        verification_token = generate_secure_token()
        try:
            company = Company(
                name=data.company_name.strip(),
                business_type=data.business_type.strip(),
                phone_number=data.phone_number.strip(),
                country=data.country.upper(),
                email=email,
                default_language=data.default_language,
                timezone=data.timezone,
                status=CompanyStatus.PENDING_VERIFICATION,
                signup_source=data.signup_source,
            )
            self.db.add(company)
            await self.db.flush()

            user = User(
                company_id=company.id,
                full_name=data.full_name.strip(),
                email=email,
                hashed_password=hash_password(data.password),
                role=UserRole.COMPANY_ADMIN,
                is_active=True,
                email_verified=False,
                failed_login_attempts=0,
            )
            self.db.add(user)
            await self.db.flush()

            self.db.add(
                AuthToken(
                    user_id=user.id,
                    token_type=AuthTokenType.EMAIL_VERIFICATION,
                    token_hash=hash_auth_token(verification_token),
                    expires_at=datetime.now(timezone.utc)
                    + timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS),
                )
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictError("An account with this email already exists") from exc
        except Exception:
            await self.db.rollback()
            raise

        self._queue_email(user, "verification_email", verification_token)
        return SignupResponse(
            message="Registration successful. Please verify your email.",
            company_id=str(company.id),
            user_id=str(user.id),
            email=user.email,
        )

    async def login(self, data: LoginRequest) -> TokenResponse:
        email = normalize_email(str(data.email))
        user = await self.repo.get_user_by_email(email)
        now = datetime.now(timezone.utc)
        if user and user.locked_until and self._aware(user.locked_until) > now:
            raise AuthenticationError("Account is temporarily locked")
        if not user or not verify_password(data.password, user.hashed_password):
            if user:
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
                    user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
                await self.db.commit()
            raise AuthenticationError("Invalid email or password")
        if not user.is_active:
            raise AuthenticationError("User account is disabled")
        if not user.email_verified:
            raise EmailNotVerifiedError()
        if user.company_id:
            result = await self.db.execute(select(Company).where(Company.id == user.company_id))
            company = result.scalar_one_or_none()
            if company and company.status not in (CompanyStatus.TRIAL, CompanyStatus.ACTIVE):
                raise AuthenticationError("Company account is not active")
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        await self.db.flush()
        logger.info(f"User {user.email} logged in")
        return await self._issue_login_tokens(user)

    async def refresh(self, refresh_token: str) -> TokenResponse:
        try:
            payload = decode_token(refresh_token)
            if payload.get("type") != "refresh":
                raise AuthenticationError("Invalid token type")
            user_id = payload.get("sub")
        except JWTError:
            raise AuthenticationError("Invalid or expired refresh token")
        stored_token = await self.repo.get_token(
            hash_auth_token(refresh_token),
            AuthTokenType.REFRESH_TOKEN,
        )
        now = datetime.now(timezone.utc)
        if (
            not stored_token
            or stored_token.used_at is not None
            or self._aware(stored_token.expires_at) <= now
        ):
            raise AuthenticationError("Invalid or expired refresh token")
        user = await self.repo.get_user_by_id(user_id)
        if not user or not user.is_active or not user.email_verified:
            raise AuthenticationError("User not found or disabled")
        if user.company_id:
            company = await self.db.scalar(
                select(Company).where(Company.id == user.company_id)
            )
            if company and company.status not in (
                CompanyStatus.TRIAL,
                CompanyStatus.ACTIVE,
            ):
                raise AuthenticationError("Company account is not active")
        stored_token.used_at = now
        await self.db.flush()
        return await self._issue_login_tokens(user)

    async def verify_email(self, raw_token: str) -> VerifyEmailResponse:
        token = await self.repo.get_token(
            hash_auth_token(raw_token),
            AuthTokenType.EMAIL_VERIFICATION,
        )
        now = datetime.now(timezone.utc)
        if (
            not token
            or token.used_at is not None
            or self._aware(token.expires_at) <= now
        ):
            raise ValidationError("Invalid or expired verification token")
        user = await self.repo.get_user_by_id(str(token.user_id))
        if not user:
            raise ValidationError("Invalid verification token")
        company = await self.db.scalar(select(Company).where(Company.id == user.company_id))
        if not company:
            raise ValidationError("Company not found")

        token.used_at = now
        user.email_verified = True
        user.email_verified_at = now
        user.is_active = True
        if company.status == CompanyStatus.PENDING_VERIFICATION:
            company.status = CompanyStatus.TRIAL
            company.trial_started_at = now
            company.trial_ends_at = now + timedelta(days=settings.TRIAL_DAYS)
        await self.db.flush()
        tokens = await self._issue_login_tokens(user)
        self._queue_email(user, "welcome_email")
        return VerifyEmailResponse(**tokens.model_dump())

    async def resend_verification(self, email_value: str) -> None:
        email = normalize_email(email_value)
        user = await self.repo.get_user_by_email(email)
        if not user or user.email_verified:
            return
        now = datetime.now(timezone.utc)
        latest = await self.db.scalar(
            select(AuthToken)
            .where(
                AuthToken.user_id == user.id,
                AuthToken.token_type == AuthTokenType.EMAIL_VERIFICATION,
            )
            .order_by(AuthToken.created_at.desc())
            .limit(1)
        )
        if latest and self._aware(latest.created_at) > now - timedelta(seconds=60):
            return
        await self.repo.invalidate_unused_tokens(
            user.id, AuthTokenType.EMAIL_VERIFICATION, now
        )
        raw_token = generate_secure_token()
        self.db.add(
            AuthToken(
                user_id=user.id,
                token_type=AuthTokenType.EMAIL_VERIFICATION,
                token_hash=hash_auth_token(raw_token),
                expires_at=now + timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS),
            )
        )
        await self.db.commit()
        self._queue_email(user, "verification_email", raw_token)

    async def forgot_password(self, email_value: str) -> None:
        user = await self.repo.get_user_by_email(normalize_email(email_value))
        if not user or not user.is_active:
            return
        now = datetime.now(timezone.utc)
        await self.repo.invalidate_unused_tokens(user.id, AuthTokenType.PASSWORD_RESET, now)
        raw_token = generate_secure_token()
        self.db.add(
            AuthToken(
                user_id=user.id,
                token_type=AuthTokenType.PASSWORD_RESET,
                token_hash=hash_auth_token(raw_token),
                expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES),
            )
        )
        await self.db.commit()
        self._queue_email(user, "password_reset_email", raw_token)

    async def reset_password(self, raw_token: str, new_password: str) -> None:
        validate_password_strength(new_password)
        token = await self.repo.get_token(
            hash_auth_token(raw_token),
            AuthTokenType.PASSWORD_RESET,
        )
        now = datetime.now(timezone.utc)
        if (
            not token
            or token.used_at is not None
            or self._aware(token.expires_at) <= now
        ):
            raise ValidationError("Invalid or expired password reset token")
        user = await self.repo.get_user_by_id(str(token.user_id))
        if not user:
            raise ValidationError("Invalid password reset token")
        user.hashed_password = hash_password(new_password)
        user.failed_login_attempts = 0
        user.locked_until = None
        token.used_at = now
        await self.repo.invalidate_unused_tokens(user.id, AuthTokenType.REFRESH_TOKEN, now)
        await self.db.commit()

    async def get_me(self, user_id: str) -> UserMeResponse:
        user = await self.repo.get_user_by_id(user_id)
        if not user:
            raise AuthenticationError("User not found")
        return UserMeResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role.value,
            company_id=str(user.company_id) if user.company_id else None,
            is_active=user.is_active,
            email_verified=user.email_verified,
        )
