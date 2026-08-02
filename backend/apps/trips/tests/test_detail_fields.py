"""The dashboard redesign surfaces passenger + assigned-driver details on the trip
detail endpoint (driver's active-trip panel, rider's next-ride card)."""

import pytest

from apps.accounts.models import VehicleType
from apps.accounts.tests.factories import DriverProfileFactory, RiderProfileFactory
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


def test_detail_exposes_passenger_and_vehicle_fields(client, _auth):
    driver = DriverProfileFactory(vehicle_plate="ND-1234", vehicle_type=VehicleType.WHEELCHAIR_VAN)
    profile = RiderProfileFactory()
    profile.user.first_name = "Robert"
    profile.user.last_name = "Jones"
    profile.user.phone_number = "+17015550123"
    profile.user.save()
    trip = TripFactory(
        rider=profile,
        assigned_driver=driver,
        status=TripStatus.EN_ROUTE,
        mobility_need="WHEELCHAIR",
    )
    _auth(client, profile.user)

    response = client.get(f"/api/trips/{trip.id}/")

    assert response.status_code == 200, response.data
    data = response.data
    assert data["rider_name"] == "Robert Jones"
    assert data["rider_phone"] == "+17015550123"
    assert data["rider_mobility_needs"] == ["WHEELCHAIR"]
    assert data["assigned_driver_vehicle_plate"] == "ND-1234"
    assert data["assigned_driver_vehicle_type"] == VehicleType.WHEELCHAIR_VAN
    assert data["assigned_driver_rating"] is None  # no rated trips yet


def test_detail_averages_assigned_driver_rating(client, _auth):
    driver = DriverProfileFactory()
    for score in (5, 3):
        TripFactory(assigned_driver=driver, status=TripStatus.COMPLETED, rating=score)

    profile = RiderProfileFactory()
    trip = TripFactory(rider=profile, assigned_driver=driver, status=TripStatus.ASSIGNED)
    _auth(client, profile.user)

    response = client.get(f"/api/trips/{trip.id}/")

    assert response.status_code == 200, response.data
    assert response.data["assigned_driver_rating"] == 4.0


def test_detail_driver_fields_null_when_unassigned(client, _auth):
    profile = RiderProfileFactory()
    trip = TripFactory(rider=profile, status=TripStatus.REQUESTED)
    _auth(client, profile.user)

    response = client.get(f"/api/trips/{trip.id}/")

    assert response.status_code == 200, response.data
    assert response.data["assigned_driver_rating"] is None
    assert response.data["assigned_driver_vehicle_plate"] is None
