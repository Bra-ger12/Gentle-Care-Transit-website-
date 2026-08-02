import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Role
from apps.accounts.tests.factories import DriverProfileFactory, RiderFactory
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory
from config.asgi import application


def _token(user):
    # Creating a RefreshToken writes an OutstandingToken row (blacklist app), so
    # this must run in a sync DB thread, never directly in an async test body.
    return str(RefreshToken.for_user(user).access_token)


@database_sync_to_async
def _rider_token():
    return _token(RiderFactory())


@database_sync_to_async
def _admin_token():
    return _token(RiderFactory(role=Role.ADMIN, is_staff=True))


@database_sync_to_async
def _assigned_trip():
    """Return (trip_id, rider_token, driver_token) as primitives so the async test
    body never touches the ORM directly."""
    driver = DriverProfileFactory()
    trip = TripFactory(status=TripStatus.EN_ROUTE, assigned_driver=driver)
    return str(trip.id), _token(trip.rider.user), _token(driver.user)


async def test_notification_socket_rejects_anonymous():
    communicator = WebsocketCommunicator(application, "/ws/notifications/")
    connected, _ = await communicator.connect()
    assert connected is False
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
async def test_notification_socket_accepts_authenticated():
    token = await _rider_token()
    communicator = WebsocketCommunicator(application, f"/ws/notifications/?token={token}")
    connected, _ = await communicator.connect()
    assert connected is True
    message = await communicator.receive_json_from()
    assert message["event"] == "unread_count"
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
async def test_tracking_rejects_unrelated_user():
    trip_id, _rider, _driver = await _assigned_trip()
    stranger = await _rider_token()
    communicator = WebsocketCommunicator(
        application, f"/ws/trips/{trip_id}/track/?token={stranger}"
    )
    connected, _ = await communicator.connect()
    assert connected is False
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
async def test_driver_location_is_relayed_to_rider():
    trip_id, rider_token, driver_token = await _assigned_trip()
    rider_comm = WebsocketCommunicator(
        application, f"/ws/trips/{trip_id}/track/?token={rider_token}"
    )
    driver_comm = WebsocketCommunicator(
        application, f"/ws/trips/{trip_id}/track/?token={driver_token}"
    )
    assert (await rider_comm.connect())[0] is True
    assert (await driver_comm.connect())[0] is True

    await driver_comm.send_json_to({"type": "location", "lat": 46.87, "lng": -96.78})

    message = await rider_comm.receive_json_from()
    assert message["event"] == "driver_location"
    assert message["lat"] == 46.87

    await rider_comm.disconnect()
    await driver_comm.disconnect()


@pytest.mark.django_db(transaction=True)
async def test_driver_location_is_relayed_to_admin():
    """The dispatch board's fleet map follows every in-flight trip's driver dot."""
    trip_id, _rider, driver_token = await _assigned_trip()
    admin_token = await _admin_token()
    admin_comm = WebsocketCommunicator(
        application, f"/ws/trips/{trip_id}/track/?token={admin_token}"
    )
    driver_comm = WebsocketCommunicator(
        application, f"/ws/trips/{trip_id}/track/?token={driver_token}"
    )
    assert (await admin_comm.connect())[0] is True
    assert (await driver_comm.connect())[0] is True

    await driver_comm.send_json_to({"type": "location", "lat": 46.81, "lng": -100.78})

    message = await admin_comm.receive_json_from()
    assert message == {"event": "driver_location", "lat": 46.81, "lng": -100.78}

    await admin_comm.disconnect()
    await driver_comm.disconnect()


@pytest.mark.django_db(transaction=True)
async def test_viewer_location_is_not_relayed():
    trip_id, rider_token, _driver = await _assigned_trip()
    admin_token = await _admin_token()
    rider_comm = WebsocketCommunicator(
        application, f"/ws/trips/{trip_id}/track/?token={rider_token}"
    )
    admin_comm = WebsocketCommunicator(
        application, f"/ws/trips/{trip_id}/track/?token={admin_token}"
    )
    assert (await rider_comm.connect())[0] is True
    assert (await admin_comm.connect())[0] is True

    # Rider is a viewer, not the assigned driver -- their "location" is ignored.
    await rider_comm.send_json_to({"type": "location", "lat": 1.0, "lng": 2.0})

    assert await admin_comm.receive_nothing(timeout=0.3) is True

    await rider_comm.disconnect()
    await admin_comm.disconnect()
