"""Email utilities for the Wicked Yoda Bot.

Provides a shared email sending capability for password resets,
notifications, and other outbound mail.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage


def get_smtp_config() -> dict:
    """Read SMTP configuration from environment variables."""
    return {
        "host": os.getenv("WEB_SMTP_HOST", "").strip(),
        "port": int(os.getenv("WEB_SMTP_PORT", "587")),
        "username": os.getenv("WEB_SMTP_USERNAME", "").strip(),
        "password": os.getenv("WEB_SMTP_PASSWORD", ""),
        "from_email": os.getenv("WEB_SMTP_FROM_EMAIL", "").strip(),
        "from_name": os.getenv("WEB_SMTP_FROM_NAME", "Wicked Yoda Bot Admin").strip(),
        "security": os.getenv("WEB_SMTP_SECURITY", "starttls").strip().lower(),
    }


def is_smtp_configured() -> bool:
    """Check if SMTP is configured and ready to send."""
    config = get_smtp_config()
    return bool(config["host"] and config["from_email"])


def send_email(
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> tuple[bool, str]:
    """
    Send an email using the configured SMTP settings.

    Returns:
        tuple[bool, str]: (success, message)
    """
    config = get_smtp_config()

    if not config["host"] or not config["from_email"]:
        return False, "SMTP not configured: missing host or from_email"

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{config['from_name']} <{config['from_email']}>"
    message["To"] = to_email

    if html_body:
        message.set_content(body)
        message.add_alternative(html_body, subtype="html")
    else:
        message.set_content(body)

    try:
        if config["security"] == "ssl":
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(config["host"], config["port"], timeout=15, context=context) as server:
                if config["username"]:
                    server.login(config["username"], config["password"])
                server.send_message(message)
        else:
            with smtplib.SMTP(config["host"], config["port"], timeout=15) as server:
                if config["security"] == "starttls":
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                if config["username"]:
                    server.login(config["username"], config["password"])
                server.send_message(message)

        return True, "Email sent successfully"

    except smtplib.SMTPAuthenticationError as e:
        return False, f"SMTP authentication failed: {e}"
    except smtplib.SMTPConnectError as e:
        return False, f"SMTP connection failed: {e}"
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {e}"
    except Exception as e:
        return False, f"Failed to send email: {e}"


def send_password_reset_email(to_email: str, reset_token: str, ttl_minutes: int = 30) -> tuple[bool, str]:
    """
    Send a password reset email to the user.

    Args:
        to_email: Recipient email address
        reset_token: The reset token from the web admin
        ttl_minutes: Token time-to-live in minutes

    Returns:
        tuple[bool, str]: (success, message)
    """
    base_url = os.getenv("WEB_PUBLIC_BASE_URL", "").strip()
    if not base_url:
        return False, "WEB_PUBLIC_BASE_URL not configured"

    reset_link = f"{base_url.rstrip('/')}/admin/password-reset/confirm?token={reset_token}"

    subject = "Wicked Yoda Bot Admin - Password Reset"

    body = f"""
A password reset was requested for your Wicked Yoda Bot Admin account.

Reset link: {reset_link}

This link expires in {ttl_minutes} minutes and can only be used once.

If you did not request this, you can ignore this email.
""".strip()

    html_body = f"""
<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2>Password Reset Request</h2>
        <p>A password reset was requested for your <strong>Wicked Yoda Bot Admin</strong> account.</p>
        <p>
            <a href="{reset_link}" style="display: inline-block; padding: 12px 24px; background-color: #2563eb; color: white; text-decoration: none; border-radius: 4px;">
                Reset Your Password
            </a>
        </p>
        <p>Or copy this link: <a href="{reset_link}">{reset_link}</a></p>
        <p><small>This link expires in {ttl_minutes} minutes and can only be used once.</small></p>
        <p><small>If you did not request this, you can ignore this email.</small></p>
    </div>
</body>
</html>
""".strip()

    return send_email(to_email, subject, body, html_body)


# Backwards compatibility function for webui/app.py
def _send_password_reset_email(target_email: str, raw_token: str) -> None:
    """Legacy internal function - raises on failure."""
    success, message = send_password_reset_email(target_email, raw_token)
    if not success:
        raise RuntimeError(message)
