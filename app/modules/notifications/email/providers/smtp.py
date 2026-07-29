import smtplib
from email.message import EmailMessage

from app.core.config import settings
from app.modules.notifications.email.base import EmailProvider


class SMTPEmailProvider(EmailProvider):
    def send(self, recipient: str, subject: str, html_body: str, text_body: str) -> None:
        message = EmailMessage()
        message["From"] = settings.EMAIL_FROM
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls()
            if settings.SMTP_USERNAME:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)
