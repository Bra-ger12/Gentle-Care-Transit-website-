import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import DriverProfileFactory, RiderFactory
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


def _admin():
    return RiderFactory(role=Role.ADMIN, is_staff=True)


def test_assigned_driver_can_accept(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.ASSIGNED, assigned_driver=driver)
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{trip.id}/accept/")

    assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert trip.status == TripStatus.ASSIGNED
    assert trip.accepted_at is not None


def test_double_accept_rejected(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(
        status=TripStatus.ASSIGNED, assigned_driver=driver, accepted_at=timezone.now()
    )
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{trip.id}/accept/")

    assert response.status_code == 400


def test_other_driver_forbidden_from_accept(client, _auth):
    driver = DriverProfileFactory()
    other_driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.ASSIGNED, assigned_driver=driver)
    _auth(client, other_driver.user)

    response = client.post(f"/api/trips/{trip.id}/accept/")

    # get_queryset() scopes a driver to their own assigned trips, so a trip
    # assigned to someone else 404s before the permission check is reached.
    assert response.status_code == 404


def test_admin_cannot_accept_on_drivers_behalf(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.ASSIGNED, assigned_driver=driver)
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/accept/")

    assert response.status_code == 403


def test_assigned_driver_can_decline(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.ASSIGNED, assigned_driver=driver)
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{trip.id}/decline/", {"reason": "car trouble"})

    assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert trip.status == TripStatus.CONFIRMED
    assert trip.assigned_driver is None
    assert trip.assigned_at is None
    assert trip.decline_reason == "car trouble"


def test_decline_after_accept_rejected(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(
        status=TripStatus.ASSIGNED, assigned_driver=driver, accepted_at=timezone.now()
    )
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{trip.id}/decline/")

    assert response.status_code == 400


def test_other_driver_cannot_decline(client, _auth):
    driver = DriverProfileFactory()
    other_driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.ASSIGNED, assigned_driver=driver)
    _auth(client, other_driver.user)

    response = client.post(f"/api/trips/{trip.id}/decline/")

    assert response.status_code == 404


def test_decline_reason_reaches_the_record_and_dispatch(client, _auth):
    """The driver's reason is how dispatch decides who to send instead, so it lands
    on the trip and in the admins' notification."""
    from apps.notifications.models import Notification

    admin = _admin()
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.ASSIGNED, assigned_driver=driver)
    _auth(client, driver.user)

    response = client.post(
        f"/api/trips/{trip.id}/decline/",
        {"reason": "Wheelchair lift is out of service."},
        format="json",
    )

    assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert trip.status == TripStatus.CONFIRMED
    assert trip.decline_reason == "Wheelchair lift is out of service."

    notification = Notification.objects.filter(recipient=admin, category="TRIP_DECLINED").first()
    assert notification is not None
    assert "Wheelchair lift is out of service." in notification.body


def test_decline_without_a_reason_still_notifies(client, _auth):
    from apps.notifications.models import Notification

    admin = _admin()
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.ASSIGNED, assigned_driver=driver)
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{trip.id}/decline/")

    assert response.status_code == 200, response.data
    notification = Notification.objects.filter(recipient=admin, category="TRIP_DECLINED").first()
    assert "No reason given" in notification.body


def test_queue_row_carries_the_decline_reason(client, _auth):
    """The dispatch board reads `decline_reason` off the list payload."""
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.ASSIGNED, assigned_driver=driver)
    _auth(client, driver.user)
    client.post(f"/api/trips/{trip.id}/decline/", {"reason": "Van in the shop."}, format="json")

    _auth(client, _admin())
    response = client.get("/api/trips/?status=CONFIRMED")

    assert response.status_code == 200, response.data
    assert response.data["results"][0]["decline_reason"] == "Van in the shop."
