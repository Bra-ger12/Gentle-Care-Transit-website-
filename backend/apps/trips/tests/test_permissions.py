import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import (
    DriverFactory,
    DriverProfileFactory,
    RiderFactory,
    RiderProfileFactory,
)
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


def test_rider_list_scoped_to_own_trips(client, _auth):
    mine = RiderProfileFactory()
    other = RiderProfileFactory()
    my_trip = TripFactory(rider=mine)
    TripFactory(rider=other)
    _auth(client, mine.user)

    response = client.get("/api/trips/")

    assert response.status_code == 200
    ids = {row["id"] for row in response.data["results"]}
    assert ids == {str(my_trip.id)}


def test_admin_list_sees_all_trips(client, _auth):
    TripFactory(rider=RiderProfileFactory())
    TripFactory(rider=RiderProfileFactory())
    admin = RiderFactory(role=Role.ADMIN, is_staff=True)
    _auth(client, admin)

    response = client.get("/api/trips/")

    assert response.status_code == 200
    assert response.data["count"] == 2


def test_driver_list_sees_no_trips(client, _auth):
    TripFactory(rider=RiderProfileFactory())
    driver = DriverFactory()
    _auth(client, driver)

    response = client.get("/api/trips/")

    assert response.status_code == 200
    assert response.data["count"] == 0


def test_retrieve_of_another_riders_trip_is_404(client, _auth):
    owner = RiderProfileFactory()
    other = RiderProfileFactory()
    trip = TripFactory(rider=owner)
    _auth(client, other.user)

    response = client.get(f"/api/trips/{trip.id}/")

    assert response.status_code == 404


def test_driver_list_scoped_to_assigned_trips(client, _auth):
    mine = DriverProfileFactory()
    other = DriverProfileFactory()
    my_trip = TripFactory(status=TripStatus.ASSIGNED, assigned_driver=mine)
    TripFactory(status=TripStatus.ASSIGNED, assigned_driver=other)
    TripFactory(rider=RiderProfileFactory())  # unassigned CONFIRMED-style trip
    _auth(client, mine.user)

    response = client.get("/api/trips/")

    assert response.status_code == 200
    ids = {row["id"] for row in response.data["results"]}
    assert ids == {str(my_trip.id)}


def test_retrieve_of_unrelated_trip_is_404_for_driver(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(rider=RiderProfileFactory())
    _auth(client, driver.user)

    response = client.get(f"/api/trips/{trip.id}/")

    assert response.status_code == 404
