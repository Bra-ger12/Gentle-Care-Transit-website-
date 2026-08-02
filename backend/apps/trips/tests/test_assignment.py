from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import MobilityNeed, Role, VehicleType
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


def test_admin_can_manually_assign_an_eligible_driver(client, _auth):
    trip = TripFactory(status=TripStatus.CONFIRMED)
    driver = DriverProfileFactory()
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/assign/", {"driver_id": str(driver.id)})

    assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert trip.status == TripStatus.ASSIGNED
    assert trip.assigned_driver == driver
    assert trip.assigned_at is not None
    assert trip.accepted_at is None


def test_manual_assign_rejects_unapproved_driver(client, _auth):
    trip = TripFactory(status=TripStatus.CONFIRMED)
    driver = DriverProfileFactory(is_approved=False)
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/assign/", {"driver_id": str(driver.id)})

    assert response.status_code == 400
    trip.refresh_from_db()
    assert trip.status == TripStatus.CONFIRMED


@pytest.mark.parametrize(
    "mobility_need,vehicle_type,expected_status",
    [
        (MobilityNeed.STRETCHER, VehicleType.SEDAN, 400),
        (MobilityNeed.STRETCHER, VehicleType.STRETCHER_VAN, 200),
        (MobilityNeed.WHEELCHAIR, VehicleType.SEDAN, 400),
        (MobilityNeed.WHEELCHAIR, VehicleType.WHEELCHAIR_VAN, 200),
        (MobilityNeed.WHEELCHAIR, VehicleType.STRETCHER_VAN, 200),
        (MobilityNeed.AMBULATORY, VehicleType.SEDAN, 200),
    ],
)
def test_manual_assign_vehicle_capability_rules(
    client, _auth, mobility_need, vehicle_type, expected_status
):
    trip = TripFactory(status=TripStatus.CONFIRMED, mobility_need=mobility_need)
    driver = DriverProfileFactory(vehicle_type=vehicle_type)
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/assign/", {"driver_id": str(driver.id)})

    assert response.status_code == expected_status, response.data


def test_manual_assign_rejects_double_booked_driver(client, _auth):
    pickup_time = timezone.now() + timedelta(days=3)
    driver = DriverProfileFactory()
    TripFactory(
        status=TripStatus.ASSIGNED,
        assigned_driver=driver,
        scheduled_pickup_time=pickup_time + timedelta(minutes=30),
    )
    trip = TripFactory(status=TripStatus.CONFIRMED, scheduled_pickup_time=pickup_time)
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/assign/", {"driver_id": str(driver.id)})

    assert response.status_code == 400


def test_manual_assign_allows_driver_whose_conflict_is_outside_window(client, _auth):
    pickup_time = timezone.now() + timedelta(days=3)
    driver = DriverProfileFactory()
    TripFactory(
        status=TripStatus.ASSIGNED,
        assigned_driver=driver,
        scheduled_pickup_time=pickup_time + timedelta(hours=3),
    )
    trip = TripFactory(status=TripStatus.CONFIRMED, scheduled_pickup_time=pickup_time)
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/assign/", {"driver_id": str(driver.id)})

    assert response.status_code == 200


def test_manual_assign_rejects_non_confirmed_trip(client, _auth):
    trip = TripFactory(status=TripStatus.REQUESTED)
    driver = DriverProfileFactory()
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/assign/", {"driver_id": str(driver.id)})

    assert response.status_code == 400


def test_rider_forbidden_from_assign(client, _auth):
    profile = RiderProfileFactory()
    trip = TripFactory(rider=profile, status=TripStatus.CONFIRMED)
    driver = DriverProfileFactory()
    _auth(client, profile.user)

    response = client.post(f"/api/trips/{trip.id}/assign/", {"driver_id": str(driver.id)})

    assert response.status_code == 403


def test_auto_assign_picks_driver_with_fewest_active_trips(client, _auth):
    trip = TripFactory(status=TripStatus.CONFIRMED)
    busy_driver = DriverProfileFactory()
    TripFactory(status=TripStatus.ASSIGNED, assigned_driver=busy_driver)
    free_driver = DriverProfileFactory()
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/auto-assign/")

    assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert trip.assigned_driver == free_driver


def test_auto_assign_tie_breaks_by_date_joined(client, _auth):
    trip = TripFactory(status=TripStatus.CONFIRMED)
    older_driver = DriverProfileFactory()
    newer_driver = DriverProfileFactory()
    newer_driver.user.date_joined = timezone.now() + timedelta(days=1)
    newer_driver.user.save(update_fields=["date_joined"])
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/auto-assign/")

    assert response.status_code == 200
    trip.refresh_from_db()
    assert trip.assigned_driver == older_driver


def test_auto_assign_returns_400_with_no_eligible_drivers(client, _auth):
    trip = TripFactory(status=TripStatus.CONFIRMED)
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/auto-assign/")

    assert response.status_code == 400


def test_auto_assign_excludes_unapproved_drivers(client, _auth):
    trip = TripFactory(status=TripStatus.CONFIRMED)
    DriverProfileFactory(is_approved=False)
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/auto-assign/")

    assert response.status_code == 400


def test_reassign_succeeds_before_acceptance(client, _auth):
    trip = TripFactory(status=TripStatus.ASSIGNED, assigned_driver=DriverProfileFactory())
    new_driver = DriverProfileFactory()
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/reassign/", {"driver_id": str(new_driver.id)})

    assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert trip.assigned_driver == new_driver


def test_reassign_rejected_after_acceptance(client, _auth):
    trip = TripFactory(
        status=TripStatus.ASSIGNED,
        assigned_driver=DriverProfileFactory(),
        accepted_at=timezone.now(),
    )
    new_driver = DriverProfileFactory()
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/reassign/", {"driver_id": str(new_driver.id)})

    assert response.status_code == 400
