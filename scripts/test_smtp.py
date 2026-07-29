"""Send one real email using the SMTP settings loaded by the application."""

import argparse
import sys

from app.core.config import settings
from app.modules.notifications.email.providers.smtp import SMTPEmailProvider


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a real SMTP diagnostic email")
    parser.add_argument("recipient", help="Email address that should receive the test")
    args = parser.parse_args()

    if settings.EMAIL_PROVIDER.casefold() != "smtp":
        print("EMAIL_PROVIDER must be set to smtp.", file=sys.stderr)
        return 2
    if not settings.SMTP_HOST:
        print("SMTP_HOST must be configured.", file=sys.stderr)
        return 2

    SMTPEmailProvider().send(
        recipient=args.recipient,
        subject=f"{settings.APP_NAME} SMTP test",
        text_body=(
            f"This is a test email from {settings.APP_NAME}. "
            "If you received it, the SMTP configuration is working."
        ),
        html_body=(
            f"<p>This is a test email from <strong>{settings.APP_NAME}</strong>.</p>"
            "<p>If you received it, the SMTP configuration is working.</p>"
        ),
    )
    print(f"SMTP accepted the test message for {args.recipient}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

