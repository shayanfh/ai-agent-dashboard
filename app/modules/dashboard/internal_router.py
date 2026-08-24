import re
import uuid
import wave
from datetime import datetime, timezone
from typing import Any, Optional
from unicodedata import decimal

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
from pydantic import AliasChoices, BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import verify_internal_api_key
from app.core.exceptions import ConflictError, NotFoundError
from app.core.storage import ObjectStorage, get_object_storage
from app.modules.agents.models import Agent
from app.modules.companies.models import Company
from app.modules.calls.models import Call, CallStatus
from app.modules.calls.schemas import (
    CallCompleteRequest,
)
from app.modules.extensions.models import Extension, ExtensionStatus
from app.modules.extensions.service import ExtensionService
from app.modules.phone_numbers.models import ConnectionStatus, PhoneNumber
from app.modules.knowledge_base.models import (
    DocumentProcessingStatus,
    KBItemStatus,
    KnowledgeBaseItem,
    KnowledgeChunk,
    KnowledgeDocument,
)
from app.modules.knowledge_base.schemas import (
    KnowledgeSnapshotEntry,
    KnowledgeSnapshotResponse,
)

router = APIRouter()

ASTERISK_LINKED_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


class ResolveAgentRequest(BaseModel):
    phone_number: str


class ResolvedAgentResponse(BaseModel):
    company_id: str
    agent_id: str
    agent_name: str
    language: str
    greeting_message: Optional[str]
    system_prompt: Optional[str]
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
    knowledge_version: int
    outbound_context: dict[str, Any] | None = None


class InternalCallCreate(BaseModel):
    phone_number: str
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


class TransferTargetRequest(BaseModel):
    target: str = Field(
        min_length=1,
        max_length=100,
        validation_alias=AliasChoices("target", "extension"),
    )

    @field_validator("target")
    @classmethod
    def normalize_target(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Transfer target cannot be empty")
        if normalized.isdecimal():
            return "".join(str(decimal(character)) for character in normalized)
        return normalized


class TransferTargetResponse(BaseModel):
    extension_id: str
    extension: str
    display_name: str
    sip_uri: str


@router.get("/voice/resolve-agent", response_model=ResolvedAgentResponse)
async def resolve_agent(
    phone_number: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_api_key),
):
    query = select(PhoneNumber).where(
        PhoneNumber.phone_number == phone_number,
        PhoneNumber.is_enabled == True,
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
        knowledge_version=(
            await db.scalar(
                select(Company.knowledge_version).where(Company.id == pn.company_id)
            )
        )
        or 1,
    )


@router.get("/voice/resolve-agent-by-id", response_model=ResolvedAgentResponse)
async def resolve_agent_by_id(
    agent_id: uuid.UUID = Query(...),
    company_id: uuid.UUID = Query(...),
    call_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_api_key),
):
    outbound_call = await db.scalar(
        select(Call).where(
            Call.id == call_id,
            Call.company_id == company_id,
            Call.agent_id == agent_id,
        )
    )
    if not outbound_call:
        raise NotFoundError("Outbound call context not found")
    from app.modules.outbound_campaigns.models import OutboundCampaign, OutboundRecipient
    outbound_row = (
        await db.execute(
            select(OutboundCampaign, OutboundRecipient)
            .join(OutboundRecipient, OutboundRecipient.id == outbound_call.recipient_id)
            .where(OutboundCampaign.id == outbound_call.campaign_id)
        )
    ).one_or_none()
    if not outbound_row:
        raise NotFoundError("Outbound campaign context not found")
    campaign, recipient = outbound_row
    agent = await db.scalar(
        select(Agent).where(Agent.id == agent_id, Agent.company_id == company_id)
    )
    if not agent:
        raise NotFoundError("Agent not found")
    return ResolvedAgentResponse(
        company_id=str(company_id), agent_id=str(agent.id), agent_name=agent.name,
        language=agent.language, greeting_message=agent.greeting_message,
        system_prompt=agent.system_prompt,
        use_realtime=agent.use_realtime, realtime_provider=agent.realtime_provider,
        realtime_model=agent.realtime_model, voice_provider=agent.voice_provider,
        voice_id=agent.voice_id, tts_provider=agent.tts_provider,
        tts_model=agent.tts_model, stt_provider=agent.stt_provider,
        stt_model=agent.stt_model, llm_provider=agent.llm_provider,
        llm_model=agent.llm_model,
        knowledge_version=(await db.scalar(select(Company.knowledge_version).where(Company.id == company_id))) or 1,
        outbound_context={
            "campaign_name": campaign.name,
            "objective": campaign.message_text,
            "recipient": {
                "first_name": recipient.first_name,
                "last_name": recipient.last_name,
                "language": recipient.language,
                "external_id": recipient.external_id,
                "custom_fields": recipient.custom_fields or {},
            },
        },
    )


@router.get("/voice/knowledge-snapshot", response_model=KnowledgeSnapshotResponse)
async def knowledge_snapshot(
    agent_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_api_key),
):
    agent = await db.scalar(select(Agent).where(Agent.id == agent_id))
    if not agent:
        raise NotFoundError("Agent not found")
    version = (
        await db.scalar(
            select(Company.knowledge_version).where(Company.id == agent.company_id)
        )
    ) or 1
    scope = or_(
        KnowledgeBaseItem.agent_id.is_(None),
        KnowledgeBaseItem.agent_id == agent.id,
    )
    items = list(
        await db.scalars(
            select(KnowledgeBaseItem)
            .where(
                KnowledgeBaseItem.company_id == agent.company_id,
                KnowledgeBaseItem.status == KBItemStatus.ACTIVE,
                scope,
            )
            .order_by(KnowledgeBaseItem.created_at, KnowledgeBaseItem.id)
        )
    )
    chunks = list(
        await db.execute(
            select(KnowledgeChunk, KnowledgeDocument.file_name)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(
                KnowledgeChunk.company_id == agent.company_id,
                or_(KnowledgeChunk.agent_id.is_(None), KnowledgeChunk.agent_id == agent.id),
                KnowledgeDocument.processing_status == DocumentProcessingStatus.COMPLETED,
            )
            .order_by(KnowledgeDocument.created_at, KnowledgeChunk.chunk_index)
        )
    )
    entries: list[KnowledgeSnapshotEntry] = []
    total_chars = 0
    for item in items:
        content = f"Question: {item.question}\nAnswer: {item.answer}"
        if total_chars + len(content) > settings.KNOWLEDGE_SNAPSHOT_MAX_CHARS:
            break
        entries.append(
            KnowledgeSnapshotEntry(
                id=str(item.id),
                source="qa",
                title=item.question,
                content=content,
                category=item.category,
            )
        )
        total_chars += len(content)
    for chunk, file_name in chunks:
        if total_chars + len(chunk.content) > settings.KNOWLEDGE_SNAPSHOT_MAX_CHARS:
            break
        entries.append(
            KnowledgeSnapshotEntry(
                id=str(chunk.id),
                source="document",
                title=file_name,
                content=chunk.content,
            )
        )
        total_chars += len(chunk.content)
    return KnowledgeSnapshotResponse(
        company_id=str(agent.company_id),
        agent_id=str(agent.id),
        version=version,
        entries=entries,
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


@router.post(
    "/voice/calls/{call_id}/transfer-target",
    response_model=TransferTargetResponse,
)
async def resolve_transfer_target(
    call_id: uuid.UUID,
    data: TransferTargetRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_internal_api_key),
):
    call = await db.get(Call, call_id)
    if not call:
        raise NotFoundError("Call not found")
    active_target = (
        Extension.company_id == call.company_id,
        Extension.is_enabled.is_(True),
        Extension.status == ExtensionStatus.ACTIVE,
    )
    if data.target.isdigit():
        matches = (
            await db.scalars(
                select(Extension).where(
                    *active_target,
                    Extension.extension == data.target,
                )
            )
        ).all()
    else:
        matches = (
            await db.scalars(
                select(Extension).where(
                    *active_target,
                    func.lower(Extension.display_name) == data.target.lower(),
                )
            )
        ).all()
    if not matches:
        raise NotFoundError("Active extension not found")
    if len(matches) > 1:
        raise ConflictError(
            "Multiple active extensions use this display name; use the extension number"
        )
    extension = matches[0]
    return TransferTargetResponse(
        extension_id=str(extension.id),
        extension=extension.extension,
        display_name=extension.display_name,
        sip_uri=ExtensionService.transfer_uri(call.company_id, extension.extension),
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
