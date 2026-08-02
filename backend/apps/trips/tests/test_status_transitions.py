from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import RiderFactory, RiderProfileFactory
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


def _admin():
    return RiderFactory(role=Role.ADMIN, is_staff=True)


def test_admin_can_confirm_a_requested_trip(client, _auth):
    trip = TripFactory(status=TripStatus.REQUESTED)
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/confirm/")

    assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert trip.status == TripStatus.CONFIRMED


def test_rider_forbidden_from_confirm(client, _auth):
    profile = RiderProfileFactory()
    trip = TripFactory(rider=profile, status=TripStatus.REQUESTED)
    _auth(client, profile.user)

    response = client.post(f"/api/trips/{trip.id}/confirm/")

    assert response.status_code == 403


def test_cannot_complete_a_requested_trip_directly(client, _auth):
    trip = TripFactory(status=TripStatus.REQUESTED)
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/complete/")

    assert response.status_code == 400
    trip.refresh_from_db()
    assert trip.status == TripStatus.REQUESTED


def test_cannot_confirm_a_completed_trip(client, _auth):
    trip = TripFactory(
        status=TripStatus.COMPLETED,
        scheduled_pickup_time=timezone.now() + timedelta(days=1),
    )
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/confirm/")

    assert response.status_code == 400


def test_cannot_complete_a_confirmed_trip_directly(client, _auth):
    """A trip must be assigned/driven through the pipeline; CONFIRMED can no
    longer jump straight to COMPLETED now that dispatch exists (Phase 3)."""
    trip = TripFactory(status=TripStatus.CONFIRMED)
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/complete/")

    assert response.status_code == 400
    trip.refresh_from_db()
    assert trip.status == TripStatus.CONFIRMED


def test_cannot_mark_a_confirmed_trip_no_show_directly(client, _auth):
    trip = TripFactory(status=TripStatus.CONFIRMED)
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/no-show/")

    assert response.status_code == 400
    trip.refresh_from_db()
    assert trip.status == TripStatus.CONFIRMED
