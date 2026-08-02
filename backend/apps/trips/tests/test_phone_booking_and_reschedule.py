"""Dispatch booking a trip over the phone, and moving a trip that already exists."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import (
    AdminFactory,
    DriverProfileFactory,
    RiderProfileFactory,
)
from apps.notifications.models import Notification
from apps.trips.models import Trip, TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db

HOME = "1420 Boulevard Ave, Bismarck, ND"
CLINIC = "Sanford Health, 300 N 7th St, Bismarck, ND"


def _payload(**overrides):
    payload = {
        "scheduled_pickup_time": (timezone.now() + timedelta(days=3)).isoformat(),
        "pickup_address": HOME,
        "dropoff_address": CLINIC,
    }
    payload.update(overrides)
    return payload


# --- phone booking -------------------------------------------------------


def test_admin_books_on_behalf_of_a_rider(client, _auth):
    admin = AdminFactory()
    rider = RiderProfileFactory()
    _auth(client, admin)

    response = client.post("/api/trips/", _payload(rider_id=str(rider.id)), format="json")

    assert response.status_code == 201, response.data
    trip = Trip.objects.get()
    assert trip.rider == rider
    # Who took the call is recorded separately from whose trip it is.
    assert trip.created_by == admin


def test_admin_must_say_who_the_booking_is_for(client, _auth):
    _auth(client, AdminFactory())

    response = client.post("/api/trips/", _payload(), format="json")

    assert response.status_code == 400
    assert "rider_id" in response.data
    assert Trip.objects.count() == 0


def test_admin_booking_for_an_unknown_rider_is_rejected(client, _auth):
    _auth(client, AdminFactory())
    response = client.post(
        "/api/trips/",
        _payload(rider_id="00000000-0000-0000-0000-000000000000"),
        format="json",
    )
    assert response.status_code == 400


def test_admin_cannot_book_for_a_suspended_rider(client, _auth):
    admin = AdminFactory()
    rider = RiderProfileFactory()
    rider.user.is_active = False
    rider.user.save()
    _auth(client, admin)

    response = client.post("/api/trips/", _payload(rider_id=str(rider.id)), format="json")

    assert response.status_code == 400
    assert "suspended" in str(response.data["rider_id"])


def test_a_rider_cannot_book_for_someone_else(client, _auth):
    rider = RiderProfileFactory()
    victim = RiderProfileFactory()
    _auth(client, rider.user)

    response = client.post("/api/trips/", _payload(rider_id=str(victim.id)), format="json")

    assert response.status_code == 400
    assert "yourself" in str(response.data["rider_id"])
    assert Trip.objects.count() == 0


def test_a_phone_booking_skips_the_rider_email_gate(client, _auth):
    """Dispatch took the call; the rider's inbox isn't the channel here."""
    admin = AdminFactory()
    rider = RiderProfileFactory()
    rider.user.is_verified = False
    rider.user.save()
    _auth(client, admin)

    response = client.post("/api/trips/", _payload(rider_id=str(rider.id)), format="json")
    assert response.status_code == 201, response.data


def test_a_driver_still_cannot_book(client, _auth):
    _auth(client, DriverProfileFactory().user)
    assert client.post("/api/trips/", _payload(), format="json").status_code == 403


# --- reschedule ----------------------------------------------------------


def _future_trip(rider, **overrides):
    fields = {
        "rider": rider,
        "status": TripStatus.CONFIRMED,
        "scheduled_pickup_time": timezone.now() + timedelta(days=5),
    }
    fields.update(overrides)
    return TripFactory(**fields)


def test_rider_can_move_a_trip(client, _auth):
    rider = RiderProfileFactory()
    trip = _future_trip(rider)
    _auth(client, rider.user)
    new_time = timezone.now() + timedelta(days=6)

    response = client.post(
        f"/api/trips/{trip.id}/reschedule/",
        {"scheduled_pickup_time": new_time.isoformat(), "reason": "clinic moved it"},
        format="json",
    )

    assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert abs((trip.scheduled_pickup_time - new_time).total_seconds()) < 2


def test_rescheduling_inside_the_cutoff_is_refused(client, _auth):
    rider = RiderProfileFactory()
    trip = _future_trip(rider, scheduled_pickup_time=timezone.now() + timedelta(hours=6))
    _auth(client, rider.user)

    response = client.post(
        f"/api/trips/{trip.id}/reschedule/",
        {"scheduled_pickup_time": (timezone.now() + timedelta(days=2)).isoformat()},
        format="json",
    )

    assert response.status_code == 400
    assert "24 hours" in str(response.data)


def test_an_admin_may_move_a_trip_inside_the_cutoff(client, _auth):
    rider = RiderProfileFactory()
    trip = _future_trip(rider, scheduled_pickup_time=timezone.now() + timedelta(hours=6))
    _auth(client, AdminFactory())

    response = client.post(
        f"/api/trips/{trip.id}/reschedule/",
        {"scheduled_pickup_time": (timezone.now() + timedelta(days=2)).isoformat()},
        format="json",
    )
    assert response.status_code == 200, response.data


def test_the_new_time_must_respect_the_lead_time(client, _auth):
    rider = RiderProfileFactory()
    trip = _future_trip(rider)
    _auth(client, rider.user)

    response = client.post(
        f"/api/trips/{trip.id}/reschedule/",
        {"scheduled_pickup_time": (timezone.now() + timedelta(minutes=5)).isoformat()},
        format="json",
    )

    assert response.status_code == 400
    assert "scheduled_pickup_time" in response.data


def test_moving_an_assigned_trip_releases_its_driver(client, _auth):
    """Whoever accepted a 09:00 pickup did not agree to a 15:00 one."""
    rider = RiderProfileFactory()
    driver = DriverProfileFactory()
    trip = _future_trip(
        rider,
        status=TripStatus.ASSIGNED,
        assigned_driver=driver,
        accepted_at=timezone.now(),
    )
    _auth(client, AdminFactory())

    response = client.post(
        f"/api/trips/{trip.id}/reschedule/",
        {"scheduled_pickup_time": (timezone.now() + timedelta(days=7)).isoformat()},
        format="json",
    )

    assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert trip.status == TripStatus.CONFIRMED
    assert trip.assigned_driver is None
    assert trip.accepted_at is None


def test_the_released_driver_is_told(client, _auth):
    rider = RiderProfileFactory()
    driver = DriverProfileFactory()
    trip = _future_trip(rider, status=TripStatus.ASSIGNED, assigned_driver=driver)
    _auth(client, AdminFactory())

    client.post(
        f"/api/trips/{trip.id}/reschedule/",
        {"scheduled_pickup_time": (timezone.now() + timedelta(days=7)).isoformat()},
        format="json",
    )

    assert Notification.objects.filter(
        recipient=driver.user, title="Trip removed from your schedule"
    ).exists()


def test_the_rider_is_told_their_trip_moved(client, _auth):
    rider = RiderProfileFactory()
    trip = _future_trip(rider)
    _auth(client, AdminFactory())

    client.post(
        f"/api/trips/{trip.id}/reschedule/",
        {"scheduled_pickup_time": (timezone.now() + timedelta(days=7)).isoformat()},
        format="json",
    )

    assert Notification.objects.filter(recipient=rider.user, title="Trip moved").exists()


@pytest.mark.parametrize(
    "status",
    [TripStatus.EN_ROUTE, TripStatus.PICKED_UP, TripStatus.COMPLETED, TripStatus.CANCELLED],
)
def test_a_trip_already_underway_cannot_be_moved(client, _auth, status):
    rider = RiderProfileFactory()
    trip = _future_trip(rider, status=status)
    _auth(client, AdminFactory())

    response = client.post(
        f"/api/trips/{trip.id}/reschedule/",
        {"scheduled_pickup_time": (timezone.now() + timedelta(days=7)).isoformat()},
        format="json",
    )
    assert response.status_code == 400


def test_a_stranger_cannot_move_someone_elses_trip(client, _auth):
    trip = _future_trip(RiderProfileFactory())
    _auth(client, RiderProfileFactory().user)

    response = client.post(
        f"/api/trips/{trip.id}/reschedule/",
        {"scheduled_pickup_time": (timezone.now() + timedelta(days=7)).isoformat()},
        format="json",
    )
    assert response.status_code == 404


def test_rescheduling_is_audited(client, _auth):
    from apps.audit.models import AuditLog

    rider = RiderProfileFactory()
    trip = _future_trip(rider)
    _auth(client, AdminFactory())

    client.post(
        f"/api/trips/{trip.id}/reschedule/",
        {
            "scheduled_pickup_time": (timezone.now() + timedelta(days=7)).isoformat(),
            "reason": "clinic rebooked",
        },
        format="json",
    )

    entry = AuditLog.objects.filter(object_id=str(trip.id)).first()
    assert entry.metadata["action"] == "rescheduled"
    assert entry.metadata["reason"] == "clinic rebooked"
