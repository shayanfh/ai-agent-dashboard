from html import escape

from app.core.config import settings


BRAND_NAME = "StarVox"


def _email_layout(
    *,
    preview: str,
    heading: str,
    content: str,
    action_label: str | None = None,
    action_url: str | None = None,
    note: str | None = None,
) -> str:
    """Render a simple, email-client-friendly branded layout."""
    button = ""
    fallback = ""
    if action_label and action_url:
        safe_url = escape(action_url, quote=True)
        button = f"""
          <table role="presentation" border="0" cellpadding="0" cellspacing="0" style="margin: 28px 0;">
            <tr>
              <td style="border-radius: 8px; background-color: #6d5dfc;">
                <a href="{safe_url}" style="display: inline-block; padding: 14px 24px; color: #ffffff; font-size: 15px; font-weight: 700; line-height: 20px; text-decoration: none; border-radius: 8px;">{escape(action_label)}</a>
              </td>
            </tr>
          </table>"""
        fallback = f"""
          <p style="margin: 24px 0 8px; color: #667085; font-size: 13px; line-height: 20px;">If the button does not work, copy and paste this link into your browser:</p>
          <p style="margin: 0; overflow-wrap: anywhere; font-size: 13px; line-height: 20px;"><a href="{safe_url}" style="color: #5947e8; text-decoration: underline;">{safe_url}</a></p>"""

    note_block = ""
    if note:
        note_block = f"""
          <div style="margin-top: 28px; padding: 16px; color: #475467; background-color: #f8f7ff; border-left: 3px solid #6d5dfc; border-radius: 4px; font-size: 13px; line-height: 20px;">{note}</div>"""

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escape(heading)}</title>
  </head>
  <body style="margin: 0; padding: 0; background-color: #f4f4f7; color: #1d2939; font-family: Arial, Helvetica, sans-serif;">
    <div style="display: none; max-height: 0; overflow: hidden; opacity: 0;">{escape(preview)}</div>
    <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="background-color: #f4f4f7;">
      <tr>
        <td align="center" style="padding: 40px 16px;">
          <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="max-width: 600px;">
            <tr>
              <td style="padding: 0 0 20px; color: #322b73; font-size: 24px; font-weight: 800; letter-spacing: -0.5px;">{BRAND_NAME}</td>
            </tr>
            <tr>
              <td style="padding: 40px; background-color: #ffffff; border: 1px solid #e4e7ec; border-radius: 12px; box-shadow: 0 2px 8px rgba(16, 24, 40, 0.04);">
                <h1 style="margin: 0 0 20px; color: #101828; font-size: 26px; line-height: 34px; letter-spacing: -0.4px;">{escape(heading)}</h1>
                {content}
                {button}
                {fallback}
                {note_block}
              </td>
            </tr>
            <tr>
              <td style="padding: 24px 12px 0; color: #98a2b3; font-size: 12px; line-height: 18px; text-align: center;">
                This is an automated message from {BRAND_NAME}. Please do not reply to this email.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _paragraph(text: str) -> str:
    return f'<p style="margin: 0 0 16px; color: #475467; font-size: 15px; line-height: 24px;">{text}</p>'


def verification_email(full_name: str, token: str) -> tuple[str, str, str]:
    url = f"{settings.FRONTEND_URL.rstrip('/')}/verify-email?token={token}"
    safe_name = escape(full_name)
    subject = f"Verify your email to get started with {BRAND_NAME}"
    text = (
        f"Hello {full_name},\n\n"
        f"Thanks for creating your {BRAND_NAME} account. Please verify your email address "
        f"to finish setting up your account:\n\n{url}\n\n"
        f"This link will expire in {settings.EMAIL_VERIFICATION_EXPIRE_HOURS} hours. "
        f"If you did not create a {BRAND_NAME} account, you can safely ignore this email.\n\n"
        f"The {BRAND_NAME} team"
    )
    html = _email_layout(
        preview=f"Confirm your email address to activate your {BRAND_NAME} account.",
        heading="Verify your email address",
        content=(
            _paragraph(f"Hello {safe_name},")
            + _paragraph(
                f"Thanks for creating your {BRAND_NAME} account. Please confirm your email "
                "address to finish setting up your account."
            )
        ),
        action_label="Verify email address",
        action_url=url,
        note=(
            f"This link will expire in {settings.EMAIL_VERIFICATION_EXPIRE_HOURS} hours. "
            f"If you did not create a {BRAND_NAME} account, you can safely ignore this email."
        ),
    )
    return subject, html, text


def password_reset_email(full_name: str, token: str) -> tuple[str, str, str]:
    url = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"
    safe_name = escape(full_name)
    subject = f"Reset your {BRAND_NAME} password"
    text = (
        f"Hello {full_name},\n\n"
        f"We received a request to reset the password for your {BRAND_NAME} account. "
        f"Choose a new password using the link below:\n\n{url}\n\n"
        f"This link will expire in {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes. "
        "If you did not request a password reset, you can safely ignore this email; "
        "your password will remain unchanged.\n\n"
        f"The {BRAND_NAME} team"
    )
    html = _email_layout(
        preview=f"Use this secure link to reset your {BRAND_NAME} password.",
        heading="Reset your password",
        content=(
            _paragraph(f"Hello {safe_name},")
            + _paragraph(
                f"We received a request to reset the password for your {BRAND_NAME} account. "
                "Select the button below to choose a new password."
            )
        ),
        action_label="Reset password",
        action_url=url,
        note=(
            f"For your security, this link will expire in {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes. "
            "If you did not request a password reset, you can safely ignore this email; "
            "your password will remain unchanged."
        ),
    )
    return subject, html, text


def welcome_email(full_name: str) -> tuple[str, str, str]:
    dashboard_url = settings.FRONTEND_URL.rstrip("/")
    safe_name = escape(full_name)
    subject = f"Welcome to {BRAND_NAME} — your account is ready"
    text = (
        f"Welcome to {BRAND_NAME}, {full_name}!\n\n"
        "Your email has been verified and your account is ready. You can now configure your "
        "AI phone agent, add business knowledge, and start handling customer conversations.\n\n"
        f"Open your dashboard: {dashboard_url}\n\n"
        f"The {BRAND_NAME} team"
    )
    html = _email_layout(
        preview=f"Your {BRAND_NAME} account is verified and ready to use.",
        heading=f"Welcome to {BRAND_NAME}",
        content=(
            _paragraph(f"Hello {safe_name},")
            + _paragraph(
                "Your email has been verified and your account is ready. You can now configure "
                "your AI phone agent, add business knowledge, and start handling customer conversations."
            )
        ),
        action_label="Open your dashboard",
        action_url=dashboard_url,
        note="A good next step is to complete your company profile and customize your agent's greeting.",
    )
    return subject, html, text


def company_activated_email(full_name: str) -> tuple[str, str, str]:
    dashboard_url = settings.FRONTEND_URL.rstrip("/")
    safe_name = escape(full_name)
    subject = f"Your {BRAND_NAME} workspace is now active"
    text = (
        f"Hello {full_name},\n\n"
        f"Great news — your company workspace on {BRAND_NAME} is now active. "
        "You can sign in to manage your AI agents, phone connections, and customer interactions.\n\n"
        f"Open your dashboard: {dashboard_url}\n\n"
        f"The {BRAND_NAME} team"
    )
    html = _email_layout(
        preview=f"Your company workspace on {BRAND_NAME} is ready.",
        heading="Your workspace is active",
        content=(
            _paragraph(f"Hello {safe_name},")
            + _paragraph(
                f"Great news — your company workspace on {BRAND_NAME} is now active. "
                "You can sign in to manage your AI agents, phone connections, and customer interactions."
            )
        ),
        action_label="Go to dashboard",
        action_url=dashboard_url,
        note="Your workspace settings and team access can be managed from the dashboard.",
    )
    return subject, html, text
