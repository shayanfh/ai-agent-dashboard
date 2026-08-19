"""Import every SQLAlchemy model before mapper configuration.

API router imports happen to load most models, but Celery workers do not import routers.
Keeping the registry explicit makes string-based relationships resolve consistently in every
process type.
"""

import app.modules.agents.models  # noqa: F401
import app.modules.auth.models  # noqa: F401
import app.modules.billing.models  # noqa: F401
import app.modules.calls.models  # noqa: F401
import app.modules.companies.models  # noqa: F401
import app.modules.extensions.models  # noqa: F401
import app.modules.integrations.models  # noqa: F401
import app.modules.knowledge_base.models  # noqa: F401
import app.modules.onboarding.models  # noqa: F401
import app.modules.outbound_campaigns.models  # noqa: F401
import app.modules.phone_numbers.models  # noqa: F401
import app.modules.requests.models  # noqa: F401
import app.modules.users.models  # noqa: F401
import app.modules.website_forms.models  # noqa: F401
