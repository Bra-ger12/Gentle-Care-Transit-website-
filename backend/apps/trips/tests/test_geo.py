"""The offline gazetteer and distance estimator."""

from decimal import Decimal

import pytest

from apps.trips.services import geo


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("1420 Boulevard Ave, Bismarck, ND 58501", "BISMARCK"),
        ("300 N 7th St, Fargo ND", "FARGO"),
        ("St. John Clinic, St. John, ND", "ST JOHN"),
        ("101 Main, west fargo, nd", "WEST FARGO"),
        ("Altru Clinic, East Grand Forks, MN", "EAST GRAND FORKS"),
        ("14 Rue de Rivoli, Paris", None),
        ("", None),
    ],
)
def test_find_place(address, expected):
    assert geo.find_place(address) == expected


def test_longest_place_name_wins():
    """`FARGO` is a substring of `WEST FARGO`; the specific town must win."""
    assert geo.find_place("22 Sheyenne St, West Fargo, ND") == "WEST FARGO"
    assert geo.find_place("22 Broadway, Fargo, ND") == "FARGO"
    assert geo.find_place("Clinic, East Grand Forks, MN") == "EAST GRAND FORKS"
    assert geo.find_place("Altru, Grand Forks, ND") == "GRAND FORKS"


def test_locate_is_deterministic():
    first = geo.locate("1420 Boulevard Ave, Bismarck, ND")
    second = geo.locate("1420 Boulevard Ave, Bismarck, ND")
    assert first == second


def test_locate_ignores_punctuation_and_case():
    assert geo.locate("1420 Boulevard Ave., Bismarck, ND") == geo.locate(
        "1420 boulevard ave Bismarck ND"
    )


def test_two_addresses_in_one_town_are_different_points():
    """Otherwise every in-town trip would price at zero miles."""
    a = geo.locate("1420 Boulevard Ave, Bismarck, ND")
    b = geo.locate("300 N 7th St, Bismarck, ND")
    assert a != b
    assert geo.haversine_miles(a, b) > Decimal("0.05")


def test_locate_stays_near_the_town_centre():
    lat, lng = geo.locate("300 N 7th St, Bismarck, ND")
    centre_lat, centre_lng = geo.ND_PLACES["BISMARCK"]
    assert abs(float(lat) - centre_lat) <= 0.035
    assert abs(float(lng) - centre_lng) <= 0.050


def test_locate_unknown_town_is_none():
    assert geo.locate("14 Rue de Rivoli, Paris") is None


def test_haversine_against_a_known_distance():
    """Bismarck to Fargo is ~189 straight-line miles (193 by I-94)."""
    miles = geo.haversine_miles(
        (Decimal("46.8083"), Decimal("-100.7837")),
        (Decimal("46.8772"), Decimal("-96.7898")),
    )
    assert Decimal("186") < miles < Decimal("192")


def test_haversine_of_a_point_with_itself_is_zero():
    point = (Decimal("46.8083"), Decimal("-100.7837"))
    assert geo.haversine_miles(point, point) == Decimal("0.000000")


def test_estimate_route_applies_the_road_factor():
    origin = (Decimal("46.8083"), Decimal("-100.7837"))
    destination = (Decimal("46.8772"), Decimal("-96.7898"))
    straight = geo.haversine_miles(origin, destination)
    miles, minutes = geo.estimate_route(origin, destination)

    assert miles > straight
    assert miles == (straight * geo.road_circuity_factor(straight)).quantize(Decimal("0.01"))
    assert minutes > 0


def test_circuity_falls_away_on_long_trips():
    """A cross-town hop is boxed around the grid; a highway run is not."""
    assert geo.road_circuity_factor(Decimal("3")) > geo.road_circuity_factor(Decimal("30"))
    assert geo.road_circuity_factor(Decimal("30")) > geo.road_circuity_factor(Decimal("190"))


def test_long_haul_estimate_lands_near_the_real_road_distance():
    """Bismarck to Fargo is 193 miles by I-94; stay within 10% of that."""
    miles, _ = geo.estimate_route(
        (Decimal("46.8083"), Decimal("-100.7837")),
        (Decimal("46.8772"), Decimal("-96.7898")),
    )
    assert Decimal("174") < miles < Decimal("212")


@pytest.mark.parametrize(
    ("miles", "low", "high"),
    [
        (Decimal("0.5"), 5, 5),  # floored at 5 minutes
        (Decimal("3"), 5, 10),  # in-town at 25 mph
        (Decimal("200"), 220, 260),  # highway at 55 mph
    ],
)
def test_estimate_minutes_speed_model(miles, low, high):
    assert low <= geo.estimate_minutes(miles) <= high
