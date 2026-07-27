"""
Tests for authentication endpoints.

Covers:
- Successful login returning access + refresh tokens
- Login with wrong password → 401
- Login with non-existent user → 401
- GET /me with a valid token
- GET /me with an invalid token → 401
- Token refresh flow
- Logout
"""

import pytest
from httpx import AsyncClient

from app.modules.users.models import User


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, admin_user_a: User):
    """Valid credentials must return both tokens with bearer type."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": admin_user_a.email,
            "password": "Admin123!",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, admin_user_a: User):
    """Wrong password must return 401 with AUTHENTICATION_ERROR code."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": admin_user_a.email,
            "password": "WrongPassword!",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_ERROR"


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    """Login attempt for an unknown e-mail must return 401."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "nobody@example.com",
            "password": "SomePassword123!",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me(
    client: AsyncClient, admin_user_a: User, admin_a_token: str
):
    """GET /me must return the authenticated user's profile."""
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == admin_user_a.email
    assert data["role"] == "company_admin"


@pytest.mark.asyncio
async def test_get_me_invalid_token(client: AsyncClient):
    """GET /me with a garbage token must return 401."""
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient, admin_user_a: User):
    """A valid refresh token must yield a new access token."""
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "email": admin_user_a.email,
            "password": "Admin123!",
        },
    )
    refresh_token = login.json()["refresh_token"]

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_refresh_token_invalid(client: AsyncClient):
    """An invalid refresh token must return 401."""
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "bad.refresh.token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout(client: AsyncClient, admin_a_token: str):
    """Logout must return 200 (tokens are stateless; client discards them)."""
    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_protected_route_without_token(client: AsyncClient):
    """Accessing a protected route without any Authorization header must fail."""
    response = await client.get("/api/v1/auth/me")
    # FastAPI HTTPBearer returns 403 when the header is absent.
    assert response.status_code in (401, 403)
