from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import DriverProfileFactory, RiderFactory
from apps.notifications.models import Notification, NotificationCategory
from apps.notifications.tasks import check_document_expiry, send_trip_reminders
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


def test_trip_reminders_notify_rider_and_are_idempotent():
    trip = TripFactory(
        status=TripStatus.CONFIRMED,
        scheduled_pickup_time=timezone.now() + timedelta(hours=12),
    )

    first = send_trip_reminders()
    second = send_trip_reminders()

    assert first >= 1
    assert second == 0  # dedupe_key makes the second sweep a no-op
    assert (
        Notification.objects.filter(
            recipient=trip.rider.user, category=NotificationCategory.TRIP_REMINDER
        ).count()
        == 1
    )


def test_trip_reminders_skip_far_future_trips():
    TripFactory(
        status=TripStatus.CONFIRMED,
        scheduled_pickup_time=timezone.now() + timedelta(days=5),
    )
    assert send_trip_reminders() == 0


def test_document_expiry_alerts_driver_and_admin_and_is_idempotent():
    admin = RiderFactory(role=Role.ADMIN, is_staff=True)
    driver = DriverProfileFactory(license_expiry_date=timezone.localdate() + timedelta(days=5))

    first = check_document_expiry()
    second = check_document_expiry()

    assert first >= 2  # driver + admin
    assert second == 0
    assert Notification.objects.filter(
        recipient=driver.user, category=NotificationCategory.DOC_EXPIRY
    ).exists()
    assert Notification.objects.filter(
        recipient=admin, category=NotificationCategory.DOC_EXPIRY
    ).exists()


def test_document_expiry_skips_far_out_licenses():
    DriverProfileFactory(license_expiry_date=timezone.localdate() + timedelta(days=120))
    assert check_document_expiry() == 0
