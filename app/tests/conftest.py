"""
Shared pytest fixtures for the AI Agent Dashboard test suite.

Design decisions
----------------
* SQLite (aiosqlite) is used as the in-memory test database so that no
  running PostgreSQL instance is required in CI.
* PostgreSQL-specific column types (``UUID(as_uuid=True)``, ``JSONB``) are
  replaced with SQLite-compatible equivalents **before** ``Base.metadata``
  creates the schema.  This is done by iterating over every column in every
  mapped table and swapping the type object in-place.
* Each test function gets its own ``AsyncSession``.  The session is rolled
  back after each test so tests are fully isolated from each other.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator

# ---------------------------------------------------------------------------
# Import all models so that their tables are registered on Base.metadata
# before we patch the column types.
# ---------------------------------------------------------------------------
from app.core.database import Base, get_db  # noqa: E402 – must come after models
from app.core.permissions import UserRole
from app.core.security import create_access_token, hash_password
from app.main import app as fastapi_app  # noqa: E402
from app.modules.agents.models import Agent, AgentStatus
from app.modules.calls.models import Call, CallOutcome, CallStatus
from app.modules.companies.models import Company, CompanyStatus
from app.modules.phone_numbers.models import ConnectionStatus, PhoneNumber
from app.modules.users.models import User

# Ensure all remaining model tables are registered on Base.metadata
import app.modules.integrations.models  # noqa: F401
import app.modules.requests.models  # noqa: F401
import app.modules.knowledge_base.models  # noqa: F401
import app.modules.auth.models  # noqa: F401
import app.modules.onboarding.models  # noqa: F401


# ---------------------------------------------------------------------------
# SQLite-compatible UUID type
# ---------------------------------------------------------------------------

class _SQLiteUUID(TypeDecorator):
    """Store ``uuid.UUID`` values as 36-char VARCHAR in SQLite."""

    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return uuid.UUID(str(value))
        except (ValueError, AttributeError):
            return value


# ---------------------------------------------------------------------------
# Patch Base.metadata column types for SQLite before the engine is created
# ---------------------------------------------------------------------------

def _patch_metadata_for_sqlite() -> None:
    """Replace PG-specific column types with SQLite-friendly equivalents."""
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, PG_UUID):
                column.type = _SQLiteUUID()
            elif isinstance(column.type, JSONB):
                column.type = JSON()


_patch_metadata_for_sqlite()


# ---------------------------------------------------------------------------
# Test engine & session factory
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session")
def event_loop():
    """Provide a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    """Create all tables once per session; drop them on teardown."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ---------------------------------------------------------------------------
# Per-test fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a fresh database session that is rolled back after every test."""
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Provide an ``AsyncClient`` wired to the FastAPI app with the test DB
    session injected via ``get_db`` dependency override.
    """

    async def override_get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    ) as ac:
        yield ac
    fastapi_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Company fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def company_a(db_session: AsyncSession) -> Company:
    company = Company(
        id=uuid.uuid4(),
        name="Company A",
        status=CompanyStatus.ACTIVE,
        default_language="en",
        timezone="UTC",
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def company_b(db_session: AsyncSession) -> Company:
    company = Company(
        id=uuid.uuid4(),
        name="Company B",
        status=CompanyStatus.ACTIVE,
        default_language="en",
        timezone="UTC",
    )
    db_session.add(company)
    await db_session.flush()
    return company


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def super_admin_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Super Admin",
        email=f"superadmin_{uuid.uuid4().hex[:8]}@test.com",
        hashed_password=hash_password("SuperAdmin123!"),
        role=UserRole.SUPER_ADMIN,
        company_id=None,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def admin_user_a(db_session: AsyncSession, company_a: Company) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Admin A",
        email=f"admin_a_{uuid.uuid4().hex[:8]}@test.com",
        hashed_password=hash_password("Admin123!"),
        role=UserRole.COMPANY_ADMIN,
        company_id=company_a.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def operator_user_a(db_session: AsyncSession, company_a: Company) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Operator A",
        email=f"operator_a_{uuid.uuid4().hex[:8]}@test.com",
        hashed_password=hash_password("Operator123!"),
        role=UserRole.OPERATOR,
        company_id=company_a.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def admin_user_b(db_session: AsyncSession, company_b: Company) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Admin B",
        email=f"admin_b_{uuid.uuid4().hex[:8]}@test.com",
        hashed_password=hash_password("Admin123!"),
        role=UserRole.COMPANY_ADMIN,
        company_id=company_b.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


# ---------------------------------------------------------------------------
# Token helper fixtures
# ---------------------------------------------------------------------------

def make_token(user: User) -> str:
    return create_access_token(
        user_id=str(user.id),
        company_id=str(user.company_id) if user.company_id else None,
        role=user.role.value,
    )


@pytest.fixture
def super_admin_token(super_admin_user: User) -> str:
    return make_token(super_admin_user)


@pytest.fixture
def admin_a_token(admin_user_a: User) -> str:
    return make_token(admin_user_a)


@pytest.fixture
def operator_a_token(operator_user_a: User) -> str:
    return make_token(operator_user_a)


@pytest.fixture
def admin_b_token(admin_user_b: User) -> str:
    return make_token(admin_user_b)


# ---------------------------------------------------------------------------
# Agent fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def agent_a(db_session: AsyncSession, company_a: Company) -> Agent:
    agent = Agent(
        id=uuid.uuid4(),
        company_id=company_a.id,
        name="Test Agent A",
        language="en",
        status=AgentStatus.ACTIVE,
        llm_provider="openai",
        llm_model="gpt-4.1-mini",
        greeting_message="Hello!",
        system_prompt="You are a helpful assistant.",
    )
    db_session.add(agent)
    await db_session.flush()
    return agent


# ---------------------------------------------------------------------------
# Phone number fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def phone_a(
    db_session: AsyncSession,
    company_a: Company,
    agent_a: Agent,
) -> PhoneNumber:
    pn = PhoneNumber(
        id=uuid.uuid4(),
        company_id=company_a.id,
        agent_id=agent_a.id,
        phone_number="+96880001111",
        connection_status=ConnectionStatus.CONNECTED,
        is_enabled=True,
    )
    db_session.add(pn)
    await db_session.flush()
    return pn


# ---------------------------------------------------------------------------
# Call fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def call_a(
    db_session: AsyncSession,
    company_a: Company,
    agent_a: Agent,
    phone_a: PhoneNumber,
) -> Call:
    from datetime import datetime, timezone

    call = Call(
        id=uuid.uuid4(),
        company_id=company_a.id,
        agent_id=agent_a.id,
        phone_number_id=phone_a.id,
        caller_number="+96891000001",
        status=CallStatus.IN_PROGRESS,
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(call)
    await db_session.flush()
    return call
