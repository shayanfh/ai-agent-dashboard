import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user, CurrentUser, require_company_admin
from app.modules.agents.models import AgentStatus
from app.modules.agents.schemas import AgentCreate, AgentUpdate, AgentResponse, AgentTemplate, AGENT_TEMPLATES
from app.modules.agents.service import AgentService
from app.core.schemas import PaginatedResponse

router = APIRouter()


@router.get("/templates", response_model=list[AgentTemplate])
async def get_templates():
    return AGENT_TEMPLATES


@router.get("", response_model=PaginatedResponse[AgentResponse])
async def list_agents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[AgentStatus] = None,
    business_type: Optional[str] = None,
    language: Optional[str] = None,
    search: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentService(db)
    return await service.list_agents(current_user, page, page_size, status, business_type, language, search)


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    data: AgentCreate,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = AgentService(db)
    return await service.create_agent(data, current_user)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentService(db)
    return await service.get_agent(agent_id, current_user)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    data: AgentUpdate,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = AgentService(db)
    return await service.update_agent(agent_id, data, current_user)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: uuid.UUID,
    current_user: CurrentUser = Depends(require_company_admin),
    db: AsyncSession = Depends(get_db),
):
    service = AgentService(db)
    await service.delete_agent(agent_id, current_user)
