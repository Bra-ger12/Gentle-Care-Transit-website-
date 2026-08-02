import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def sms_configured() -> bool:
    return all(
        [
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_AUTH_TOKEN,
            settings.TWILIO_FROM_NUMBER,
        ]
    )


def send_sms(to: str, body: str) -> bool:
    """Send an SMS via Twilio. Degrades to a logged no-op when credentials are
    absent (the dev default) -- the same graceful pattern as the WeasyPrint PDF
    export. The `twilio` import is lazy so the package's absence never breaks
    app startup or unrelated code paths. Returns True only if actually sent."""
    if not to:
        return False
    if not sms_configured():
        logger.info("SMS skipped (Twilio not configured): to=%s body=%r", to, body)
        return False

    try:
        from twilio.rest import Client

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(to=to, from_=settings.TWILIO_FROM_NUMBER, body=body)
        return True
    except Exception:  # noqa: BLE001 -- never let SMS failure break the caller
        logger.exception("Twilio SMS send failed (to=%s)", to)
        return False
