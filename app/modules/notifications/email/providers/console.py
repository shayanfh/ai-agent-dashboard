import logging

from app.modules.notifications.email.base import EmailProvider

logger = logging.getLogger(__name__)


class ConsoleEmailProvider(EmailProvider):
    def send(self, recipient: str, subject: str, html_body: str, text_body: str) -> None:
        logger.info("Email to=%s subject=%s body=%s", recipient, subject, text_body)
