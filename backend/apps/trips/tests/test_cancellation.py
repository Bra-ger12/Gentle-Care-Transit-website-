from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import RiderFactory, RiderProfileFactory
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


def test_rider_can_cancel_trip_more_than_24h_out(client, _auth):
    profile = RiderProfileFactory()
    trip = TripFactory(rider=profile, scheduled_pickup_time=timezone.now() + timedelta(hours=25))
    _auth(client, profile.user)

    response = client.post(f"/api/trips/{trip.id}/cancel/")

    assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert trip.status == TripStatus.CANCELLED
    assert trip.cancelled_by == profile.user
    assert trip.cancelled_at is not None


def test_rider_cannot_cancel_trip_less_than_24h_out(client, _auth):
    profile = RiderProfileFactory()
    trip = TripFactory(rider=profile, scheduled_pickup_time=timezone.now() + timedelta(hours=23))
    _auth(client, profile.user)

    response = client.post(f"/api/trips/{trip.id}/cancel/")

    assert response.status_code == 400
    trip.refresh_from_db()
    assert trip.status == TripStatus.REQUESTED


def test_admin_can_cancel_trip_less_than_24h_out(client, _auth):
    profile = RiderProfileFactory()
    trip = TripFactory(rider=profile, scheduled_pickup_time=timezone.now() + timedelta(hours=1))
    admin = RiderFactory(role=Role.ADMIN, is_staff=True)
    _auth(client, admin)

    response = client.post(f"/api/trips/{trip.id}/cancel/")

    assert response.status_code == 200
    trip.refresh_from_db()
    assert trip.status == TripStatus.CANCELLED


def test_rider_cannot_cancel_another_riders_trip(client, _auth):
    owner = RiderProfileFactory()
    other = RiderProfileFactory()
    trip = TripFactory(rider=owner, scheduled_pickup_time=timezone.now() + timedelta(hours=25))
    _auth(client, other.user)

    response = client.post(f"/api/trips/{trip.id}/cancel/")

    assert response.status_code in (403, 404)
    trip.refresh_from_db()
    assert trip.status == TripStatus.REQUESTED


def test_cannot_cancel_an_already_cancelled_trip(client, _auth):
    profile = RiderProfileFactory()
    trip = TripFactory(
        rider=profile,
        status=TripStatus.CANCELLED,
        scheduled_pickup_time=timezone.now() + timedelta(hours=25),
    )
    _auth(client, profile.user)

    response = client.post(f"/api/trips/{trip.id}/cancel/")

    assert response.status_code == 400
