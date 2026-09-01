import json
import uuid
from datetime import datetime, timedelta, timezone

from livekit import api
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import CurrentUser
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.modules.agents.models import Agent
from app.modules.billing.models import Subscription
from app.modules.calls.models import Call, CallDirection, CallSource, CallStatus


class WebTestCallSessionResponse(BaseModel):
    call_id: uuid.UUID
    agent_id: uuid.UUID
    room_name: str
    participant_identity: str
    livekit_url: str
    access_token: str
    max_duration_seconds: int
    expires_at: datetime


class WebTestCallUsageResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    duration_seconds: int
    minutes_used: float
    max_duration_seconds_per_call: int


class WebTestCallService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _company_id(current_user: CurrentUser) -> uuid.UUID:
        if not current_user.company_id:
            raise PermissionDeniedError("No company context")
        return uuid.UUID(current_user.company_id)

    @staticmethod
    def _validate_livekit_settings() -> None:
        if not all(
            (
                settings.LIVEKIT_URL,
                settings.LIVEKIT_API_KEY,
                settings.LIVEKIT_API_SECRET,
                settings.LIVEKIT_AGENT_NAME,
            )
        ):
            raise ValidationError("LiveKit browser test calls are not configured")

    @staticmethod
    def _build_access_token(
        *, room_name: str, participant_identity: str, dispatch_metadata: str
    ) -> str:
        return (
            api.AccessToken(
                api_key=settings.LIVEKIT_API_KEY,
                api_secret=settings.LIVEKIT_API_SECRET,
            )
            .with_identity(participant_identity)
            .with_name("Dashboard test caller")
            .with_metadata(dispatch_metadata)
            .with_ttl(timedelta(seconds=settings.WEB_TEST_CALL_TOKEN_TTL_SECONDS))
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_publish_sources=["microphone"],
                    can_subscribe=True,
                    can_publish_data=False,
                )
            )
            .with_room_config(
                api.RoomConfiguration(
                    agents=[
                        api.RoomAgentDispatch(
                            agent_name=settings.LIVEKIT_AGENT_NAME,
                            metadata=dispatch_metadata,
                        )
                    ]
                )
            )
            .to_jwt()
        )

    @staticmethod
    def _period_fallback(now: datetime) -> tuple[datetime, datetime]:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end

    async def _period(self, company_id: uuid.UUID) -> tuple[datetime, datetime]:
        subscription = await self.db.scalar(
            select(Subscription).where(Subscription.company_id == company_id)
        )
        if subscription:
            return subscription.current_period_start, subscription.current_period_end
        return self._period_fallback(datetime.now(timezone.utc))

    async def get_usage(self, current_user: CurrentUser) -> WebTestCallUsageResponse:
        company_id = self._company_id(current_user)
        period_start, period_end = await self._period(company_id)
        duration_seconds = int(
            (
                await self.db.scalar(
                    select(func.coalesce(func.sum(Call.duration_seconds), 0)).where(
                        Call.company_id == company_id,
                        Call.source == CallSource.WEB_TEST,
                        Call.started_at >= period_start,
                        Call.started_at < period_end,
                    )
                )
            )
            or 0
        )
        return WebTestCallUsageResponse(
            period_start=period_start,
            period_end=period_end,
            duration_seconds=duration_seconds,
            minutes_used=round(duration_seconds / 60, 2),
            max_duration_seconds_per_call=settings.WEB_TEST_CALL_MAX_DURATION_SECONDS,
        )

    async def create_session(
        self, agent_id: uuid.UUID, current_user: CurrentUser
    ) -> WebTestCallSessionResponse:
        self._validate_livekit_settings()
        company_id = self._company_id(current_user)
        agent = await self.db.scalar(
            select(Agent).where(Agent.id == agent_id, Agent.company_id == company_id)
        )
        if not agent:
            raise NotFoundError("Agent not found")

        now = datetime.now(timezone.utc)
        call_id = uuid.uuid4()
        room_name = f"web-test-{company_id.hex}-{call_id.hex}"
        participant_identity = f"web-test-user-{uuid.uuid4().hex}"
        dispatch_metadata = json.dumps(
            {
                "call_type": CallSource.WEB_TEST.value,
                "call_id": str(call_id),
                "company_id": str(company_id),
                "agent_id": str(agent.id),
                "participant_identity": participant_identity,
                "max_duration_seconds": settings.WEB_TEST_CALL_MAX_DURATION_SECONDS,
            }
        )
        token = self._build_access_token(
            room_name=room_name,
            participant_identity=participant_identity,
            dispatch_metadata=dispatch_metadata,
        )
        call = Call(
            id=call_id,
            company_id=company_id,
            agent_id=agent.id,
            direction=CallDirection.INBOUND,
            source=CallSource.WEB_TEST,
            caller_number="browser",
            destination_number=str(agent.id),
            livekit_room_name=room_name,
            status=CallStatus.INITIATED,
            started_at=now,
            metadata_={
                "call_type": CallSource.WEB_TEST.value,
                "participant_identity": participant_identity,
                "created_by_user_id": current_user.user_id,
                "max_duration_seconds": settings.WEB_TEST_CALL_MAX_DURATION_SECONDS,
            },
        )
        self.db.add(call)
        await self.db.commit()

        return WebTestCallSessionResponse(
            call_id=call_id,
            agent_id=agent.id,
            room_name=room_name,
            participant_identity=participant_identity,
            livekit_url=settings.LIVEKIT_URL,
            access_token=token,
            max_duration_seconds=settings.WEB_TEST_CALL_MAX_DURATION_SECONDS,
            expires_at=now + timedelta(seconds=settings.WEB_TEST_CALL_TOKEN_TTL_SECONDS),
        )
