import pytest
from django.core import mail

from apps.accounts.tests.factories import RiderFactory
from apps.notifications import sms
from apps.notifications.models import (
    Notification,
    NotificationCategory,
    NotificationPreference,
)
from apps.notifications.services import notify

pytestmark = pytest.mark.django_db


def test_notify_creates_row_and_sends_email():
    user = RiderFactory(email="rider@example.com")
    result = notify(
        user,
        category=NotificationCategory.TRIP_CONFIRMED,
        title="Trip confirmed",
        body="Your ride is set.",
    )
    assert result is not None
    assert Notification.objects.filter(recipient=user).count() == 1
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["rider@example.com"]


def test_notify_dedupe_key_is_idempotent():
    user = RiderFactory()
    first = notify(
        user,
        category=NotificationCategory.TRIP_REMINDER,
        title="Reminder",
        body="Soon",
        dedupe_key="reminder:x:24h",
    )
    second = notify(
        user,
        category=NotificationCategory.TRIP_REMINDER,
        title="Reminder",
        body="Soon",
        dedupe_key="reminder:x:24h",
    )
    assert first is not None
    assert second is None
    assert Notification.objects.filter(dedupe_key="reminder:x:24h").count() == 1


def test_notify_respects_email_optout():
    user = RiderFactory()
    NotificationPreference.objects.create(user=user, email_enabled=False)
    notify(
        user,
        category=NotificationCategory.TRIP_CONFIRMED,
        title="Trip confirmed",
        body="Your ride is set.",
    )
    # In-app row still written; email suppressed by preference.
    assert Notification.objects.filter(recipient=user).count() == 1
    assert len(mail.outbox) == 0


def test_send_sms_is_noop_without_credentials(settings):
    settings.TWILIO_ACCOUNT_SID = ""
    settings.TWILIO_AUTH_TOKEN = ""
    settings.TWILIO_FROM_NUMBER = ""
    assert sms.send_sms("+17015550100", "hello") is False
