from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class AgentTemplateChoice(str, Enum):
    RESTAURANT = "restaurant"
    CAR_RENTAL = "car_rental"
    CUSTOMER_SUPPORT = "customer_support"
    BLANK = "blank"


class PhoneConnectionChoice(str, Enum):
    MANAGED_NUMBER = "managed_number"
    SIP_TRUNK = "sip_trunk"
    SKIP = "skip"


class OnboardingSteps(BaseModel):
    company_profile: bool
    first_agent: bool
    knowledge_base: bool
    phone_connection: bool
    test_agent: bool


class OnboardingStatusResponse(BaseModel):
    completed: bool
    current_step: Optional[str]
    steps: OnboardingSteps


class CompanyOnboardingUpdate(BaseModel):
    company_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    business_type: Optional[str] = Field(default=None, min_length=2, max_length=100)
    phone_number: Optional[str] = Field(default=None, min_length=5, max_length=50)
    country: Optional[str] = Field(default=None, min_length=2, max_length=2)
    default_language: Optional[str] = Field(default=None, min_length=2, max_length=10)
    timezone: Optional[str] = Field(default=None, min_length=1, max_length=100)
    website_url: Optional[HttpUrl] = None
    description: Optional[str] = Field(default=None, max_length=4000)
    agent_template: Optional[AgentTemplateChoice] = None
    phone_connection: Optional[PhoneConnectionChoice] = None
    sip_configuration: Optional[dict] = None


class OnboardingCompleteResponse(BaseModel):
    completed: bool
    onboarding_completed_at: str


class WebsiteAnalysisRequest(BaseModel):
    website_url: HttpUrl


class CompanySuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    website_url: str = Field(max_length=2048)
    company_name: str | None = Field(max_length=255)
    business_type: str | None = Field(max_length=100)
    description: str | None = Field(max_length=4000)
    phone_number: str | None = Field(max_length=50)
    country: str | None = Field(min_length=2, max_length=2)
    default_language: str | None = Field(min_length=2, max_length=10)
    timezone: str | None = Field(max_length=100)


class AgentSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    business_type: str | None = Field(max_length=100)
    language: str = Field(min_length=2, max_length=10)
    use_realtime: bool
    greeting_message: str = Field(min_length=1, max_length=1000)
    system_prompt: str = Field(min_length=1, max_length=6000)


class WebsiteAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_suggestion: CompanySuggestion
    agent_suggestion: AgentSuggestion
