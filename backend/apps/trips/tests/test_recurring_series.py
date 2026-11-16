from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import AdminFactory, RiderProfileFactory
from apps.trips.models import RecurringTripSeries, Trip, Weekday
from apps.trips.services.maps import RouteResolution
from apps.trips.tasks import generate_recurring_trips
from apps.trips.tests.factories import RecurringTripSeriesFactory, ServiceFactory

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


@patch("apps.trips.serializers.resolve_route", return_value=ROUTE_RESULT)
def test_creating_a_series_triggers_initial_generation(mock_route, client, _auth):
    profile = RiderProfileFactory()
    _auth(client, profile.user)

    today = timezone.localdate()
    service = ServiceFactory()
    payload = {
        "pickup_address": "123 Main St, Fargo, ND",
        "dropoff_address": "456 Broadway, Fargo, ND",
        "service_id": str(service.id),
        "pickup_time": "09:00:00",
        "weekdays": [today.weekday()],
        "start_date": today.isoformat(),
        "end_date": (today + timedelta(days=13)).isoformat(),
        "mobility_need": "",
        "notes": "",
    }

    response = client.post("/api/trips/recurring-series/", payload, format="json")

    assert response.status_code == 201, response.data
    mock_route.assert_called_once()

    series = RecurringTripSeries.objects.get(id=response.data["id"])
    assert Trip.objects.filter(recurring_series=series).exists()


@patch("apps.trips.serializers.resolve_route", return_value=ROUTE_RESULT)
def test_admin_can_create_recurring_series_for_rider(mock_route, client, _auth):
    # FIX #3: dispatch admins can create recurring rides for a patient by phone.
    admin = AdminFactory()
    profile = RiderProfileFactory()
    _auth(client, admin)

    today = timezone.localdate()
    service = ServiceFactory()
    payload = {
        "rider_id": profile.id,
        "pickup_address": "123 Main St, Fargo, ND",
        "dropoff_address": "456 Broadway, Fargo, ND",
        "service_id": str(service.id),
        "pickup_time": "09:00:00",
        "weekdays": [today.weekday()],
        "start_date": today.isoformat(),
        "end_date": (today + timedelta(days=13)).isoformat(),
        "mobility_need": "",
        "notes": "",
    }

    response = client.post("/api/trips/recurring-series/", payload, format="json")

    assert response.status_code == 201, response.data
    series = RecurringTripSeries.objects.get(id=response.data["id"])
    assert series.rider == profile
    mock_route.assert_called_once()


@patch("apps.trips.serializers.resolve_route", return_value=ROUTE_RESULT)
def test_rider_cannot_create_recurring_series_for_another_rider(mock_route, client, _auth):
    # FIX #3: rider_id is only honored for admins.
    profile = RiderProfileFactory()
    other = RiderProfileFactory()
    _auth(client, profile.user)

    today = timezone.localdate()
    service = ServiceFactory()
    payload = {
        "rider_id": other.id,
        "pickup_address": "123 Main St, Fargo, ND",
        "dropoff_address": "456 Broadway, Fargo, ND",
        "service_id": str(service.id),
        "pickup_time": "09:00:00",
        "weekdays": [today.weekday()],
        "start_date": today.isoformat(),
        "end_date": (today + timedelta(days=13)).isoformat(),
        "mobility_need": "",
        "notes": "",
    }

    response = client.post("/api/trips/recurring-series/", payload, format="json")

    assert response.status_code == 400
    assert not RecurringTripSeries.objects.filter(rider=other).exists()


def test_generate_recurring_trips_produces_correct_dates():
    start = timezone.localdate()
    series = RecurringTripSeriesFactory(
        start_date=start,
        end_date=start + timedelta(days=13),
        weekdays=[Weekday.MONDAY],
    )

    created = generate_recurring_trips.run(series_id=str(series.id), window_days=14)

    expected_dates = {
        d for d in (start + timedelta(days=n) for n in range(14)) if d.weekday() == Weekday.MONDAY
    }
    trips = Trip.objects.filter(recurring_series=series)
    assert trips.count() == len(expected_dates)
    assert created == len(expected_dates)
    assert {t.scheduled_pickup_time.date() for t in trips} == expected_dates


def test_generate_recurring_trips_is_idempotent():
    series = RecurringTripSeriesFactory()

    first = generate_recurring_trips.run(series_id=str(series.id), window_days=14)
    second = generate_recurring_trips.run(series_id=str(series.id), window_days=14)

    assert first > 0
    assert second == 0


def test_inactive_series_are_skipped():
    series = RecurringTripSeriesFactory(is_active=False)

    created = generate_recurring_trips.run(series_id=str(series.id), window_days=14)

    assert created == 0
    assert not Trip.objects.filter(recurring_series=series).exists()


@patch("apps.trips.serializers.resolve_route")
def test_generated_trips_never_call_the_maps_service(mock_route):
    series = RecurringTripSeriesFactory()

    created = generate_recurring_trips.run(series_id=str(series.id), window_days=14)

    assert created > 0
    mock_route.assert_not_called()


def test_rider_can_list_and_deactivate_their_own_series(client, _auth):
    """Backs the rider's "Recurring rides" page: see your series, stop new bookings."""
    profile = RiderProfileFactory()
    series = RecurringTripSeriesFactory(rider=profile)
    _auth(client, profile.user)

    listed = client.get("/api/trips/recurring-series/")
    assert listed.status_code == 200, listed.data
    assert [s["id"] for s in listed.data["results"]] == [str(series.id)]

    response = client.post(f"/api/trips/recurring-series/{series.id}/deactivate/")

    assert response.status_code == 200, response.data
    assert response.data["is_active"] is False
    series.refresh_from_db()
    assert series.is_active is False


def test_deactivating_stops_further_generation(client, _auth):
    start = timezone.localdate()
    series = RecurringTripSeriesFactory(start_date=start, weekdays=[d.weekday() for d in (start,)])
    _auth(client, series.rider.user)

    client.post(f"/api/trips/recurring-series/{series.id}/deactivate/")
    Trip.objects.filter(recurring_series=series).delete()
    generate_recurring_trips(series_id=str(series.id))

    assert Trip.objects.filter(recurring_series=series).count() == 0


def test_rider_cannot_see_or_deactivate_another_riders_series(client, _auth):
    series = RecurringTripSeriesFactory()
    other = RiderProfileFactory()
    _auth(client, other.user)

    listed = client.get("/api/trips/recurring-series/")
    assert listed.data["count"] == 0

    response = client.post(f"/api/trips/recurring-series/{series.id}/deactivate/")

    assert response.status_code == 404
    series.refresh_from_db()
    assert series.is_active is True
