"""Tests for the four "system map" features: rating & review, driver
availability, driver reports, and admin account/vehicle management."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Role, VehicleType
from apps.accounts.tests.factories import (
    DriverProfileFactory,
    RiderFactory,
    RiderProfileFactory,
)
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


def _admin():
    return RiderFactory(role=Role.ADMIN, is_staff=True)


# --- Rating & Review -------------------------------------------------------


def test_rider_can_rate_completed_trip(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.COMPLETED, assigned_driver=driver)
    _auth(client, trip.rider.user)

    response = client.post(f"/api/trips/{trip.id}/rate/", {"rating": 5, "review": "Great ride"})

    assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert trip.rating == 5
    assert trip.review == "Great ride"
    assert trip.rated_at is not None


def test_cannot_rate_non_completed_trip(client, _auth):
    trip = TripFactory(status=TripStatus.CONFIRMED)
    _auth(client, trip.rider.user)

    response = client.post(f"/api/trips/{trip.id}/rate/", {"rating": 4})

    assert response.status_code == 400
    trip.refresh_from_db()
    assert trip.rating is None


def test_cannot_rate_twice(client, _auth):
    trip = TripFactory(status=TripStatus.COMPLETED)
    _auth(client, trip.rider.user)

    assert client.post(f"/api/trips/{trip.id}/rate/", {"rating": 4}).status_code == 200
    assert client.post(f"/api/trips/{trip.id}/rate/", {"rating": 2}).status_code == 400


def test_rating_out_of_range_rejected(client, _auth):
    trip = TripFactory(status=TripStatus.COMPLETED)
    _auth(client, trip.rider.user)

    assert client.post(f"/api/trips/{trip.id}/rate/", {"rating": 6}).status_code == 400


def test_other_rider_cannot_rate(client, _auth):
    trip = TripFactory(status=TripStatus.COMPLETED)
    other = RiderProfileFactory()
    _auth(client, other.user)

    response = client.post(f"/api/trips/{trip.id}/rate/", {"rating": 5})

    assert response.status_code in (403, 404)
    trip.refresh_from_db()
    assert trip.rating is None


def test_driver_average_rating_in_profile(client, _auth):
    driver = DriverProfileFactory()
    for score in (5, 3):
        trip = TripFactory(status=TripStatus.COMPLETED, assigned_driver=driver)
        _auth(client, trip.rider.user)
        client.post(f"/api/trips/{trip.id}/rate/", {"rating": score})

    _auth(client, driver.user)
    response = client.get("/api/auth/me/driver-profile/")

    assert response.status_code == 200
    assert response.data["average_rating"] == 4.0
    assert response.data["ratings_count"] == 2


# --- Driver availability ---------------------------------------------------


def test_driver_can_toggle_availability(client, _auth):
    driver = DriverProfileFactory(is_available=True)
    _auth(client, driver.user)

    response = client.patch("/api/auth/me/driver-profile/", {"is_available": False}, format="json")

    assert response.status_code == 200, response.data
    driver.refresh_from_db()
    assert driver.is_available is False


def test_auto_assign_skips_offline_driver(client, _auth):
    trip = TripFactory(status=TripStatus.CONFIRMED)
    DriverProfileFactory(is_available=False)
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/auto-assign/")

    assert response.status_code == 400
    trip.refresh_from_db()
    assert trip.status == TripStatus.CONFIRMED


def test_auto_assign_picks_online_driver(client, _auth):
    trip = TripFactory(status=TripStatus.CONFIRMED)
    driver = DriverProfileFactory(is_available=True)
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/auto-assign/")

    assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert trip.assigned_driver == driver


def test_manual_assign_allows_offline_driver(client, _auth):
    trip = TripFactory(status=TripStatus.CONFIRMED)
    driver = DriverProfileFactory(is_available=False)
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/assign/", {"driver_id": str(driver.id)})

    assert response.status_code == 200, response.data


# --- Driver reports --------------------------------------------------------


def test_driver_report_aggregates_trips_and_miles(client, _auth):
    driver = DriverProfileFactory()
    for _ in range(2):
        TripFactory(
            status=TripStatus.COMPLETED,
            assigned_driver=driver,
            scheduled_pickup_time=timezone.now() - timedelta(days=1),
            mileage="4.00",
        )
    _auth(client, driver.user)

    response = client.get("/api/reports/driver/summary/")

    assert response.status_code == 200, response.data
    assert response.data["total_trips"] == 2
    assert response.data["completed"] == 2
    assert response.data["total_miles"] == 8.0


def test_driver_report_forbidden_for_rider(client, _auth):
    rider = RiderProfileFactory()
    _auth(client, rider.user)

    assert client.get("/api/reports/driver/summary/").status_code == 403


# --- Admin account management ----------------------------------------------


def test_admin_can_suspend_and_activate_user(client, _auth):
    rider = RiderProfileFactory()
    _auth(client, _admin())

    suspend = client.post(f"/api/auth/users/{rider.user.id}/suspend/")
    assert suspend.status_code == 200, suspend.data
    rider.user.refresh_from_db()
    assert rider.user.is_active is False

    activate = client.post(f"/api/auth/users/{rider.user.id}/activate/")
    assert activate.status_code == 200
    rider.user.refresh_from_db()
    assert rider.user.is_active is True


def test_admin_cannot_suspend_admin(client, _auth):
    target = RiderFactory(role=Role.ADMIN, is_staff=True)
    _auth(client, _admin())

    response = client.post(f"/api/auth/users/{target.id}/suspend/")

    assert response.status_code == 400
    target.refresh_from_db()
    assert target.is_active is True


def test_admin_cannot_suspend_self(client, _auth):
    admin = _admin()
    _auth(client, admin)

    assert client.post(f"/api/auth/users/{admin.id}/suspend/").status_code == 400


def test_non_admin_cannot_list_users(client, _auth):
    rider = RiderProfileFactory()
    _auth(client, rider.user)

    assert client.get("/api/auth/users/").status_code == 403


# --- Admin vehicle management ----------------------------------------------


def test_admin_can_update_driver_vehicle(client, _auth):
    driver = DriverProfileFactory(vehicle_type=VehicleType.SEDAN)
    _auth(client, _admin())

    response = client.patch(
        f"/api/auth/drivers/{driver.id}/vehicle/",
        {
            "vehicle_type": VehicleType.WHEELCHAIR_VAN,
            "vehicle_plate": "ND 1234",
            "vehicle_capacity": 6,
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    driver.refresh_from_db()
    assert driver.vehicle_type == VehicleType.WHEELCHAIR_VAN
    assert driver.vehicle_plate == "ND 1234"
    assert driver.vehicle_capacity == 6
