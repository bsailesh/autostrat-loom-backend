"""
Minimal SMTP email sending using only the Python standard library.

Works with AWS SES's SMTP interface, Gmail (with an app password), SendGrid,
Postmark, or any other SMTP provider — just fill in the SMTP_* values in
.env. If SMTP_HOST is left empty, send_email() logs a warning and returns
False instead of raising, so local development and tests never break just
because email isn't configured yet.
"""
import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger("loom.email")


def send_email(*, to: str, subject: str, body: str) -> bool:
    settings = get_settings()

    if not settings.smtp_host:
        logger.warning("SMTP not configured (SMTP_HOST is empty) — skipping send. Subject: %s", subject)
        return False

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False
