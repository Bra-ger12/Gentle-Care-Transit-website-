from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import DriverFactory, RiderProfileFactory
from apps.trips.models import Trip, TripStatus
from apps.trips.services.maps import RouteResolution

pytestmark = pytest.mark.django_db

ROUTE_RESULT = RouteResolution(
    pickup_lat=Decimal("46.877186"),
    pickup_lng=Decimal("-96.789803"),
    dropoff_lat=Decimal("46.873800"),
    dropoff_lng=Decimal("-96.767800"),
    miles=Decimal("3.20"),
    duration_minutes=12,
    estimated=False,
)


def _payload(**overrides):
    payload = {
        "scheduled_pickup_time": (timezone.now() + timedelta(days=3)).isoformat(),
        "pickup_address": "123 Main St, Fargo, ND",
        "dropoff_address": "456 Broadway, Fargo, ND",
        "mobility_need": "",
        "notes": "",
    }
    payload.update(overrides)
    return payload


@patch("apps.trips.serializers.resolve_route", return_value=ROUTE_RESULT)
def test_rider_can_book_a_trip(mock_route, client, _auth):
    profile = RiderProfileFactory()
    _auth(client, profile.user)

    response = client.post("/api/trips/", _payload(), format="json")

    assert response.status_code == 201, response.data
    assert response.data["status"] == TripStatus.REQUESTED
    assert response.data["mileage"] == "3.20"
    assert response.data["distance_estimated"] is False
    mock_route.assert_called_once()

    trip = Trip.objects.get(id=response.data["id"])
    assert trip.rider == profile
    assert trip.created_by == profile.user


@patch("apps.trips.serializers.resolve_route")
def test_geocoding_failure_returns_400(mock_route, client, _auth):
    from apps.trips.services.maps import GeocodingError

    mock_route.side_effect = GeocodingError("Could not geocode address")
    profile = RiderProfileFactory()
    _auth(client, profile.user)

    response = client.post("/api/trips/", _payload(), format="json")

    assert response.status_code == 400
    assert Trip.objects.count() == 0


@patch("apps.trips.serializers.resolve_route", return_value=ROUTE_RESULT)
def test_driver_cannot_book_a_trip(mock_route, client, _auth):
    driver = DriverFactory()
    _auth(client, driver)

    response = client.post("/api/trips/", _payload(), format="json")

    assert response.status_code == 403


def test_unauthenticated_cannot_book_a_trip(client):
    response = client.post("/api/trips/", _payload(), format="json")
    assert response.status_code == 401


@patch("apps.trips.serializers.resolve_route", return_value=ROUTE_RESULT)
def test_booking_a_past_pickup_time_is_rejected(mock_route, client, _auth):
    profile = RiderProfileFactory()
    _auth(client, profile.user)

    payload = _payload(scheduled_pickup_time=(timezone.now() - timedelta(days=1)).isoformat())
    response = client.post("/api/trips/", payload, format="json")

    assert response.status_code == 400
