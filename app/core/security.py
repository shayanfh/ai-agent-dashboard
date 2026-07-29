import uuid
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt
from jose import JWTError, jwt
from cryptography.fernet import Fernet
from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def create_access_token(
    user_id: str,
    company_id: Optional[str],
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": user_id,
        "company_id": company_id,
        "role": role,
        "exp": expire,
        "type": "access",
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "exp": expire,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])


def encrypt_credential(value: str) -> str:
    f = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
    return f.encrypt(value.encode()).decode()


def decrypt_credential(encrypted_value: str) -> str:
    f = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
    return f.decrypt(encrypted_value.encode()).decode()


def generate_secure_token() -> str:
    return secrets.token_urlsafe(48)


def hash_auth_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def validate_password_strength(password: str) -> None:
    from app.core.exceptions import ValidationError

    failures = []
    if len(password) < 12:
        failures.append("at least 12 characters")
    if not re.search(r"[A-Z]", password):
        failures.append("an uppercase letter")
    if not re.search(r"[a-z]", password):
        failures.append("a lowercase letter")
    if not re.search(r"\d", password):
        failures.append("a number")
    if not re.search(r"[^A-Za-z0-9]", password):
        failures.append("a special character")
    if failures:
        raise ValidationError(
            "Password is too weak",
            {"requirements": failures},
        )
