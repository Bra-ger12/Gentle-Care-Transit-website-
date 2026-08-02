"""Service-area coverage, and the booking rejection it produces."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import AdminFactory, RiderProfileFactory
from apps.operations.models import ServiceArea, ServiceAreaKind, SystemSetting
from apps.operations.services import ServiceAreaError, check_service_area, is_covered
from apps.trips.models import Trip

pytestmark = pytest.mark.django_db

BISMARCK = "1420 Boulevard Ave, Bismarck, ND"
FARGO = "300 Main Ave, Fargo, ND"
WILLISTON = "1301 15th Ave W, Williston, ND"


def place(name, **kwargs):
    return ServiceArea.objects.create(
        name=name.title(), kind=ServiceAreaKind.PLACE, place=name.upper(), **kwargs
    )


def radius(name, lat, lng, miles, **kwargs):
    return ServiceArea.objects.create(
        name=name,
        kind=ServiceAreaKind.RADIUS,
        center_lat=Decimal(str(lat)),
        center_lng=Decimal(str(lng)),
        radius_miles=Decimal(str(miles)),
        **kwargs,
    )


def test_no_areas_means_no_restriction():
    """A fresh install hasn't drawn a boundary, so it turns nobody away."""
    assert is_covered(WILLISTON) is True


def test_place_rule_matches_by_name():
    place("BISMARCK")
    assert is_covered(BISMARCK) is True
    assert is_covered(FARGO) is False


def test_place_rule_matches_by_proximity_when_the_town_is_not_named():
    """A Google-resolved address can arrive without its city; coordinates decide."""
    place("BISMARCK")
    near = (Decimal("46.8100"), Decimal("-100.7800"))
    assert is_covered("300 N 7th St", near) is True


def test_radius_rule_covers_what_is_inside_it():
    radius("Burleigh County area", 46.8083, -100.7837, 40)
    inside = (Decimal("46.8267"), Decimal("-100.8896"))  # Mandan
    outside = (Decimal("46.8772"), Decimal("-96.7898"))  # Fargo
    assert is_covered("405 3rd Ave NW, Mandan, ND", inside) is True
    assert is_covered(FARGO, outside) is False


def test_any_matching_rule_is_enough():
    place("BISMARCK")
    place("FARGO")
    assert is_covered(BISMARCK) is True
    assert is_covered(FARGO) is True


def test_inactive_rules_are_ignored():
    place("BISMARCK")
    place("FARGO", is_active=False)
    assert is_covered(FARGO) is False


def test_check_names_the_end_that_is_out_of_area():
    place("BISMARCK")
    with pytest.raises(ServiceAreaError) as exc:
        check_service_area(BISMARCK, None, FARGO, None)
    assert "dropoff_address" in exc.value.args[0]
    assert "pickup_address" not in exc.value.args[0]


def test_check_is_skipped_when_enforcement_is_off():
    place("BISMARCK")
    setting = SystemSetting.load()
    setting.enforce_service_area = False
    setting.save()

    check_service_area(BISMARCK, None, FARGO, None)  # must not raise


def _booking(**overrides):
    payload = {
        "scheduled_pickup_time": (timezone.now() + timedelta(days=3)).isoformat(),
        "pickup_address": BISMARCK,
        "dropoff_address": "Sanford Health, 300 N 7th St, Bismarck, ND",
    }
    payload.update(overrides)
    return payload


def test_booking_inside_the_area_succeeds(client, _auth):
    place("BISMARCK")
    profile = RiderProfileFactory()
    _auth(client, profile.user)

    response = client.post("/api/trips/", _booking(), format="json")
    assert response.status_code == 201, response.data


def test_booking_outside_the_area_is_rejected_with_a_useful_message(client, _auth):
    place("BISMARCK")
    profile = RiderProfileFactory()
    _auth(client, profile.user)

    response = client.post("/api/trips/", _booking(dropoff_address=FARGO), format="json")

    assert response.status_code == 400, response.data
    assert "dropoff_address" in response.data
    assert "Bismarck" in str(response.data["dropoff_address"])
    assert Trip.objects.count() == 0


def test_recurring_series_honours_the_service_area(client, _auth):
    place("BISMARCK")
    profile = RiderProfileFactory()
    _auth(client, profile.user)
    today = timezone.localdate()

    response = client.post(
        "/api/trips/recurring-series/",
        {
            "pickup_address": BISMARCK,
            "dropoff_address": FARGO,
            "pickup_time": "09:00:00",
            "weekdays": [today.weekday()],
            "start_date": today.isoformat(),
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "dropoff_address" in response.data


def test_only_admins_may_change_the_service_area(client, _auth):
    profile = RiderProfileFactory()
    _auth(client, profile.user)

    response = client.post(
        "/api/operations/service-areas/",
        {"name": "Anywhere", "kind": "PLACE", "place": "Fargo"},
        format="json",
    )
    assert response.status_code == 403


def test_admin_can_add_an_area_and_it_takes_effect(client, _auth):
    admin = AdminFactory()
    _auth(client, admin)

    created = client.post(
        "/api/operations/service-areas/",
        {"name": "Bismarck", "kind": "PLACE", "place": "bismarck"},
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.data["place"] == "BISMARCK"
    assert is_covered(FARGO) is False


def test_a_place_rule_must_name_a_town_the_geocoder_knows(client, _auth):
    admin = AdminFactory()
    _auth(client, admin)

    response = client.post(
        "/api/operations/service-areas/",
        {"name": "Nowhere", "kind": "PLACE", "place": "Atlantis"},
        format="json",
    )
    assert response.status_code == 400
    assert "place" in response.data


def test_a_radius_rule_needs_a_centre_and_a_radius(client, _auth):
    admin = AdminFactory()
    _auth(client, admin)

    response = client.post(
        "/api/operations/service-areas/",
        {"name": "Somewhere", "kind": "RADIUS"},
        format="json",
    )
    assert response.status_code == 400
    assert "radius_miles" in response.data


def test_summary_tells_a_rider_where_the_service_runs(client, _auth):
    place("BISMARCK")
    profile = RiderProfileFactory()
    _auth(client, profile.user)

    response = client.get("/api/operations/service-area-summary/")

    assert response.status_code == 200
    assert response.data["enforced"] is True
    assert [area["name"] for area in response.data["areas"]] == ["Bismarck"]
