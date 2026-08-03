import re
import uuid
import wave
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import verify_internal_api_key
from app.core.exceptions import NotFoundError
from app.core.storage import ObjectStorage, get_object_storage
from app.modules.agents.models import Agent
from app.modules.calls.models import Call, CallStatus
from app.modules.calls.schemas import (
    CallCompleteRequest,
)
from app.modules.phone_numbers.models import ConnectionStatus, PhoneNumber

router = APIRouter()

ASTERISK_LINKED_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


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
    metadata: dict[str, Any] = Field(default_factory=dict)


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


class InternalRecordingUpdate(BaseModel):
    egress_id: str = Field(min_length=1, max_length=255)
    recording_url: str = Field(min_length=1, max_length=4000)
    object_key: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    source: str = Field(default="livekit_egress", pattern="^(livekit_egress|external)$")
    recording_duration_seconds: Optional[int] = Field(default=None, ge=0)


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
        metadata_=data.metadata,
    )
    db.add(call)
    if pn.connection_id:
        from app.modules.onboarding.models import (
            TelephonyConnection,
            TelephonyConnectionStatus,
        )

        connection = await db.get(TelephonyConnection, pn.connection_id)
        if connection and connection.status != TelephonyConnectionStatus.ACTIVE:
            connection.status = TelephonyConnectionStatus.ACTIVE
            connection.connected_at = datetime.now(timezone.utc)
            connection.last_error = None
            pn.connection_status = ConnectionStatus.CONNECTED
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


@router.patch("/voice/calls/{call_id}/recording")
async def update_internal_call_recording(
    call_id: uuid.UUID,
    data: InternalRecordingUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_api_key),
):
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if not call:
        raise NotFoundError("Call not found")

    if data.object_key:
        expected_prefix = f"recordings/livekit/{call.company_id}/{call.id}"
        if not data.object_key.startswith(expected_prefix):
            raise HTTPException(status_code=400, detail="Invalid recording object key")
    recording_metadata = {
        "egress_id": data.egress_id,
        "status": "complete",
        "source": data.source,
    }
    if data.object_key:
        recording_metadata["object_key"] = data.object_key
    call.recording_url = data.recording_url
    call.recording_duration_seconds = data.recording_duration_seconds
    call.metadata_ = {
        **(call.metadata_ or {}),
        "recording": recording_metadata,
    }
    await db.commit()
    return {
        "call_id": str(call.id),
        "recording_url": call.recording_url,
        "recording_duration_seconds": call.recording_duration_seconds,
        "egress_id": data.egress_id,
    }


@router.post("/voice/recordings/asterisk", status_code=201)
async def upload_asterisk_recording(
    linked_id: str = Form(...),
    recording: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_api_key),
    storage: ObjectStorage = Depends(get_object_storage),
):
    if not ASTERISK_LINKED_ID_PATTERN.fullmatch(linked_id):
        raise HTTPException(status_code=400, detail="Invalid Asterisk linked ID")

    result = await db.execute(
        select(Call)
        .where(Call.metadata_["asterisk_linked_id"].as_string() == linked_id)
        .order_by(Call.created_at.desc())
        .limit(1)
    )
    call = result.scalars().first()
    if not call:
        raise NotFoundError("No call found for the Asterisk linked ID")

    recording.file.seek(0, 2)
    size = recording.file.tell()
    recording.file.seek(0)
    if size <= 0 or size > settings.MAX_RECORDING_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Recording file size is invalid")

    header = recording.file.read(12)
    recording.file.seek(0)
    if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
        raise HTTPException(status_code=415, detail="Only valid WAV recordings are accepted")

    duration_seconds: Optional[int] = None
    try:
        with wave.open(recording.file, "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            if frame_rate:
                duration_seconds = round(wav_file.getnframes() / frame_rate)
    except (wave.Error, EOFError):
        raise HTTPException(status_code=415, detail="Invalid WAV recording")
    finally:
        recording.file.seek(0)

    object_key = f"recordings/asterisk/{call.company_id}/{call.id}.wav"
    try:
        recording_url = await storage.upload(
            recording.file,
            key=object_key,
            content_type="audio/wav",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Recording storage is unavailable",
        ) from exc

    call.recording_url = recording_url
    call.recording_duration_seconds = duration_seconds
    call.metadata_ = {
        **(call.metadata_ or {}),
        "recording": {
            "source": "asterisk_mixmonitor",
            "linked_id": linked_id,
            "object_key": object_key,
            "status": "complete",
        },
    }
    await db.commit()
    return {
        "call_id": str(call.id),
        "recording_url": recording_url,
        "recording_duration_seconds": duration_seconds,
    }
