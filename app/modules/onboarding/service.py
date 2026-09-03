import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.modules.agents.models import Agent, AgentStatus
from app.modules.agents.schemas import AGENT_TEMPLATES
from app.modules.billing.entitlements import EntitlementService
from app.modules.companies.models import Company
from app.modules.knowledge_base.models import KnowledgeBaseItem, KnowledgeDocument
from app.modules.onboarding.models import (
    TelephonyConnection,
    TelephonyConnectionStatus,
    TelephonyConnectionType,
)
from app.modules.onboarding.schemas import (
    AgentTemplateChoice,
    CompanyOnboardingUpdate,
    OnboardingCompleteResponse,
    OnboardingStatusResponse,
    OnboardingSteps,
    PhoneConnectionChoice,
)
from app.modules.phone_numbers.models import PhoneNumber


class OnboardingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _company_id(self, current_user: CurrentUser) -> uuid.UUID:
        if not current_user.company_id:
            raise PermissionDeniedError("No company context")
        return uuid.UUID(current_user.company_id)

    async def _company(self, current_user: CurrentUser) -> Company:
        company = await self.db.scalar(
            select(Company).where(Company.id == self._company_id(current_user))
        )
        if not company:
            raise NotFoundError("Company not found")
        return company

    async def status(self, current_user: CurrentUser) -> OnboardingStatusResponse:
        company = await self._company(current_user)
        company_id = company.id
        agent_count = await self.db.scalar(
            select(func.count()).select_from(Agent).where(Agent.company_id == company_id)
        )
        active_agent_count = await self.db.scalar(
            select(func.count())
            .select_from(Agent)
            .where(Agent.company_id == company_id, Agent.status == AgentStatus.ACTIVE)
        )
        kb_item_count = await self.db.scalar(
            select(func.count())
            .select_from(KnowledgeBaseItem)
            .where(KnowledgeBaseItem.company_id == company_id)
        )
        kb_document_count = await self.db.scalar(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.company_id == company_id)
        )
        phone_count = await self.db.scalar(
            select(func.count())
            .select_from(PhoneNumber)
            .where(PhoneNumber.company_id == company_id)
        )
        connection_count = await self.db.scalar(
            select(func.count())
            .select_from(TelephonyConnection)
            .where(TelephonyConnection.company_id == company_id)
        )

        steps = OnboardingSteps(
            company_profile=bool(
                company.name
                and company.business_type
                and company.phone_number
                and company.country
            ),
            first_agent=bool(agent_count),
            knowledge_base=bool(kb_item_count or kb_document_count),
            phone_connection=bool(phone_count or connection_count),
            test_agent=bool(active_agent_count),
        )
        current_step = next(
            (name for name, complete in steps.model_dump().items() if not complete),
            None,
        )
        return OnboardingStatusResponse(
            completed=company.onboarding_completed_at is not None,
            current_step=current_step,
            steps=steps,
        )

    async def update_company(
        self,
        data: CompanyOnboardingUpdate,
        current_user: CurrentUser,
    ) -> OnboardingStatusResponse:
        company = await self._company(current_user)
        field_map = {
            "company_name": "name",
            "business_type": "business_type",
            "phone_number": "phone_number",
            "country": "country",
            "default_language": "default_language",
            "timezone": "timezone",
        }
        values = data.model_dump(exclude_unset=True)
        for source, target in field_map.items():
            if source in values and values[source] is not None:
                value = values[source]
                if source == "country":
                    value = value.upper()
                setattr(company, target, value)

        if data.agent_template and data.agent_template != AgentTemplateChoice.BLANK:
            existing_agent = await self.db.scalar(
                select(Agent).where(Agent.company_id == company.id).limit(1)
            )
            if not existing_agent:
                await EntitlementService(self.db).require_resource_capacity(
                    company.id, "agents"
                )
                template = next(
                    item
                    for item in AGENT_TEMPLATES
                    if item.business_type == data.agent_template.value
                )
                agent_data = template.model_dump()
                agent_data.update(company_id=company.id, status=AgentStatus.DRAFT)
                self.db.add(Agent(**agent_data))

        if data.phone_connection and data.phone_connection != PhoneConnectionChoice.SKIP:
            if (
                data.phone_connection == PhoneConnectionChoice.SIP_TRUNK
                and not data.sip_configuration
            ):
                raise ValidationError("SIP configuration is required")
            connection_type = (
                TelephonyConnectionType.SIP_TRUNK
                if data.phone_connection == PhoneConnectionChoice.SIP_TRUNK
                else TelephonyConnectionType.MANAGED_NUMBER
            )
            existing_connection = await self.db.scalar(
                select(TelephonyConnection).where(
                    TelephonyConnection.company_id == company.id,
                    TelephonyConnection.connection_type == connection_type,
                )
            )
            if not existing_connection:
                self.db.add(
                    TelephonyConnection(
                        company_id=company.id,
                        connection_type=connection_type,
                        status=TelephonyConnectionStatus.PENDING,
                        configuration=(
                            data.sip_configuration
                            if connection_type == TelephonyConnectionType.SIP_TRUNK
                            else None
                        ),
                    )
                )

        await self.db.commit()
        return await self.status(current_user)

    async def complete(self, current_user: CurrentUser) -> OnboardingCompleteResponse:
        company = await self._company(current_user)
        if company.onboarding_completed_at is None:
            company.onboarding_completed_at = datetime.now(timezone.utc)
            await self.db.commit()
        return OnboardingCompleteResponse(
            completed=True,
            onboarding_completed_at=company.onboarding_completed_at.isoformat(),
        )
