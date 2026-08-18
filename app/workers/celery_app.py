from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "ai_agent_dashboard",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.knowledge_tasks",
        "app.workers.integration_tasks",
        "app.workers.notification_tasks",
        "app.workers.outbound_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_ignore_result=True,
    task_publish_retry=False,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.integration_tasks.*": {"queue": "integrations"},
        "app.workers.call_tasks.*": {"queue": "calls"},
        "app.workers.notification_tasks.*": {"queue": "notifications"},
        "app.workers.knowledge_tasks.*": {"queue": "knowledge"},
        "app.workers.outbound_tasks.*": {"queue": "calls"},
    },
    beat_schedule={
        "dispatch-due-outbound-campaigns": {
            "task": "app.workers.outbound_tasks.dispatch_due_campaigns",
            "schedule": settings.OUTBOUND_DISPATCH_INTERVAL_SECONDS,
        }
    },
)
