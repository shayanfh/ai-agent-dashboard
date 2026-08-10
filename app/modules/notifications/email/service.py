from app.core.config import settings
from app.modules.notifications.email.providers import ConsoleEmailProvider, SMTPEmailProvider
from app.modules.notifications.email import templates


class EmailService:
    def __init__(self):
        self.provider = (
            SMTPEmailProvider()
            if settings.EMAIL_PROVIDER.casefold() == "smtp"
            else ConsoleEmailProvider()
        )

    def send_template(
        self,
        recipient: str,
        template_name: str,
        full_name: str,
        token: str | None = None,
    ) -> None:
        template = getattr(templates, template_name)
        content = template(full_name, token) if token is not None else template(full_name)
        subject, html_body, text_body = content
        self.provider.send(recipient, subject, html_body, text_body)

    def send_message(self, recipient: str, subject: str, text_body: str) -> None:
        """Send an application-generated notification with escaped HTML."""
        from html import escape

        self.provider.send(recipient, subject, f"<pre>{escape(text_body)}</pre>", text_body)
