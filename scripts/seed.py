"""
Seed script for development data.

DEMO CREDENTIALS (development only — never use in production):
  superadmin@example.com      / SuperAdmin123!
  admin@demo-car-rental.com   / Admin123!
  operator@demo-car-rental.com/ Operator123!
  admin@demo-restaurant.com   / Admin123!
  operator@demo-restaurant.com/ Operator123!

Run: python -m scripts.seed
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.modules.companies.models import Company, CompanyStatus
from app.modules.users.models import User
from app.core.permissions import UserRole
from app.modules.agents.models import Agent, AgentStatus
from app.modules.phone_numbers.models import PhoneNumber, ConnectionStatus
from app.modules.calls.models import Call, CallMessage, CallStatus, CallOutcome, Speaker
from app.modules.requests.models import Request, RequestStatus, RequestType
from app.modules.knowledge_base.models import KnowledgeBaseItem, KBItemStatus
from app.modules.integrations.models import Integration, IntegrationType, IntegrationStatus
from app.core.security import encrypt_credential
import random


async def seed():
    print("Seeding database...")
    async with AsyncSessionLocal() as db:

        # ─── Companies ──────────────────────────────────────────────────────────
        company1 = Company(
            id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
            name="Demo Car Rental",
            business_type="car_rental",
            default_language="en",
            timezone="Asia/Muscat",
            phone_number="+96812345678",
            email="info@demo-car-rental.com",
            status=CompanyStatus.ACTIVE,
            business_hours={"weekdays": "08:00-20:00", "weekends": "09:00-17:00"},
        )
        company2 = Company(
            id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            name="Demo Restaurant Group",
            business_type="restaurant",
            default_language="ar",
            timezone="Asia/Muscat",
            phone_number="+96887654321",
            email="info@demo-restaurant.com",
            status=CompanyStatus.ACTIVE,
        )
        db.add_all([company1, company2])
        await db.flush()

        # ─── Super Admin ─────────────────────────────────────────────────────────
        super_admin = User(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            full_name="Super Admin",
            email="superadmin@example.com",
            hashed_password=hash_password("SuperAdmin123!"),
            role=UserRole.SUPER_ADMIN,
            company_id=None,
            is_active=True,
        )

        # ─── Company 1 Users ─────────────────────────────────────────────────────
        admin1 = User(
            id=uuid.UUID("11111111-1111-1111-1111-111111111112"),
            full_name="Car Rental Admin",
            email="admin@demo-car-rental.com",
            hashed_password=hash_password("Admin123!"),
            role=UserRole.COMPANY_ADMIN,
            company_id=company1.id,
            is_active=True,
        )
        operator1 = User(
            id=uuid.UUID("11111111-1111-1111-1111-111111111113"),
            full_name="Car Rental Operator",
            email="operator@demo-car-rental.com",
            hashed_password=hash_password("Operator123!"),
            role=UserRole.OPERATOR,
            company_id=company1.id,
            is_active=True,
        )

        # ─── Company 2 Users ─────────────────────────────────────────────────────
        admin2 = User(
            id=uuid.UUID("22222222-2222-2222-2222-222222222223"),
            full_name="Restaurant Admin",
            email="admin@demo-restaurant.com",
            hashed_password=hash_password("Admin123!"),
            role=UserRole.COMPANY_ADMIN,
            company_id=company2.id,
            is_active=True,
        )
        operator2 = User(
            id=uuid.UUID("22222222-2222-2222-2222-222222222224"),
            full_name="Restaurant Operator",
            email="operator@demo-restaurant.com",
            hashed_password=hash_password("Operator123!"),
            role=UserRole.OPERATOR,
            company_id=company2.id,
            is_active=True,
        )
        db.add_all([super_admin, admin1, operator1, admin2, operator2])
        await db.flush()

        # ─── Agents ──────────────────────────────────────────────────────────────
        agent1 = Agent(
            id=uuid.UUID("11111111-1111-1111-1111-111111111120"),
            company_id=company1.id,
            name="Car Rental Booking Agent",
            business_type="car_rental",
            language="en",
            voice_provider="openai",
            voice_id="alloy",
            stt_provider="openai",
            stt_model="whisper-1",
            llm_provider="openai",
            llm_model="gpt-4.1-mini",
            system_prompt=(
                "You are a professional car rental booking assistant for Demo Car Rental. "
                "Help customers reserve vehicles by collecting: vehicle type, pickup location, "
                "pickup date, return date, and contact information. "
                "Always confirm availability and provide pricing estimates when possible."
            ),
            greeting_message="Welcome to Demo Car Rental! How can I assist you today?",
            transfer_number="1001",
            status=AgentStatus.ACTIVE,
        )
        agent2 = Agent(
            id=uuid.UUID("22222222-2222-2222-2222-222222222220"),
            company_id=company2.id,
            name="Restaurant Reservation Agent",
            business_type="restaurant",
            language="ar",
            voice_provider="openai",
            voice_id="nova",
            stt_provider="openai",
            stt_model="whisper-1",
            llm_provider="openai",
            llm_model="gpt-4.1-mini",
            system_prompt=(
                "You are a friendly restaurant reservation assistant for Demo Restaurant Group. "
                "Help customers make table reservations by asking for: date, time, number of guests, and branch. "
                "Confirm the booking details before finalizing."
            ),
            greeting_message="أهلاً بكم في مجموعة المطاعم! كيف يمكنني مساعدتكم؟",
            transfer_number="2001",
            status=AgentStatus.ACTIVE,
        )
        db.add_all([agent1, agent2])
        await db.flush()

        # ─── Phone Numbers ───────────────────────────────────────────────────────
        phone1 = PhoneNumber(
            id=uuid.UUID("11111111-1111-1111-1111-111111111130"),
            company_id=company1.id,
            agent_id=agent1.id,
            phone_number="+96880001234",
            provider="twilio",
            sip_trunk_id="trunk_demo_001",
            livekit_trunk_id="lk_trunk_demo_001",
            connection_status=ConnectionStatus.CONNECTED,
            is_enabled=True,
        )
        db.add(phone1)
        await db.flush()

        # ─── Calls (20 sample) ───────────────────────────────────────────────────
        call_statuses = [CallStatus.COMPLETED, CallStatus.MISSED, CallStatus.COMPLETED,
                         CallStatus.COMPLETED, CallStatus.TRANSFERRED, CallStatus.FAILED]
        call_outcomes = [CallOutcome.BOOKING_CREATED, None, CallOutcome.BOOKING_CREATED,
                         CallOutcome.INFORMATION_REQUEST, None, None]
        callers = ["+96891000001", "+96891000002", "+96891000003", "+96891000004",
                   "+96891000005", "+96891000006", "+96891000007", "+96891000008",
                   "+96891000009", "+96891000010"]

        calls = []
        for i in range(20):
            days_ago = random.randint(0, 7)
            hours_ago = random.randint(0, 23)
            start = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)
            duration = random.randint(45, 300)
            status = call_statuses[i % len(call_statuses)]
            outcome = call_outcomes[i % len(call_outcomes)] if status == CallStatus.COMPLETED else None

            call = Call(
                company_id=company1.id,
                agent_id=agent1.id,
                phone_number_id=phone1.id,
                caller_number=callers[i % len(callers)],
                status=status,
                outcome=outcome,
                started_at=start,
                answered_at=start + timedelta(seconds=5) if status != CallStatus.MISSED else None,
                ended_at=start + timedelta(seconds=duration) if status in (CallStatus.COMPLETED, CallStatus.TRANSFERRED, CallStatus.FAILED) else None,
                duration_seconds=duration if status in (CallStatus.COMPLETED, CallStatus.TRANSFERRED, CallStatus.FAILED) else None,
                was_transferred=(status == CallStatus.TRANSFERRED),
                summary="Customer requested SUV from Muscat Airport." if outcome == CallOutcome.BOOKING_CREATED else None,
                extracted_data={
                    "customer_name": f"Customer {i + 1}",
                    "customer_phone": callers[i % len(callers)],
                    "request_type": "car_booking",
                    "vehicle_type": "SUV",
                    "pickup_location": "Muscat Airport",
                    "pickup_date": "2026-07-28",
                    "return_date": "2026-07-31",
                } if outcome == CallOutcome.BOOKING_CREATED else None,
            )
            calls.append(call)

        db.add_all(calls)
        await db.flush()

        # ─── Transcript for first call ────────────────────────────────────────────
        if calls:
            first_call = calls[0]
            if first_call.status == CallStatus.COMPLETED:
                messages = [
                    CallMessage(call_id=first_call.id, company_id=company1.id, speaker=Speaker.ASSISTANT,
                                text="Welcome to Demo Car Rental! How can I assist you today?", sequence=1),
                    CallMessage(call_id=first_call.id, company_id=company1.id, speaker=Speaker.CALLER,
                                text="Hi, I need to rent an SUV from Muscat Airport.", sequence=2, confidence=0.95),
                    CallMessage(call_id=first_call.id, company_id=company1.id, speaker=Speaker.ASSISTANT,
                                text="I'd be happy to help! When do you need to pick it up?", sequence=3),
                    CallMessage(call_id=first_call.id, company_id=company1.id, speaker=Speaker.CALLER,
                                text="July 28th, and I'll return it July 31st.", sequence=4, confidence=0.92),
                    CallMessage(call_id=first_call.id, company_id=company1.id, speaker=Speaker.ASSISTANT,
                                text="Perfect! May I have your name and phone number?", sequence=5),
                    CallMessage(call_id=first_call.id, company_id=company1.id, speaker=Speaker.CALLER,
                                text="Ahmed Al-Rashidi, plus 968 9 1 0 0 0 0 0 1.", sequence=6, confidence=0.88),
                    CallMessage(call_id=first_call.id, company_id=company1.id, speaker=Speaker.ASSISTANT,
                                text="Thank you Ahmed! Your SUV booking from Muscat Airport, July 28-31, is confirmed.", sequence=7),
                ]
                db.add_all(messages)

        # ─── Requests (5 samples) ────────────────────────────────────────────────
        completed_calls = [c for c in calls if c.status == CallStatus.COMPLETED and c.outcome == CallOutcome.BOOKING_CREATED]
        for i, call in enumerate(completed_calls[:5]):
            req = Request(
                company_id=company1.id,
                call_id=call.id,
                agent_id=agent1.id,
                customer_name=f"Customer {i + 1}",
                customer_phone=callers[i % len(callers)],
                request_type=RequestType.CAR_BOOKING,
                status=RequestStatus.NEW,
                request_data={
                    "vehicle_type": "SUV",
                    "pickup_location": "Muscat Airport",
                    "pickup_date": "2026-07-28",
                    "return_date": "2026-07-31",
                },
            )
            db.add(req)

        # ─── Knowledge Base (10 items) ────────────────────────────────────────────
        kb_items = [
            ("What vehicles do you offer?", "We offer a wide range: economy cars, SUVs, vans, and luxury vehicles.", "fleet"),
            ("What are your operating hours?", "We operate 8 AM to 8 PM weekdays, 9 AM to 5 PM weekends.", "hours"),
            ("Do you offer airport pickup?", "Yes, we offer pickup from Muscat International Airport at no extra charge.", "locations"),
            ("What is your cancellation policy?", "Free cancellation up to 24 hours before pickup.", "policies"),
            ("Do you require a credit card?", "Yes, a valid credit card is required as a security deposit.", "payment"),
            ("Can I extend my rental?", "Yes, contact us at least 2 hours before your return time.", "rental"),
            ("What is included in the price?", "Basic insurance and unlimited mileage are included in all rentals.", "pricing"),
            ("Do you offer child seats?", "Yes, child seats are available for a small daily fee.", "extras"),
            ("What documents do I need?", "A valid driving license and passport or national ID are required.", "requirements"),
            ("Do you have GPS devices?", "GPS devices are available for rent at a daily fee.", "extras"),
        ]
        for q, a, cat in kb_items:
            item = KnowledgeBaseItem(
                company_id=company1.id,
                agent_id=agent1.id,
                question=q,
                answer=a,
                category=cat,
                status=KBItemStatus.ACTIVE,
            )
            db.add(item)

        # ─── ERPNext Integration ──────────────────────────────────────────────────
        integration = Integration(
            company_id=company1.id,
            integration_type=IntegrationType.ERPNEXT,
            name="ERPNext Main",
            base_url="https://erp.demo-car-rental.com",
            api_key_encrypted=encrypt_credential("demo-api-key-change-in-production"),
            api_secret_encrypted=encrypt_credential("demo-api-secret-change-in-production"),
            configuration={
                "customer_doctype": "Customer",
                "request_doctype": "Booking Request",
                "customer_group": "All Customer Groups",
                "territory": "All Territories",
                "field_mapping": {
                    "customer_name": "customer_name",
                    "customer_phone": "mobile_no",
                    "request_type": "request_type",
                    "vehicle_type": "vehicle_type",
                    "pickup_location": "pickup_location",
                    "pickup_date": "pickup_date",
                    "return_date": "return_date",
                },
            },
            status=IntegrationStatus.CONNECTED,
        )
        db.add(integration)

        await db.commit()
        print("Seed data inserted successfully!")
        print("\nDemo credentials:")
        print("  superadmin@example.com       / SuperAdmin123!")
        print("  admin@demo-car-rental.com    / Admin123!")
        print("  operator@demo-car-rental.com / Operator123!")
        print("  admin@demo-restaurant.com    / Admin123!")
        print("  operator@demo-restaurant.com / Operator123!")


if __name__ == "__main__":
    asyncio.run(seed())
