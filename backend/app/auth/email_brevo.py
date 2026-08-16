"""
Brevo transactional email — used only for the password-reset OTP.
If BREVO_API_KEY/BREVO_SENDER_EMAIL aren't set, sending is skipped and
logged; the reset flow still works end-to-end (the OTP just won't reach
an inbox), matching the "never break the app over email" requirement.
"""

import logging

import httpx

from app.core.config import BREVO_API_KEY, BREVO_SENDER_EMAIL, BREVO_SENDER_NAME

logger = logging.getLogger("urban_pulse.auth")

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def is_configured() -> bool:
    return bool(BREVO_API_KEY and BREVO_SENDER_EMAIL)


def send_otp_email(to_email: str, otp: str) -> bool:
    if not is_configured():
        logger.info("Brevo not configured; skipping OTP email delivery")
        return False

    try:
        response = httpx.post(
            BREVO_URL,
            headers={
                "api-key": BREVO_API_KEY,
                "content-type": "application/json",
                "accept": "application/json",
            },
            json={
                "sender": {"email": BREVO_SENDER_EMAIL, "name": BREVO_SENDER_NAME},
                "to": [{"email": to_email}],
                "subject": "Your Urban Pulse password reset code",
                "htmlContent": (
                    f"<p>Your password reset code is <strong>{otp}</strong>.</p>"
                    f"<p>It expires in 10 minutes. If you didn't request this, ignore this email.</p>"
                ),
            },
            timeout=6,
        )
        response.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("Brevo send failed: %s", type(exc).__name__)
        return False
