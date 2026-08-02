"""Account emails and the tokens that back them.

Verification uses its own token generator rather than Django's default one, so a
verification link can never be replayed as a password reset. Including
`is_verified` in the hash also makes each link single-use: the moment the address
is confirmed, every outstanding link for it stops working.
"""

import logging

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger(__name__)


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    key_salt = "apps.accounts.email-verification"

    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{timestamp}{user.is_verified}{user.email}"


email_verification_token = EmailVerificationTokenGenerator()


def make_email_verification_link(user, frontend_url: str) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    return f"{frontend_url}/verify-email.html?uid={uid}&token={token}"


def send_verification_email(user) -> bool:
    """Best-effort: a mail failure must not roll back a registration.

    A rider who signs up and never gets the email can ask for another from the
    banner on their dashboard, which is a far better outcome than losing the
    account entirely because SMTP was down for a minute.
    """
    link = make_email_verification_link(user, settings.FRONTEND_URL)
    try:
        send_mail(
            subject="Confirm your Gentle Care Transit email",
            message=(
                f"Hello {user.get_short_name()},\n\n"
                "Confirm this address so we can send you trip confirmations, "
                "driver updates and appointment reminders:\n\n"
                f"{link}\n\n"
                "If you didn't create an account, you can ignore this message.\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )
        return True
    except Exception:  # noqa: BLE001
        logger.exception("verification email to %s failed", user.email)
        return False
