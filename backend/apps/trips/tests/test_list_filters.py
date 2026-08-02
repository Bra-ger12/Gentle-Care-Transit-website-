"""The dashboards read the trip list by day (driver manifest, dispatch "today"
counts) and plot it on a map, so the list endpoint filters by scheduled date and
carries pickup/drop-off coordinates."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import RiderFactory
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_user():
    return RiderFactory(role=Role.ADMIN, is_staff=True)


def test_date_filter_returns_only_that_days_trips(client, _auth, admin_user):
    today = timezone.localtime()
    todays_trip = TripFactory(scheduled_pickup_time=today + timedelta(minutes=90))
    TripFactory(scheduled_pickup_time=today + timedelta(days=2))
    _auth(client, admin_user)

    response = client.get(f"/api/trips/?date={today.date().isoformat()}")

    assert response.status_code == 200, response.data
    assert [t["id"] for t in response.data["results"]] == [str(todays_trip.id)]


def test_date_filter_combines_with_status(client, _auth, admin_user):
    today = timezone.localtime()
    assigned = TripFactory(
        scheduled_pickup_time=today + timedelta(minutes=90), status=TripStatus.ASSIGNED
    )
    TripFactory(scheduled_pickup_time=today + timedelta(minutes=120), status=TripStatus.COMPLETED)
    _auth(client, admin_user)

    response = client.get(f"/api/trips/?date={today.date().isoformat()}&status=ASSIGNED")

    assert response.status_code == 200, response.data
    assert [t["id"] for t in response.data["results"]] == [str(assigned.id)]


@pytest.mark.parametrize("value", ["not-a-date", "2026-13-01", "26/07/2026"])
def test_malformed_date_is_rejected(client, _auth, admin_user, value):
    _auth(client, admin_user)

    response = client.get(f"/api/trips/?date={value}")

    assert response.status_code == 400, response.data
    assert "date" in response.data


def test_list_exposes_acceptance_state(client, _auth, admin_user):
    """The dispatch board offers "Reassign" only for a trip no driver has accepted."""
    accepted_at = timezone.now()
    TripFactory(status=TripStatus.ASSIGNED, accepted_at=None)
    TripFactory(status=TripStatus.ASSIGNED, accepted_at=accepted_at)
    _auth(client, admin_user)

    response = client.get("/api/trips/?status=ASSIGNED")

    assert response.status_code == 200, response.data
    states = sorted(row["accepted_at"] is None for row in response.data["results"])
    assert states == [False, True]


def test_list_includes_map_coordinates(client, _auth, admin_user):
    trip = TripFactory()
    _auth(client, admin_user)

    response = client.get("/api/trips/")

    assert response.status_code == 200, response.data
    row = response.data["results"][0]
    assert row["id"] == str(trip.id)
    assert float(row["pickup_lat"]) == float(trip.pickup_lat)
    assert float(row["pickup_lng"]) == float(trip.pickup_lng)
    assert float(row["dropoff_lat"]) == float(trip.dropoff_lat)
    assert float(row["dropoff_lng"]) == float(trip.dropoff_lng)
