"""Booking survives an unavailable Google Maps.

The system must run with no API key at all, and must not stop taking bookings
when a configured key stops working (billing lapsed, quota exhausted, outage).
Both cases fall back to the offline gazetteer + haversine estimate, and the
resulting trip is flagged `distance_estimated=True` so nobody mistakes a
computed mileage for a measured one.

Set `MAPS_OFFLINE_FALLBACK=False` to opt out and get the old hard failure.
"""

from decimal import Decimal
from unittest.mock import patch

import googlemaps.exceptions
import pytest

from apps.accounts.tests.factories import RiderProfileFactory
from apps.trips.models import Trip
from apps.trips.services.maps import GeocodingError, geocode_address, resolve_route
from apps.trips.tests.factories import ServiceFactory

ADDRESS = "1420 Boulevard Ave, Bismarck, ND"
DESTINATION = "Sanford Health, 300 N 7th St, Fargo, ND"

UPSTREAM_FAILURES = [
    googlemaps.exceptions.ApiError(
        "REQUEST_DENIED", "You must enable Billing on the Google Cloud Project"
    ),
    googlemaps.exceptions.Timeout(),
    googlemaps.exceptions.TransportError("connection reset"),
    googlemaps.exceptions.HTTPError(503),
]


@pytest.mark.parametrize("failure", UPSTREAM_FAILURES, ids=lambda f: type(f).__name__)
def test_upstream_failure_falls_back_to_the_offline_estimate(failure, settings):
    settings.GOOGLE_MAPS_API_KEY = "test-key"
    with patch("apps.trips.services.maps.googlemaps.Client") as client:
        client.return_value.geocode.side_effect = failure
        lat, lng = geocode_address(ADDRESS)

    # Bismarck, within the gazetteer's per-address offset.
    assert Decimal("46.7") < lat < Decimal("46.9")
    assert Decimal("-100.9") < lng < Decimal("-100.6")


@pytest.mark.parametrize("failure", UPSTREAM_FAILURES, ids=lambda f: type(f).__name__)
def test_upstream_failure_still_raises_when_fallback_is_disabled(failure, settings):
    settings.GOOGLE_MAPS_API_KEY = "test-key"
    settings.MAPS_OFFLINE_FALLBACK = False
    with patch("apps.trips.services.maps.googlemaps.Client") as client:
        client.return_value.geocode.side_effect = failure
        with pytest.raises(GeocodingError):
            geocode_address(ADDRESS)


def test_missing_key_uses_the_offline_estimate(settings):
    settings.GOOGLE_MAPS_API_KEY = ""
    lat, lng = geocode_address(ADDRESS)
    assert Decimal("46.7") < lat < Decimal("46.9")


def test_missing_key_raises_when_fallback_is_disabled(settings):
    settings.GOOGLE_MAPS_API_KEY = ""
    settings.MAPS_OFFLINE_FALLBACK = False
    with pytest.raises(GeocodingError):
        geocode_address(ADDRESS)


def test_unknown_town_is_still_an_error(settings):
    """The fallback is not a rubber stamp -- an address it can't place fails."""
    settings.GOOGLE_MAPS_API_KEY = ""
    with pytest.raises(GeocodingError):
        geocode_address("14 Rue de Rivoli, Paris")


def test_resolve_route_marks_google_results_as_measured(settings):
    settings.GOOGLE_MAPS_API_KEY = "test-key"
    with (
        patch("apps.trips.services.maps.googlemaps.Client") as client,
        patch("apps.trips.services.maps.requests.post") as post,
    ):
        client.return_value.geocode.return_value = [
            {"geometry": {"location": {"lat": 46.8083, "lng": -100.7837}}}
        ]
        post.return_value.status_code = 200
        post.return_value.json.return_value = {
            "routes": [{"distanceMeters": 16093, "duration": "900s"}]
        }
        route = resolve_route(ADDRESS, DESTINATION)

    assert route.estimated is False
    assert route.miles == Decimal("10.00")
    assert route.duration_minutes == 15


def test_resolve_route_bismarck_to_fargo_is_roughly_right(settings):
    """~193 road miles by US-94. The estimate should be in the same country."""
    settings.GOOGLE_MAPS_API_KEY = ""
    route = resolve_route(ADDRESS, DESTINATION)

    assert route.estimated is True
    assert Decimal("150") < route.miles < Decimal("240")
    assert 150 < route.duration_minutes < 300


@pytest.mark.django_db
def test_booking_succeeds_with_no_maps_key(client, _auth, settings):
    """The end-to-end shape of a fresh checkout with no API key."""
    settings.GOOGLE_MAPS_API_KEY = ""
    profile = RiderProfileFactory()
    service = ServiceFactory()
    _auth(client, profile.user)

    response = client.post(
        "/api/trips/",
        {
            "scheduled_pickup_time": "2026-12-01T09:00:00Z",
            "pickup_address": ADDRESS,
            "dropoff_address": "Sanford Health, 300 N 7th St, Bismarck, ND",
            "service_id": str(service.id),
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    trip = Trip.objects.get()
    assert trip.distance_estimated is True
    assert trip.mileage > 0
    assert response.data["distance_estimated"] is True


@pytest.mark.django_db
def test_booking_rejects_an_unplaceable_address(client, _auth, settings):
    settings.GOOGLE_MAPS_API_KEY = ""
    profile = RiderProfileFactory()
    service = ServiceFactory()
    _auth(client, profile.user)

    response = client.post(
        "/api/trips/",
        {
            "scheduled_pickup_time": "2026-12-01T09:00:00Z",
            "pickup_address": "somewhere over there",
            "dropoff_address": "Sanford Health, 300 N 7th St, Bismarck, ND",
            "service_id": str(service.id),
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    assert Trip.objects.count() == 0


@pytest.mark.django_db
def test_booking_rejects_identical_pickup_and_dropoff(client, _auth, settings):
    settings.GOOGLE_MAPS_API_KEY = ""
    profile = RiderProfileFactory()
    service = ServiceFactory()
    _auth(client, profile.user)

    response = client.post(
        "/api/trips/",
        {
            "scheduled_pickup_time": "2026-12-01T09:00:00Z",
            "pickup_address": ADDRESS,
            "dropoff_address": "1420 Boulevard Ave., Bismarck ND",
            "service_id": str(service.id),
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "dropoff_address" in response.data
    assert Trip.objects.count() == 0
