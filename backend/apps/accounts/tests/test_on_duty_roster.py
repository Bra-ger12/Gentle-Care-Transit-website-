"""The on-duty roster the dispatch board assigns from.

A driver who is online but between jobs has no trip to hang a map marker off, so
before this endpoint existed the board could show an empty map with four people
online -- exactly the drivers a dispatcher wants when the next booking lands.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import DriverLocation
from apps.accounts.tests.factories import (
    AdminFactory,
    DriverProfileFactory,
    RiderProfileFactory,
)
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db

ENDPOINT = "/api/auth/drivers/on-duty/"


def place(driver, lat=46.8083, lng=-100.7837, minutes_ago=0):
    return DriverLocation.objects.create(
        driver=driver,
        lat=Decimal(str(lat)),
        lng=Decimal(str(lng)),
        reported_at=timezone.now() - timedelta(minutes=minutes_ago),
    )


def rows(client):
    response = client.get(ENDPOINT)
    assert response.status_code == 200, response.data
    return {row["name"]: row for row in response.data}


def test_only_on_duty_approved_drivers_are_listed(client, _auth):
    on = DriverProfileFactory(is_approved=True, is_available=True)
    off = DriverProfileFactory(is_approved=True, is_available=False)
    unapproved = DriverProfileFactory(is_approved=False, is_available=True)
    _auth(client, AdminFactory())

    listed = {row["id"] for row in client.get(ENDPOINT).data}

    assert on.id in listed
    assert off.id not in listed
    assert unapproved.id not in listed


def test_a_fresh_position_is_reported(client, _auth):
    driver = DriverProfileFactory()
    place(driver, minutes_ago=2)
    _auth(client, AdminFactory())

    row = client.get(ENDPOINT).data[0]

    assert row["lat"] is not None
    assert row["position_age_minutes"] == 2
    assert row["position_is_stale"] is False


def test_a_stale_position_is_flagged_not_hidden(client, _auth):
    """Dispatch needs to know the fix is old, not merely be denied it."""
    driver = DriverProfileFactory()
    place(driver, minutes_ago=45)
    _auth(client, AdminFactory())

    row = client.get(ENDPOINT).data[0]

    assert row["lat"] is not None
    assert row["position_is_stale"] is True
    assert row["position_age_minutes"] == 45


def test_a_driver_who_never_reported_has_no_position(client, _auth):
    DriverProfileFactory()
    _auth(client, AdminFactory())

    row = client.get(ENDPOINT).data[0]

    assert row["lat"] is None
    assert row["position_age_minutes"] is None
    assert row["position_is_stale"] is False


def test_the_current_job_travels_with_the_driver(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(
        assigned_driver=driver,
        status=TripStatus.EN_ROUTE,
        dropoff_address="Sanford Health, 300 N 7th St, Bismarck, ND",
    )
    _auth(client, AdminFactory())

    row = client.get(ENDPOINT).data[0]

    assert row["current_trip_id"] == str(trip.id)
    assert row["current_trip_status"] == TripStatus.EN_ROUTE
    assert "Sanford" in row["current_trip_dropoff"]


def test_a_driver_at_a_pickup_still_counts_as_working(client, _auth):
    """ARRIVED is an active state -- a driver at a rider's door is not free."""
    driver = DriverProfileFactory()
    TripFactory(assigned_driver=driver, status=TripStatus.ARRIVED)
    _auth(client, AdminFactory())

    row = client.get(ENDPOINT).data[0]

    assert row["active_trip_count"] == 1
    assert row["current_trip_status"] == TripStatus.ARRIVED


def test_a_free_driver_shows_no_current_trip(client, _auth):
    driver = DriverProfileFactory()
    TripFactory(assigned_driver=driver, status=TripStatus.COMPLETED)
    _auth(client, AdminFactory())

    row = client.get(ENDPOINT).data[0]

    assert row["active_trip_count"] == 0
    assert row["current_trip_id"] is None


def test_the_freest_driver_is_listed_first(client, _auth):
    busy = DriverProfileFactory()
    free = DriverProfileFactory()
    TripFactory(assigned_driver=busy, status=TripStatus.ASSIGNED)
    TripFactory(assigned_driver=busy, status=TripStatus.EN_ROUTE)
    _auth(client, AdminFactory())

    listed = [row["id"] for row in client.get(ENDPOINT).data]

    assert listed.index(free.id) < listed.index(busy.id)


def test_the_roster_is_admin_only(client, _auth):
    _auth(client, RiderProfileFactory().user)
    assert client.get(ENDPOINT).status_code == 403


def test_a_driver_cannot_read_the_roster(client, _auth):
    _auth(client, DriverProfileFactory().user)
    assert client.get(ENDPOINT).status_code == 403


def test_unauthenticated_access_is_refused(client):
    assert client.get(ENDPOINT).status_code == 401
