import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.modules.agents.models import AgentStatus


class AgentCreate(BaseModel):
    name: str
    business_type: Optional[str] = None
    language: str = "en"
    voice_provider: Optional[str] = None
    voice_id: Optional[str] = None
    stt_provider: Optional[str] = None
    stt_model: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    system_prompt: Optional[str] = None
    greeting_message: Optional[str] = None
    transfer_number: Optional[str] = None
    status: AgentStatus = AgentStatus.DRAFT


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    business_type: Optional[str] = None
    language: Optional[str] = None
    voice_provider: Optional[str] = None
    voice_id: Optional[str] = None
    stt_provider: Optional[str] = None
    stt_model: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    system_prompt: Optional[str] = None
    greeting_message: Optional[str] = None
    transfer_number: Optional[str] = None
    status: Optional[AgentStatus] = None


class AgentResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    business_type: Optional[str]
    language: str
    voice_provider: Optional[str]
    voice_id: Optional[str]
    stt_provider: Optional[str]
    stt_model: Optional[str]
    llm_provider: Optional[str]
    llm_model: Optional[str]
    system_prompt: Optional[str]
    greeting_message: Optional[str]
    transfer_number: Optional[str]
    status: AgentStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentTemplate(BaseModel):
    business_type: str
    name: str
    language: str
    voice_provider: str
    voice_id: str
    stt_provider: str
    stt_model: str
    llm_provider: str
    llm_model: str
    system_prompt: str
    greeting_message: str


AGENT_TEMPLATES: list[AgentTemplate] = [
    AgentTemplate(
        business_type="restaurant",
        name="Restaurant Reservation Agent",
        language="en",
        voice_provider="openai",
        voice_id="alloy",
        stt_provider="openai",
        stt_model="whisper-1",
        llm_provider="openai",
        llm_model="gpt-4.1-mini",
        system_prompt=(
            "You are a friendly restaurant reservation assistant. Help customers make table reservations. "
            "Ask for: date, time, number of guests, and branch preference. "
            "Confirm the booking details before finalizing."
        ),
        greeting_message="Welcome! I'm your restaurant assistant. How can I help you today?",
    ),
    AgentTemplate(
        business_type="car_rental",
        name="Car Rental Booking Agent",
        language="en",
        voice_provider="openai",
        voice_id="alloy",
        stt_provider="openai",
        stt_model="whisper-1",
        llm_provider="openai",
        llm_model="gpt-4.1-mini",
        system_prompt=(
            "You are a professional car rental booking assistant. Help customers reserve vehicles. "
            "Collect: vehicle type, pickup location, pickup date, return date, and customer contact. "
            "Always confirm availability and provide pricing estimates."
        ),
        greeting_message="Welcome to our car rental service! How can I assist you today?",
    ),
    AgentTemplate(
        business_type="customer_support",
        name="Customer Support Agent",
        language="en",
        voice_provider="openai",
        voice_id="nova",
        stt_provider="openai",
        stt_model="whisper-1",
        llm_provider="openai",
        llm_model="gpt-4.1-mini",
        system_prompt=(
            "You are a helpful customer support agent. Assist customers with inquiries, complaints, and service requests. "
            "Be empathetic and professional. Escalate complex issues to human agents when needed."
        ),
        greeting_message="Thank you for calling customer support. How can I help you today?",
    ),
]
