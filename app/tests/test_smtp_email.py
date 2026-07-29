from email.message import EmailMessage

from app.core.config import settings
from app.modules.notifications.email.providers.smtp import SMTPEmailProvider
from app.modules.notifications.email.service import EmailService


class FakeSMTP:
    instances = []

    def __init__(self, host: str, port: int, timeout: int):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.tls_started = False
        self.credentials = None
        self.message = None
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def starttls(self):
        self.tls_started = True

    def login(self, username: str, password: str):
        self.credentials = (username, password)

    def send_message(self, message: EmailMessage):
        self.message = message


def test_smtp_sends_templated_email_with_tls_and_auth(monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(
        "app.modules.notifications.email.providers.smtp.smtplib.SMTP", FakeSMTP
    )
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp")
    monkeypatch.setattr(settings, "EMAIL_FROM", "no-reply@mozaic.test")
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.mozaic.test")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "smtp-user")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "smtp-password")
    monkeypatch.setattr(settings, "SMTP_USE_TLS", True)
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://dashboard.mozaic.test")

    EmailService().send_template(
        recipient="customer@example.com",
        template_name="verification_email",
        full_name="Test Customer",
        token="verification-token",
    )

    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port, smtp.timeout) == ("smtp.mozaic.test", 587, 30)
    assert smtp.tls_started is True
    assert smtp.credentials == ("smtp-user", "smtp-password")
    assert smtp.message["From"] == "no-reply@mozaic.test"
    assert smtp.message["To"] == "customer@example.com"
    assert smtp.message["Subject"] == "Verify your email"
    assert "verification-token" in smtp.message.get_body(preferencelist=("plain",)).get_content()
    assert "https://dashboard.mozaic.test/verify-email" in (
        smtp.message.get_body(preferencelist=("html",)).get_content()
    )


def test_smtp_skips_tls_and_login_when_disabled(monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(
        "app.modules.notifications.email.providers.smtp.smtplib.SMTP", FakeSMTP
    )
    monkeypatch.setattr(settings, "SMTP_HOST", "local-mail")
    monkeypatch.setattr(settings, "SMTP_PORT", 1025)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    monkeypatch.setattr(settings, "SMTP_USE_TLS", False)

    SMTPEmailProvider().send(
        recipient="customer@example.com",
        subject="SMTP test",
        html_body="<p>SMTP test</p>",
        text_body="SMTP test",
    )

    smtp = FakeSMTP.instances[0]
    assert smtp.tls_started is False
    assert smtp.credentials is None
    assert smtp.message["Subject"] == "SMTP test"

