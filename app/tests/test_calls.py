import uuid
import pytest
from datetime import datetime, timezone
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.calls.models import Call, CallStatus, CallOutcome
from app.modules.agents.models import Agent
from app.modules.requests.models import Request


@pytest.mark.asyncio
async def test_create_call(client: AsyncClient, admin_a_token: str, agent_a: Agent):
    response = await client.post(
        "/api/v1/calls",
        json={
            "agent_id": str(agent_a.id),
            "caller_number": "+96891000099",
        },
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["caller_number"] == "+96891000099"
    assert data["status"] == "initiated"
    assert data["agent_id"] == str(agent_a.id)


@pytest.mark.asyncio
async def test_get_call(client: AsyncClient, call_a: Call, admin_a_token: str):
    response = await client.get(
        f"/api/v1/calls/{call_a.id}",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(call_a.id)
    assert data["caller_number"] == "+96891000001"
    assert data["messages"] == []
    assert data["phone_number"]["id"] == str(call_a.phone_number_id)


@pytest.mark.asyncio
async def test_list_calls(client: AsyncClient, call_a: Call, admin_a_token: str):
    response = await client.get(
        "/api/v1/calls",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_list_calls_filter_by_status(
    client: AsyncClient, call_a: Call, admin_a_token: str
):
    response = await client.get(
        "/api/v1/calls?status=in_progress",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["status"] == "in_progress"


@pytest.mark.asyncio
async def test_update_call(client: AsyncClient, call_a: Call, admin_a_token: str):
    response = await client.patch(
        f"/api/v1/calls/{call_a.id}",
        json={"status": "answered", "answered_at": datetime.now(timezone.utc).isoformat()},
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "answered"


@pytest.mark.asyncio
async def test_add_transcript_message(
    client: AsyncClient, call_a: Call, admin_a_token: str
):
    response = await client.post(
        f"/api/v1/calls/{call_a.id}/messages",
        json={
            "speaker": "caller",
            "text": "I need to rent a car.",
            "sequence": 1,
            "confidence": 0.95,
        },
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["text"] == "I need to rent a car."
    assert data["speaker"] == "caller"
    assert data["sequence"] == 1
    assert data["confidence"] == 0.95


@pytest.mark.asyncio
async def test_add_multiple_transcript_messages(
    client: AsyncClient, call_a: Call, admin_a_token: str
):
    for i, (speaker, text) in enumerate([
        ("assistant", "Welcome! How can I help you?"),
        ("caller", "I want an SUV from the airport."),
        ("assistant", "When do you need it?"),
    ], start=1):
        resp = await client.post(
            f"/api/v1/calls/{call_a.id}/messages",
            json={"speaker": speaker, "text": text, "sequence": i},
            headers={"Authorization": f"Bearer {admin_a_token}"},
        )
        assert resp.status_code == 201

    detail = await client.get(
        f"/api/v1/calls/{call_a.id}",
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert detail.status_code == 200
    assert len(detail.json()["messages"]) >= 3


@pytest.mark.asyncio
async def test_complete_call_booking_creates_request(
    client: AsyncClient,
    call_a: Call,
    admin_a_token: str,
    db_session: AsyncSession,
):
    request_payload = {
        "summary": "Customer requested an SUV from Muscat Airport.",
        "outcome": "booking_created",
        "was_transferred": False,
        "extracted_data": {
            "customer_name": "Ahmed",
            "customer_phone": "+96890000001",
            "request_type": "car_booking",
            "vehicle_type": "SUV",
            "pickup_location": "Muscat Airport",
            "pickup_date": "2026-07-28",
            "return_date": "2026-07-31",
        },
    }
    response = await client.post(
        f"/api/v1/calls/{call_a.id}/complete",
        json=request_payload,
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["call"]["status"] == "completed"
    assert data["call"]["outcome"] == "booking_created"
    assert data["request"] is not None
    assert data["request"]["request_type"] == "car_booking"
    assert data["request"]["customer_name"] == "Ahmed"
    assert data["request"]["status"] == "new"

    repeated_response = await client.post(
        f"/api/v1/calls/{call_a.id}/complete",
        json=request_payload,
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert repeated_response.status_code == 200
    assert repeated_response.json()["request"]["id"] == data["request"]["id"]

    request_count = await db_session.scalar(
        select(func.count()).select_from(Request).where(Request.call_id == call_a.id)
    )
    assert request_count == 1


@pytest.mark.asyncio
async def test_complete_call_callback_creates_request(
    client: AsyncClient, agent_a: Agent, admin_a_token: str, db_session: AsyncSession
):
    call = Call(
        id=uuid.uuid4(),
        company_id=agent_a.company_id,
        agent_id=agent_a.id,
        caller_number="+96899000002",
        status=CallStatus.IN_PROGRESS,
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(call)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/calls/{call.id}/complete",
        json={
            "summary": "Customer requested a callback.",
            "outcome": "callback_requested",
            "was_transferred": False,
            "extracted_data": {
                "customer_name": "Sara",
                "customer_phone": "+96899000002",
                "request_type": "callback",
            },
        },
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["request"] is not None
    assert data["request"]["request_type"] == "callback"


@pytest.mark.asyncio
async def test_complete_call_information_no_request(
    client: AsyncClient, agent_a: Agent, admin_a_token: str, db_session: AsyncSession
):
    call = Call(
        id=uuid.uuid4(),
        company_id=agent_a.company_id,
        agent_id=agent_a.id,
        caller_number="+96899000003",
        status=CallStatus.IN_PROGRESS,
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(call)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/calls/{call.id}/complete",
        json={
            "summary": "Customer asked about pricing.",
            "outcome": "information_request",
            "was_transferred": False,
        },
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["call"]["status"] == "completed"
    assert data["request"] is None


@pytest.mark.asyncio
async def test_complete_call_calculates_duration(
    client: AsyncClient, agent_a: Agent, admin_a_token: str, db_session: AsyncSession
):
    from datetime import timedelta
    started = datetime.now(timezone.utc) - timedelta(seconds=120)
    call = Call(
        id=uuid.uuid4(),
        company_id=agent_a.company_id,
        agent_id=agent_a.id,
        caller_number="+96899000004",
        status=CallStatus.IN_PROGRESS,
        started_at=started,
    )
    db_session.add(call)
    await db_session.flush()

    response = await client.post(
        f"/api/v1/calls/{call.id}/complete",
        json={"outcome": "no_action", "was_transferred": False},
        headers={"Authorization": f"Bearer {admin_a_token}"},
    )
    assert response.status_code == 200
    duration = response.json()["call"]["duration_seconds"]
    assert duration is not None
    assert duration >= 119  # allow 1s tolerance
