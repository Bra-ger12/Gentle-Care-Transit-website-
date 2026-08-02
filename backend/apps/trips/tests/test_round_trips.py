"""Round trips, will-call returns, and escorts."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import AdminFactory, RiderProfileFactory
from apps.trips.models import Trip, TripStatus, TripType

pytestmark = pytest.mark.django_db

HOME = "1420 Boulevard Ave, Bismarck, ND"
CLINIC = "Sanford Health, 300 N 7th St, Bismarck, ND"


def _payload(**overrides):
    payload = {
        "scheduled_pickup_time": (timezone.now() + timedelta(days=3)).isoformat(),
        "pickup_address": HOME,
        "dropoff_address": CLINIC,
    }
    payload.update(overrides)
    return payload


def _book(client, **overrides):
    return client.post("/api/trips/", _payload(**overrides), format="json")


@pytest.fixture
def rider(client, _auth):
    profile = RiderProfileFactory()
    _auth(client, profile.user)
    return profile


def test_one_way_creates_a_single_trip(client, rider):
    assert _book(client).status_code == 201
    assert Trip.objects.count() == 1


def test_round_trip_creates_both_legs(client, rider):
    outbound_time = timezone.now() + timedelta(days=3)
    response = _book(
        client,
        scheduled_pickup_time=outbound_time.isoformat(),
        trip_type=TripType.ROUND_TRIP,
        return_pickup_time=(outbound_time + timedelta(hours=3)).isoformat(),
    )

    assert response.status_code == 201, response.data
    assert Trip.objects.count() == 2

    outbound = Trip.objects.get(id=response.data["id"])
    leg = outbound.return_trip
    assert leg.outbound_trip == outbound
    assert leg.trip_type == TripType.ROUND_TRIP
    assert leg.is_will_call is False


def test_the_return_leg_runs_the_route_backwards(client, rider):
    outbound_time = timezone.now() + timedelta(days=3)
    response = _book(
        client,
        scheduled_pickup_time=outbound_time.isoformat(),
        trip_type=TripType.ROUND_TRIP,
        return_pickup_time=(outbound_time + timedelta(hours=3)).isoformat(),
    )
    outbound = Trip.objects.get(id=response.data["id"])
    leg = outbound.return_trip

    assert leg.pickup_address == outbound.dropoff_address
    assert leg.dropoff_address == outbound.pickup_address
    assert leg.pickup_lat == outbound.dropoff_lat
    # Same two points, so the same distance -- not re-geocoded.
    assert leg.mileage == outbound.mileage


def test_will_call_return_is_pencilled_in_and_flagged(client, rider):
    response = _book(client, trip_type=TripType.ROUND_TRIP, return_is_will_call=True)

    assert response.status_code == 201, response.data
    leg = Trip.objects.get(id=response.data["id"]).return_trip
    assert leg.is_will_call is True
    assert leg.will_call_requested_at is None
    # A placeholder after the outbound, so it still shows on the schedule.
    assert leg.scheduled_pickup_time > leg.outbound_trip.scheduled_pickup_time


def test_a_round_trip_needs_a_return_time_or_will_call(client, rider):
    response = _book(client, trip_type=TripType.ROUND_TRIP)

    assert response.status_code == 400
    assert "return_pickup_time" in response.data
    assert Trip.objects.count() == 0


def test_a_return_time_and_will_call_together_are_rejected(client, rider):
    outbound_time = timezone.now() + timedelta(days=3)
    response = _book(
        client,
        scheduled_pickup_time=outbound_time.isoformat(),
        trip_type=TripType.ROUND_TRIP,
        return_pickup_time=(outbound_time + timedelta(hours=2)).isoformat(),
        return_is_will_call=True,
    )
    assert response.status_code == 400
    assert Trip.objects.count() == 0


def test_a_return_before_the_outbound_is_rejected(client, rider):
    outbound_time = timezone.now() + timedelta(days=3)
    response = _book(
        client,
        scheduled_pickup_time=outbound_time.isoformat(),
        trip_type=TripType.ROUND_TRIP,
        return_pickup_time=(outbound_time - timedelta(hours=1)).isoformat(),
    )
    assert response.status_code == 400
    assert "return_pickup_time" in response.data


def test_return_details_on_a_one_way_are_rejected(client, rider):
    response = _book(client, return_is_will_call=True)
    assert response.status_code == 400
    assert "trip_type" in response.data


def test_rider_can_call_for_their_will_call_return(client, rider):
    booked = _book(client, trip_type=TripType.ROUND_TRIP, return_is_will_call=True)
    leg = Trip.objects.get(id=booked.data["id"]).return_trip

    response = client.post(f"/api/trips/{leg.id}/request-return/", {}, format="json")

    assert response.status_code == 200, response.data
    leg.refresh_from_db()
    assert leg.will_call_requested_at is not None
    # Rescheduled to "soon", not left at the placeholder.
    assert leg.scheduled_pickup_time < timezone.now() + timedelta(hours=2)


def test_calling_twice_is_refused(client, rider):
    booked = _book(client, trip_type=TripType.ROUND_TRIP, return_is_will_call=True)
    leg = Trip.objects.get(id=booked.data["id"]).return_trip

    assert client.post(f"/api/trips/{leg.id}/request-return/", {}).status_code == 200
    assert client.post(f"/api/trips/{leg.id}/request-return/", {}).status_code == 400


def test_a_scheduled_return_cannot_be_called_early(client, rider):
    outbound_time = timezone.now() + timedelta(days=3)
    booked = _book(
        client,
        scheduled_pickup_time=outbound_time.isoformat(),
        trip_type=TripType.ROUND_TRIP,
        return_pickup_time=(outbound_time + timedelta(hours=3)).isoformat(),
    )
    leg = Trip.objects.get(id=booked.data["id"]).return_trip

    response = client.post(f"/api/trips/{leg.id}/request-return/", {})
    assert response.status_code == 400
    assert "will-call" in str(response.data)


def test_another_rider_cannot_call_for_someone_elses_return(client, _auth, rider):
    booked = _book(client, trip_type=TripType.ROUND_TRIP, return_is_will_call=True)
    leg = Trip.objects.get(id=booked.data["id"]).return_trip

    intruder = RiderProfileFactory()
    _auth(client, intruder.user)

    response = client.post(f"/api/trips/{leg.id}/request-return/", {})
    assert response.status_code == 404


def test_will_call_notifies_dispatch(client, _auth, rider):
    from apps.notifications.models import Notification, NotificationCategory

    admin = AdminFactory()
    booked = _book(client, trip_type=TripType.ROUND_TRIP, return_is_will_call=True)
    leg = Trip.objects.get(id=booked.data["id"]).return_trip

    client.post(f"/api/trips/{leg.id}/request-return/", {})

    assert Notification.objects.filter(
        recipient=admin, category=NotificationCategory.WILL_CALL
    ).exists()


# --- escorts -------------------------------------------------------------


def test_escorts_are_recorded(client, rider):
    response = _book(client, escort_count=2)
    assert response.status_code == 201, response.data
    assert Trip.objects.get().escort_count == 2


def test_escorts_default_to_none(client, rider):
    _book(client)
    assert Trip.objects.get().escort_count == 0


def test_an_implausible_escort_count_is_rejected(client, rider):
    response = _book(client, escort_count=9)
    assert response.status_code == 400
    assert "escort_count" in response.data


def test_escorts_carry_to_the_return_leg(client, rider):
    booked = _book(client, trip_type=TripType.ROUND_TRIP, return_is_will_call=True, escort_count=1)
    leg = Trip.objects.get(id=booked.data["id"]).return_trip
    assert leg.escort_count == 1


def test_cancelling_the_outbound_leaves_the_return_visible(client, rider):
    """Legs are independent records; cancelling one must not silently drop the other."""
    booked = _book(client, trip_type=TripType.ROUND_TRIP, return_is_will_call=True)
    outbound = Trip.objects.get(id=booked.data["id"])

    client.post(f"/api/trips/{outbound.id}/cancel/", {"reason": "clinic moved it"})

    outbound.refresh_from_db()
    assert outbound.status == TripStatus.CANCELLED
    assert Trip.objects.filter(outbound_trip=outbound).exists()
