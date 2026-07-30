import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select
from app.core.database import get_db
from app.core.dependencies import verify_internal_api_key
from app.core.exceptions import NotFoundError
from app.modules.phone_numbers.models import PhoneNumber
from app.modules.agents.models import Agent
from app.modules.calls.models import Call, CallStatus
from app.modules.calls.schemas import CallCreate, CallUpdate, CallMessageCreate, CallCompleteRequest
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

router = APIRouter()


class ResolveAgentRequest(BaseModel):
    phone_number: str
    extension: Optional[str] = None


class ResolvedAgentResponse(BaseModel):
    company_id: str
    agent_id: str
    agent_name: str
    language: str
    greeting_message: Optional[str]
    system_prompt: Optional[str]
    transfer_number: Optional[str]
    use_realtime: bool
    # Realtime: one WebSocket session handles everything
    realtime_provider: Optional[str]
    realtime_model: Optional[str]
    # Pipeline: separate per stage
    voice_provider: Optional[str]
    voice_id: Optional[str]
    tts_provider: Optional[str]
    tts_model: Optional[str]
    stt_provider: Optional[str]
    stt_model: Optional[str]
    llm_provider: Optional[str]
    llm_model: Optional[str]


class InternalCallCreate(BaseModel):
    phone_number: str
    extension: Optional[str] = None
    caller_number: Optional[str] = None
    livekit_room_name: Optional[str] = None


class InternalCallResponse(BaseModel):
    call_id: str
    company_id: str
    agent_id: Optional[str]
    status: str


class InternalMessageCreate(BaseModel):
    speaker: str
    text: str
    sequence: int
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    confidence: Optional[float] = None


@router.get("/voice/resolve-agent", response_model=ResolvedAgentResponse)
async def resolve_agent(
    phone_number: str = Query(...),
    extension: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_api_key),
):
    query = select(PhoneNumber).where(
        PhoneNumber.phone_number == phone_number,
        PhoneNumber.is_enabled == True,
    )
    if extension:
        query = query.where(PhoneNumber.extension == extension)
    else:
        query = query.where(
            or_(PhoneNumber.extension.is_(None), PhoneNumber.extension == "")
        )
    result = await db.execute(query)
    pn = result.scalar_one_or_none()
    if not pn:
        raise NotFoundError(f"No active phone number found: {phone_number}")
    if not pn.agent_id:
        raise NotFoundError("Phone number has no agent assigned")
    agent_result = await db.execute(select(Agent).where(Agent.id == pn.agent_id))
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise NotFoundError("Agent not found")
    return ResolvedAgentResponse(
        company_id=str(pn.company_id),
        agent_id=str(agent.id),
        agent_name=agent.name,
        language=agent.language,
        greeting_message=agent.greeting_message,
        system_prompt=agent.system_prompt,
        transfer_number=agent.transfer_number,
        use_realtime=agent.use_realtime,
        realtime_provider=agent.realtime_provider,
        realtime_model=agent.realtime_model,
        voice_provider=agent.voice_provider,
        voice_id=agent.voice_id,
        tts_provider=agent.tts_provider,
        tts_model=agent.tts_model,
        stt_provider=agent.stt_provider,
        stt_model=agent.stt_model,
        llm_provider=agent.llm_provider,
        llm_model=agent.llm_model,
    )


@router.post("/voice/calls", response_model=InternalCallResponse, status_code=201)
async def create_internal_call(
    data: InternalCallCreate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_api_key),
):
    query = select(PhoneNumber).where(
        PhoneNumber.phone_number == data.phone_number,
        PhoneNumber.is_enabled == True,
    )
    if data.extension:
        query = query.where(PhoneNumber.extension == data.extension)
    else:
        query = query.where(
            or_(PhoneNumber.extension.is_(None), PhoneNumber.extension == "")
        )
    result = await db.execute(query)
    pn = result.scalar_one_or_none()
    if not pn:
        raise NotFoundError("Phone number not found")
    call = Call(
        company_id=pn.company_id,
        agent_id=pn.agent_id,
        phone_number_id=pn.id,
        caller_number=data.caller_number,
        livekit_room_name=data.livekit_room_name,
        status=CallStatus.RINGING,
        started_at=datetime.now(timezone.utc),
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)
    return InternalCallResponse(
        call_id=str(call.id),
        company_id=str(call.company_id),
        agent_id=str(call.agent_id) if call.agent_id else None,
        status=call.status.value,
    )


@router.post("/voice/calls/{call_id}/messages", status_code=201)
async def add_internal_message(
    call_id: uuid.UUID,
    data: InternalMessageCreate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_api_key),
):
    from app.modules.calls.models import CallMessage, Speaker
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise NotFoundError("Call not found")
    try:
        speaker = Speaker(data.speaker)
    except ValueError:
        speaker = Speaker.SYSTEM
    msg = CallMessage(
        call_id=call_id,
        company_id=call.company_id,
        speaker=speaker,
        text=data.text,
        sequence=data.sequence,
        started_at=data.started_at,
        ended_at=data.ended_at,
        confidence=data.confidence,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return {"id": str(msg.id), "sequence": msg.sequence}


@router.post("/voice/calls/{call_id}/complete")
async def complete_internal_call(
    call_id: uuid.UUID,
    data: CallCompleteRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_api_key),
):
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise NotFoundError("Call not found")
    from app.core.dependencies import CurrentUser
    from app.modules.calls.service import CallService
    # Create a synthetic CurrentUser for the service
    current_user = CurrentUser(
        user_id="internal",
        company_id=str(call.company_id),
        role="company_admin",
    )
    service = CallService(db)
    return await service.complete_call(call_id, data, current_user)
