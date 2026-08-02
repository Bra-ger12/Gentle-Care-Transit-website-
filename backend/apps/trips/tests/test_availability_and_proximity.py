"""The driver calendar, position reporting, and nearest-driver ranking."""

from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import DriverAvailability, DriverLocation, DriverTimeOff, VehicleType
from apps.accounts.tests.factories import (
    AdminFactory,
    DriverProfileFactory,
    RiderProfileFactory,
)
from apps.trips.models import TripStatus
from apps.trips.services.assignment import (
    distance_to_pickup,
    eligible_drivers,
    find_available_driver,
    rank_drivers,
)
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db

# Bismarck; the factory's trips sit near here.
PICKUP = (Decimal("46.808300"), Decimal("-100.783700"))


def trip_at(local_dt, **overrides):
    fields = {
        "status": TripStatus.CONFIRMED,
        "scheduled_pickup_time": local_dt,
        "pickup_lat": PICKUP[0],
        "pickup_lng": PICKUP[1],
    }
    fields.update(overrides)
    return TripFactory(**fields)


def next_weekday(weekday, at=time(10, 0)):
    """The next occurrence of this weekday at this local time."""
    today = timezone.localdate()
    ahead = (weekday - today.weekday()) % 7 or 7
    return timezone.make_aware(
        timezone.datetime.combine(today + timedelta(days=ahead), at)
    )


def place(driver, lat, lng, minutes_ago=0):
    return DriverLocation.objects.create(
        driver=driver,
        lat=Decimal(str(lat)),
        lng=Decimal(str(lng)),
        reported_at=timezone.now() - timedelta(minutes=minutes_ago),
    )


# --- shift calendar ------------------------------------------------------


def test_a_driver_with_no_calendar_is_always_available():
    """Every driver predates the calendar; an empty one means "not configured"."""
    driver = DriverProfileFactory()
    trip = trip_at(next_weekday(2))
    assert driver in eligible_drivers(trip)


def test_a_driver_on_shift_is_eligible():
    driver = DriverProfileFactory()
    when = next_weekday(2, time(10, 0))
    DriverAvailability.objects.create(
        driver=driver, weekday=2, start_time=time(7, 0), end_time=time(15, 30)
    )
    assert driver in eligible_drivers(trip_at(when))


def test_a_driver_off_shift_is_not_eligible():
    driver = DriverProfileFactory()
    when = next_weekday(2, time(19, 0))
    DriverAvailability.objects.create(
        driver=driver, weekday=2, start_time=time(7, 0), end_time=time(15, 30)
    )
    assert driver not in eligible_drivers(trip_at(when))


def test_a_shift_on_another_weekday_does_not_help():
    driver = DriverProfileFactory()
    DriverAvailability.objects.create(
        driver=driver, weekday=0, start_time=time(0, 1), end_time=time(23, 59)
    )
    assert driver not in eligible_drivers(trip_at(next_weekday(3)))


def test_time_off_beats_the_usual_shift():
    driver = DriverProfileFactory()
    when = next_weekday(2, time(10, 0))
    DriverAvailability.objects.create(
        driver=driver, weekday=2, start_time=time(0, 1), end_time=time(23, 59)
    )
    DriverTimeOff.objects.create(
        driver=driver,
        start_date=when.date() - timedelta(days=1),
        end_date=when.date() + timedelta(days=1),
        reason="Annual leave",
    )
    assert driver not in eligible_drivers(trip_at(when))


def test_time_off_is_inclusive_of_both_end_dates():
    """"Off Monday to Friday" means Friday too."""
    driver = DriverProfileFactory()
    when = next_weekday(2, time(10, 0))
    DriverTimeOff.objects.create(
        driver=driver, start_date=when.date(), end_date=when.date()
    )
    assert driver not in eligible_drivers(trip_at(when))


def test_a_driver_returns_after_their_time_off_ends():
    driver = DriverProfileFactory()
    when = next_weekday(2, time(10, 0))
    DriverTimeOff.objects.create(
        driver=driver,
        start_date=when.date() - timedelta(days=5),
        end_date=when.date() - timedelta(days=1),
    )
    assert driver in eligible_drivers(trip_at(when))


def test_driver_manages_their_own_shifts_over_the_api(client, _auth):
    driver = DriverProfileFactory()
    _auth(client, driver.user)

    created = client.post(
        "/api/auth/availability/",
        {"weekday": 1, "start_time": "07:00", "end_time": "15:30"},
        format="json",
    )
    assert created.status_code == 201, created.data

    listed = client.get("/api/auth/availability/")
    assert [row["weekday"] for row in listed.data["results"]] == [1]

    deleted = client.delete(f"/api/auth/availability/{created.data['id']}/")
    assert deleted.status_code == 204


def test_a_backwards_shift_is_rejected(client, _auth):
    driver = DriverProfileFactory()
    _auth(client, driver.user)
    response = client.post(
        "/api/auth/availability/",
        {"weekday": 1, "start_time": "15:00", "end_time": "07:00"},
        format="json",
    )
    assert response.status_code == 400
    assert "end_time" in response.data


def test_a_driver_never_sees_another_drivers_calendar(client, _auth):
    other = DriverProfileFactory()
    DriverAvailability.objects.create(
        driver=other, weekday=1, start_time=time(7, 0), end_time=time(15, 0)
    )
    _auth(client, DriverProfileFactory().user)

    assert client.get("/api/auth/availability/").data["results"] == []


def test_riders_have_no_calendar(client, _auth):
    _auth(client, RiderProfileFactory().user)
    assert client.get("/api/auth/availability/").status_code == 403


def test_backwards_time_off_is_rejected(client, _auth):
    _auth(client, DriverProfileFactory().user)
    today = timezone.localdate()
    response = client.post(
        "/api/auth/time-off/",
        {"start_date": today.isoformat(), "end_date": (today - timedelta(days=1)).isoformat()},
        format="json",
    )
    assert response.status_code == 400


# --- position reporting --------------------------------------------------


def test_a_driver_reports_their_position(client, _auth):
    driver = DriverProfileFactory()
    _auth(client, driver.user)

    response = client.post(
        "/api/auth/me/location/", {"lat": "46.8083", "lng": "-100.7837"}, format="json"
    )

    assert response.status_code == 204
    assert DriverLocation.objects.get(driver=driver).lat == Decimal("46.808300")


def test_reporting_again_overwrites_rather_than_appends(client, _auth):
    """One row per driver: dispatch needs where they are, not where they've been."""
    driver = DriverProfileFactory()
    _auth(client, driver.user)

    client.post("/api/auth/me/location/", {"lat": "46.80", "lng": "-100.78"}, format="json")
    client.post("/api/auth/me/location/", {"lat": "46.90", "lng": "-100.70"}, format="json")

    assert DriverLocation.objects.count() == 1
    assert DriverLocation.objects.get(driver=driver).lat == Decimal("46.900000")


def test_an_out_of_range_position_is_rejected(client, _auth):
    _auth(client, DriverProfileFactory().user)
    response = client.post(
        "/api/auth/me/location/", {"lat": "999", "lng": "-100.78"}, format="json"
    )
    assert response.status_code == 400


def test_a_rider_cannot_report_a_driver_position(client, _auth):
    _auth(client, RiderProfileFactory().user)
    response = client.post(
        "/api/auth/me/location/", {"lat": "46.80", "lng": "-100.78"}, format="json"
    )
    assert response.status_code == 403


# --- proximity -----------------------------------------------------------


def test_distance_is_none_without_a_position():
    assert distance_to_pickup(DriverProfileFactory(), trip_at(next_weekday(2))) is None


def test_distance_is_none_when_the_position_is_stale():
    """A fix from an hour ago says nothing about where someone is now."""
    driver = DriverProfileFactory()
    place(driver, 46.81, -100.78, minutes_ago=90)
    driver.refresh_from_db()
    assert distance_to_pickup(driver, trip_at(next_weekday(2))) is None


def test_distance_is_measured_from_a_fresh_position():
    driver = DriverProfileFactory()
    place(driver, 46.8083, -100.7837)
    driver.refresh_from_db()
    miles = distance_to_pickup(driver, trip_at(next_weekday(2)))
    assert miles is not None
    assert miles < Decimal("0.5")


def test_the_nearest_driver_ranks_first():
    trip = trip_at(next_weekday(2))
    near = DriverProfileFactory(vehicle_type=VehicleType.SEDAN)
    far = DriverProfileFactory(vehicle_type=VehicleType.SEDAN)
    place(near, 46.81, -100.78)
    place(far, 46.8772, -96.7898)  # Fargo

    ranked = rank_drivers(trip)

    assert ranked[0]["driver"] == near
    assert ranked[0]["miles_away"] < ranked[1]["miles_away"]


def test_a_driver_without_a_position_ranks_after_those_we_can_locate():
    """Unknown is not the same as far -- but it can't earn a preference either."""
    trip = trip_at(next_weekday(2))
    located = DriverProfileFactory()
    unlocated = DriverProfileFactory()
    place(located, 46.81, -100.78)

    ranked = rank_drivers(trip)

    assert ranked[0]["driver"] == located
    assert ranked[1]["driver"] == unlocated
    assert ranked[1]["miles_away"] is None


def test_auto_assign_picks_the_nearest_on_duty_driver():
    trip = trip_at(next_weekday(2))
    near_offline = DriverProfileFactory(is_available=False)
    far_online = DriverProfileFactory(is_available=True)
    place(near_offline, 46.81, -100.78)
    place(far_online, 46.8772, -96.7898)

    assert find_available_driver(trip) == far_online


def test_the_suggestions_endpoint_ranks_for_dispatch(client, _auth):
    trip = trip_at(next_weekday(2))
    near = DriverProfileFactory()
    far = DriverProfileFactory()
    place(near, 46.81, -100.78)
    place(far, 46.8772, -96.7898)
    _auth(client, AdminFactory())

    response = client.get(f"/api/trips/{trip.id}/driver-suggestions/")

    assert response.status_code == 200, response.data
    assert response.data[0]["driver_id"] == near.id
    assert response.data[0]["miles_away"] < response.data[1]["miles_away"]


def test_only_admins_get_suggestions(client, _auth):
    trip = trip_at(next_weekday(2))
    _auth(client, RiderProfileFactory().user)
    assert client.get(f"/api/trips/{trip.id}/driver-suggestions/").status_code in (403, 404)


# --- seats ---------------------------------------------------------------


def test_a_van_too_small_for_the_escorts_is_not_eligible():
    trip = trip_at(next_weekday(2), escort_count=3)
    small = DriverProfileFactory(vehicle_capacity=2)
    big = DriverProfileFactory(vehicle_capacity=6)

    eligible = eligible_drivers(trip)

    assert small not in eligible
    assert big in eligible


def test_an_unrecorded_capacity_does_not_exclude_a_driver():
    """A missing seat count is a missing record, not a small vehicle."""
    trip = trip_at(next_weekday(2), escort_count=3)
    unknown = DriverProfileFactory(vehicle_capacity=None)
    assert unknown in eligible_drivers(trip)
