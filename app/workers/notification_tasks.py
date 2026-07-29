from app.modules.notifications.email.service import EmailService
from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.notification_tasks.send_email", bind=True, max_retries=3)
def send_email(
    self,
    recipient: str,
    template_name: str,
    full_name: str,
    token: str | None = None,
) -> dict:
    try:
        EmailService().send_template(recipient, template_name, full_name, token)
        return {"status": "sent", "recipient": recipient, "template": template_name}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
