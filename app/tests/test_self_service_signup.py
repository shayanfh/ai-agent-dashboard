from datetime import datetime, timedelta, timezone
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_refresh_token,
    hash_auth_token,
    verify_password,
)
from app.core.rate_limit import _memory_limits
from app.modules.agents.models import Agent, AgentStatus
from app.modules.auth.models import AuthToken, AuthTokenType
from app.modules.auth.service import AuthService
from app.modules.companies.models import Company, CompanyStatus
from app.modules.onboarding.models import (
    TelephonyConnection,
    TelephonyConnectionStatus,
)
from app.modules.users.models import User


SIGNUP_PAYLOAD = {
    "full_name": "Ahmed Al Balushi",
    "email": "Ahmed.Signup@example.com",
    "password": "StrongPassword123!",
    "company_name": "Muscat Car Rental",
    "business_type": "car_rental",
    "phone_number": "+96890000000",
    "country": "om",
    "default_language": "en",
    "timezone": "Asia/Muscat",
}


@pytest.fixture
def captured_emails(monkeypatch):
    captured = []

    def capture(self, user, template_name, token=None):
        captured.append(
            {
                "email": user.email,
                "template": template_name,
                "token": token,
            }
        )

    monkeypatch.setattr(AuthService, "_queue_email", capture)
    return captured


@pytest.fixture(autouse=True)
def clear_rate_limits():
    _memory_limits.clear()


async def signup(client: AsyncClient, captured_emails, **overrides):
    suffix = uuid.uuid4().hex[:10]
    payload = {
        **SIGNUP_PAYLOAD,
        "email": f"ahmed.signup.{suffix}@example.com",
        "company_name": f"Muscat Car Rental {suffix}",
        **overrides,
    }
    response = await client.post("/api/v1/auth/signup", json=payload)
    return response


@pytest.mark.asyncio
async def test_successful_signup_is_atomic_and_normalizes_email(
    client: AsyncClient,
    db_session: AsyncSession,
    captured_emails,
):
    response = await signup(client, captured_emails)

    assert response.status_code == 201
    registered_email = response.json()["email"]

    user = await db_session.scalar(
        select(User).where(User.email == registered_email)
    )
    company = await db_session.get(Company, user.company_id)
    token_count = await db_session.scalar(
        select(func.count())
        .select_from(AuthToken)
        .where(
            AuthToken.user_id == user.id,
            AuthToken.token_type == AuthTokenType.EMAIL_VERIFICATION,
        )
    )

    assert user.role.value == "company_admin"
    assert user.email_verified is False
    assert company.status == CompanyStatus.PENDING_VERIFICATION
    assert company.country == "OM"
    assert token_count == 1
    assert captured_emails[-1]["template"] == "verification_email"
    assert captured_emails[-1]["token"]


@pytest.mark.asyncio
async def test_duplicate_email_does_not_create_an_orphan_company(
    client: AsyncClient,
    db_session: AsyncSession,
    captured_emails,
):
    first = await signup(client, captured_emails)
    company_count_before = await db_session.scalar(
        select(func.count()).select_from(Company)
    )

    duplicate = await signup(
        client,
        captured_emails,
        email=first.json()["email"].upper(),
        company_name="Orphan Company",
    )
    company_count_after = await db_session.scalar(
        select(func.count()).select_from(Company)
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert company_count_after == company_count_before


@pytest.mark.asyncio
async def test_weak_password_is_rejected_before_company_creation(
    client: AsyncClient,
    db_session: AsyncSession,
    captured_emails,
):
    company_count_before = await db_session.scalar(
        select(func.count()).select_from(Company)
    )
    response = await signup(client, captured_emails, password="weak")
    company_count_after = await db_session.scalar(
        select(func.count()).select_from(Company)
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert company_count_after == company_count_before


@pytest.mark.asyncio
async def test_unverified_user_cannot_login(
    client: AsyncClient,
    captured_emails,
):
    registration = await signup(client, captured_emails)
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": registration.json()["email"],
            "password": SIGNUP_PAYLOAD["password"],
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"


@pytest.mark.asyncio
async def test_email_verification_starts_trial_and_returns_login_tokens(
    client: AsyncClient,
    db_session: AsyncSession,
    captured_emails,
):
    signup_response = await signup(client, captured_emails)
    verification_token = captured_emails[-1]["token"]

    response = await client.post(
        "/api/v1/auth/verify-email",
        json={"token": verification_token},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["refresh_token"]

    from uuid import UUID

    user = await db_session.get(User, UUID(signup_response.json()["user_id"]))
    company = await db_session.get(Company, UUID(signup_response.json()["company_id"]))
    assert user.email_verified is True
    assert user.email_verified_at is not None
    assert company.status == CompanyStatus.TRIAL
    assert company.trial_started_at is not None
    assert company.trial_ends_at is not None

    reused = await client.post(
        "/api/v1/auth/verify-email",
        json={"token": verification_token},
    )
    assert reused.status_code == 422


@pytest.mark.asyncio
async def test_expired_verification_token_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    captured_emails,
):
    registration = await signup(client, captured_emails)
    raw_token = captured_emails[-1]["token"]
    token = await db_session.scalar(
        select(AuthToken).where(AuthToken.token_hash == hash_auth_token(raw_token))
    )
    token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/verify-email",
        json={"token": raw_token},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_resend_and_forgot_password_use_generic_responses(
    client: AsyncClient,
    captured_emails,
):
    registration = await signup(client, captured_emails)

    unknown_resend = await client.post(
        "/api/v1/auth/resend-verification",
        json={"email": "unknown@example.com"},
    )
    unknown_forgot = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "unknown@example.com"},
    )
    known_forgot = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": registration.json()["email"]},
    )

    assert unknown_resend.status_code == 200
    assert unknown_forgot.status_code == 200
    assert known_forgot.status_code == 200
    assert unknown_forgot.json() == known_forgot.json()
    assert captured_emails[-1]["template"] == "password_reset_email"


@pytest.mark.asyncio
async def test_password_reset_revokes_refresh_tokens(
    client: AsyncClient,
    db_session: AsyncSession,
    captured_emails,
):
    registration = await signup(client, captured_emails)
    user = await db_session.scalar(
        select(User).where(User.email == registration.json()["email"])
    )
    reset_token = "reset-" + ("x" * 48)
    refresh_token = create_refresh_token(str(user.id))
    db_session.add_all(
        [
            AuthToken(
                user_id=user.id,
                token_type=AuthTokenType.PASSWORD_RESET,
                token_hash=hash_auth_token(reset_token),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            ),
            AuthToken(
                user_id=user.id,
                token_type=AuthTokenType.REFRESH_TOKEN,
                token_hash=hash_auth_token(refresh_token),
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            ),
        ]
    )
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/reset-password",
        json={
            "token": reset_token,
            "new_password": "DifferentStrong456!",
        },
    )
    await db_session.refresh(user)
    refresh_record = await db_session.scalar(
        select(AuthToken).where(AuthToken.token_hash == hash_auth_token(refresh_token))
    )

    assert response.status_code == 200
    assert verify_password("DifferentStrong456!", user.hashed_password)
    assert refresh_record.used_at is not None


@pytest.mark.asyncio
async def test_onboarding_creates_draft_agent_and_pending_sip_connection(
    client: AsyncClient,
    db_session: AsyncSession,
    captured_emails,
):
    await signup(client, captured_emails)
    verified = await client.post(
        "/api/v1/auth/verify-email",
        json={"token": captured_emails[-1]["token"]},
    )
    headers = {"Authorization": f"Bearer {verified.json()['access_token']}"}

    initial = await client.get("/api/v1/onboarding/status", headers=headers)
    updated = await client.patch(
        "/api/v1/onboarding/company",
        headers=headers,
        json={
            "agent_template": "car_rental",
            "phone_connection": "sip_trunk",
            "sip_configuration": {
                "host": "sip.example.com",
                "username": "untrusted-input",
            },
        },
    )
    completed = await client.post("/api/v1/onboarding/complete", headers=headers)

    agent = await db_session.scalar(select(Agent).where(Agent.name.like("Car Rental%")))
    connection = await db_session.scalar(select(TelephonyConnection))

    assert initial.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["steps"]["first_agent"] is True
    assert updated.json()["steps"]["phone_connection"] is True
    assert agent.status == AgentStatus.DRAFT
    assert connection.status == TelephonyConnectionStatus.PENDING
    assert completed.status_code == 200
    assert completed.json()["completed"] is True
