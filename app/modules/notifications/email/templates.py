from app.core.config import settings


def verification_email(full_name: str, token: str) -> tuple[str, str, str]:
    url = f"{settings.FRONTEND_URL.rstrip('/')}/verify-email?token={token}"
    subject = "Verify your email"
    text = f"Hello {full_name}, verify your email: {url}"
    html = f"<p>Hello {full_name},</p><p><a href=\"{url}\">Verify your email</a></p>"
    return subject, html, text


def password_reset_email(full_name: str, token: str) -> tuple[str, str, str]:
    url = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"
    subject = "Reset your password"
    text = f"Hello {full_name}, reset your password: {url}"
    html = f"<p>Hello {full_name},</p><p><a href=\"{url}\">Reset your password</a></p>"
    return subject, html, text


def welcome_email(full_name: str) -> tuple[str, str, str]:
    subject = "Welcome to Mozaic"
    text = f"Welcome {full_name}! Your email has been verified."
    html = f"<p>Welcome {full_name}!</p><p>Your email has been verified.</p>"
    return subject, html, text


def company_activated_email(full_name: str) -> tuple[str, str, str]:
    subject = "Your company is active"
    text = f"Hello {full_name}, your company account is now active."
    html = f"<p>Hello {full_name},</p><p>Your company account is now active.</p>"
    return subject, html, text
