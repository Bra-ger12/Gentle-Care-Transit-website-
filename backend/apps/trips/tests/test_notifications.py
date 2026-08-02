import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import (
    DriverProfileFactory,
    RiderFactory,
    RiderProfileFactory,
)
from apps.notifications.models import Notification, NotificationCategory
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


def _admin():
    return RiderFactory(role=Role.ADMIN, is_staff=True)


def test_confirm_notifies_rider(client, _auth):
    profile = RiderProfileFactory()
    trip = TripFactory(rider=profile, status=TripStatus.REQUESTED)
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/confirm/")

    assert response.status_code == 200, response.data
    assert Notification.objects.filter(
        recipient=profile.user, category=NotificationCategory.TRIP_CONFIRMED
    ).exists()


def test_assign_notifies_driver(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.CONFIRMED)
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/assign/", {"driver_id": driver.id}, format="json")

    assert response.status_code == 200, response.data
    assert Notification.objects.filter(
        recipient=driver.user, category=NotificationCategory.TRIP_ASSIGNED
    ).exists()


def test_cancel_notifies_the_other_participant(client, _auth):
    driver = DriverProfileFactory()
    profile = RiderProfileFactory()
    trip = TripFactory(rider=profile, status=TripStatus.ASSIGNED, assigned_driver=driver)
    # Admin cancels -> both participants are "other" and get notified.
    _auth(client, _admin())

    response = client.post(
        f"/api/trips/{trip.id}/cancel/", {"reason": "clinic closed"}, format="json"
    )

    assert response.status_code == 200, response.data
    assert Notification.objects.filter(
        recipient=profile.user, category=NotificationCategory.TRIP_CANCELLED
    ).exists()
    assert Notification.objects.filter(
        recipient=driver.user, category=NotificationCategory.TRIP_CANCELLED
    ).exists()
