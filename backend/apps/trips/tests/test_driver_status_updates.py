from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import DriverProfileFactory, RiderFactory
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


def _admin():
    return RiderFactory(role=Role.ADMIN, is_staff=True)


def test_driver_blocked_from_en_route_before_accepting(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.ASSIGNED, assigned_driver=driver)
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{trip.id}/en-route/")

    assert response.status_code == 400
    trip.refresh_from_db()
    assert trip.status == TripStatus.ASSIGNED


def test_driver_can_mark_en_route_after_accepting(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(
        status=TripStatus.ASSIGNED, assigned_driver=driver, accepted_at=timezone.now()
    )
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{trip.id}/en-route/")

    assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert trip.status == TripStatus.EN_ROUTE
    assert trip.en_route_at is not None


def test_admin_can_mark_en_route_bypassing_accept_gate(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.ASSIGNED, assigned_driver=driver)
    _auth(client, _admin())

    response = client.post(f"/api/trips/{trip.id}/en-route/")

    assert response.status_code == 200
    trip.refresh_from_db()
    assert trip.status == TripStatus.EN_ROUTE


def test_driver_marks_arrived_before_picking_up(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.EN_ROUTE, assigned_driver=driver)
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{trip.id}/arrive/")

    assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert trip.status == TripStatus.ARRIVED
    assert trip.arrived_at is not None


def test_driver_can_mark_picked_up_from_arrived(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.ARRIVED, assigned_driver=driver, arrived_at=timezone.now())
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{trip.id}/picked-up/")

    assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert trip.status == TripStatus.PICKED_UP
    assert trip.picked_up_at is not None


def test_picked_up_straight_from_en_route_is_rejected(client, _auth):
    """The driver has to record arriving; the wait clock hangs off it."""
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.EN_ROUTE, assigned_driver=driver)
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{trip.id}/picked-up/")

    assert response.status_code == 400
    trip.refresh_from_db()
    assert trip.status == TripStatus.EN_ROUTE


def test_picked_up_directly_from_assigned_rejected(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(
        status=TripStatus.ASSIGNED, assigned_driver=driver, accepted_at=timezone.now()
    )
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{trip.id}/picked-up/")

    assert response.status_code == 400


def test_no_show_is_only_reachable_from_arrived(client, _auth):
    driver = DriverProfileFactory()
    waited = timezone.now() - timedelta(minutes=15)
    arrived_trip = TripFactory(status=TripStatus.ARRIVED, assigned_driver=driver, arrived_at=waited)
    picked_up_trip = TripFactory(status=TripStatus.PICKED_UP, assigned_driver=driver)
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{arrived_trip.id}/no-show/", {"reason": "not there"})
    assert response.status_code == 200, response.data
    arrived_trip.refresh_from_db()
    assert arrived_trip.status == TripStatus.NO_SHOW
    assert arrived_trip.no_show_reason == "not there"
    assert arrived_trip.no_show_waited_minutes == 15

    response = client.post(f"/api/trips/{picked_up_trip.id}/no-show/", {"reason": "x"})
    assert response.status_code == 400
    picked_up_trip.refresh_from_db()
    assert picked_up_trip.status == TripStatus.PICKED_UP


def test_no_show_before_the_wait_is_up_is_refused(client, _auth):
    """The wait is the substance of the claim -- two minutes is not a no-show."""
    driver = DriverProfileFactory()
    trip = TripFactory(
        status=TripStatus.ARRIVED,
        assigned_driver=driver,
        arrived_at=timezone.now() - timedelta(minutes=2),
    )
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{trip.id}/no-show/", {"reason": "nobody home"})

    assert response.status_code == 400
    assert "10 minutes" in str(response.data)
    trip.refresh_from_db()
    assert trip.status == TripStatus.ARRIVED


def test_no_show_needs_a_reason(client, _auth):
    driver = DriverProfileFactory()
    trip = TripFactory(
        status=TripStatus.ARRIVED,
        assigned_driver=driver,
        arrived_at=timezone.now() - timedelta(minutes=30),
    )
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{trip.id}/no-show/", {"reason": "  "})

    assert response.status_code == 400
    assert "reason" in response.data


def test_the_configured_wait_is_what_is_enforced(client, _auth, settings):
    from apps.operations.models import SystemSetting

    setting = SystemSetting.load()
    setting.no_show_wait_minutes = 20
    setting.save()

    driver = DriverProfileFactory()
    trip = TripFactory(
        status=TripStatus.ARRIVED,
        assigned_driver=driver,
        arrived_at=timezone.now() - timedelta(minutes=12),
    )
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{trip.id}/no-show/", {"reason": "nobody home"})

    assert response.status_code == 400
    assert "20 minutes" in str(response.data)


def test_driver_cannot_update_status_on_unrelated_trip(client, _auth):
    driver = DriverProfileFactory()
    other_driver = DriverProfileFactory()
    trip = TripFactory(
        status=TripStatus.ASSIGNED, assigned_driver=other_driver, accepted_at=timezone.now()
    )
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{trip.id}/en-route/")

    # get_queryset() scopes a driver to their own assigned trips, so an
    # unrelated trip 404s before the permission check is ever reached.
    assert response.status_code == 404
