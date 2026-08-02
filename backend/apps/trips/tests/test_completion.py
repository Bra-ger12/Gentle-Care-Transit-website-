import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import DriverProfileFactory, RiderFactory
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


def _admin():
    return RiderFactory(role=Role.ADMIN, is_staff=True)


def _valid_payload():
    return {"odometer_start": 1000, "odometer_end": 1010, "completion_attestation": "Jane Doe"}


def test_complete_rejected_with_missing_odometer_fields(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.PICKED_UP, assigned_driver=driver)
    _auth(client, driver.user)

    response = client.post(
        f"/api/trips/{trip.id}/complete/", {"completion_attestation": "Jane Doe"}
    )
    assert response.status_code == 400

    response = client.post(
        f"/api/trips/{trip.id}/complete/",
        {"odometer_start": 1000, "completion_attestation": "Jane Doe"},
    )
    assert response.status_code == 400


def test_complete_rejected_when_odometer_end_less_than_start(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.PICKED_UP, assigned_driver=driver)
    _auth(client, driver.user)

    response = client.post(
        f"/api/trips/{trip.id}/complete/",
        {"odometer_start": 1010, "odometer_end": 1000, "completion_attestation": "Jane Doe"},
    )

    assert response.status_code == 400


def test_complete_rejected_with_blank_attestation(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.PICKED_UP, assigned_driver=driver)
    _auth(client, driver.user)

    response = client.post(
        f"/api/trips/{trip.id}/complete/",
        {"odometer_start": 1000, "odometer_end": 1010, "completion_attestation": ""},
    )

    assert response.status_code == 400


def test_complete_succeeds_with_valid_payload(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.PICKED_UP, assigned_driver=driver)
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{trip.id}/complete/", _valid_payload())

    assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert trip.status == TripStatus.COMPLETED
    assert trip.odometer_start == 1000
    assert trip.odometer_end == 1010
    assert trip.completion_attestation == "Jane Doe"
    assert trip.completed_at is not None


def test_complete_only_reachable_from_picked_up(client, _auth):
    driver = DriverProfileFactory()
    assigned_trip = TripFactory(
        status=TripStatus.ASSIGNED, assigned_driver=driver, accepted_at=timezone.now()
    )
    en_route_trip = TripFactory(status=TripStatus.EN_ROUTE, assigned_driver=driver)
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{assigned_trip.id}/complete/", _valid_payload())
    assert response.status_code == 400

    response = client.post(f"/api/trips/{en_route_trip.id}/complete/", _valid_payload())
    assert response.status_code == 400


def test_admin_can_complete_on_drivers_behalf(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.PICKED_UP, assigned_driver=driver)
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/complete/", _valid_payload())

    assert response.status_code == 200
    trip.refresh_from_db()
    assert trip.status == TripStatus.COMPLETED
