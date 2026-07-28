import pytest

from app.modules.agents.models import Agent
from app.modules.calls.models import Call
from app.modules.companies.models import Company
from app.modules.integrations.models import Integration
from app.modules.phone_numbers.models import PhoneNumber


@pytest.mark.parametrize(
    ("model", "relationship_name"),
    [
        (Agent, "phone_numbers"),
        (Agent, "calls"),
        (Agent, "knowledge_items"),
        (Agent, "knowledge_documents"),
        (Call, "messages"),
        (Company, "users"),
        (Company, "agents"),
        (Company, "phone_numbers"),
        (Company, "calls"),
        (Company, "requests"),
        (Company, "integrations"),
        (Integration, "logs"),
        (PhoneNumber, "calls"),
    ],
)
def test_collection_relationships_are_configured_as_lists(model, relationship_name):
    relationship = getattr(model, relationship_name).property

    assert relationship.uselist is True
