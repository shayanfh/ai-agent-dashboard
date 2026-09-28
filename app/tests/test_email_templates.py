from app.core.config import settings
from app.modules.notifications.email import templates


def test_verification_email_has_professional_content_and_safe_html(monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://dashboard.mozaic.test/")
    monkeypatch.setattr(settings, "EMAIL_VERIFICATION_EXPIRE_HOURS", 24)

    subject, html, text = templates.verification_email(
        "Alex <Admin>", "token&source=email"
    )

    assert subject == "Verify your email to get started with Mozaic"
    assert "Verify email address" in html
    assert "Alex &lt;Admin&gt;" in html
    assert "Alex <Admin>" not in html
    assert "token&amp;source=email" in html
    assert "expire in 24 hours" in html
    assert "https://dashboard.mozaic.test/verify-email?token=token&source=email" in text


def test_password_reset_email_explains_security_and_expiration(monkeypatch):
    monkeypatch.setattr(settings, "PASSWORD_RESET_EXPIRE_MINUTES", 30)

    subject, html, text = templates.password_reset_email("Sam", "reset-token")

    assert subject == "Reset your Mozaic password"
    assert "Reset password" in html
    assert "expire in 30 minutes" in text
    assert "password will remain unchanged" in text


def test_welcome_and_activation_emails_link_to_dashboard(monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://dashboard.mozaic.test/")

    welcome_subject, welcome_html, welcome_text = templates.welcome_email("Taylor")
    active_subject, active_html, active_text = templates.company_activated_email("Taylor")

    assert welcome_subject == "Welcome to Mozaic — your account is ready"
    assert "Open your dashboard" in welcome_html
    assert "https://dashboard.mozaic.test" in welcome_text
    assert active_subject == "Your Mozaic workspace is now active"
    assert "Go to dashboard" in active_html
    assert "https://dashboard.mozaic.test" in active_text
