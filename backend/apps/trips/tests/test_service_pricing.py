from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.tests.factories import AdminFactory, DriverFactory, RiderProfileFactory
from apps.trips.models import Service, Trip, TripType
from apps.trips.services.maps import RouteResolution
from apps.trips.tests.factories import ServiceFactory

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


def _booking(service, **overrides):
    payload = {
        "scheduled_pickup_time": (timezone.now() + timedelta(days=3)).isoformat(),
        "pickup_address": "123 Main St, Fargo, ND",
        "dropoff_address": "456 Broadway, Fargo, ND",
        "service_id": str(service.id),
    }
    payload.update(overrides)
    return payload


def test_service_calculates_cost_with_decimal_rounding():
    service = Service(
        name="Rounding test",
        cost_per_km=Decimal("2.335"),
        base_fee=Decimal("4.00"),
        minimum_fare=Decimal("0.00"),
    )

    assert service.calculate_cost(Decimal("3.00")) == Decimal("11.01")


def test_service_minimum_fare_applies():
    service = ServiceFactory(
        cost_per_km=Decimal("1.00"),
        base_fee=Decimal("2.00"),
        minimum_fare=Decimal("15.00"),
    )

    assert service.calculate_cost(Decimal("3.00")) == Decimal("15.00")


def test_distance_must_be_positive_and_sensible():
    service = ServiceFactory()

    with pytest.raises(ValidationError):
        service.calculate_cost(Decimal("0.00"))
    with pytest.raises(ValidationError):
        service.calculate_cost(Decimal("1000.01"))


@patch("apps.trips.serializers.resolve_route", return_value=ROUTE_RESULT)
def test_booking_saves_locked_price_snapshot(mock_route, client, _auth):
    profile = RiderProfileFactory()
    service = ServiceFactory(
        name="Wheelchair van",
        cost_per_km=Decimal("3.00"),
        base_fee=Decimal("7.00"),
        minimum_fare=Decimal("10.00"),
    )
    _auth(client, profile.user)

    response = client.post("/api/trips/", _booking(service), format="json")

    assert response.status_code == 201, response.data
    trip = Trip.objects.get(id=response.data["id"])
    assert trip.service == service
    assert trip.service_name_snapshot == "Wheelchair van"
    assert trip.distance_km == Decimal("5.15")
    assert trip.cost_per_km_used == Decimal("3.00")
    assert trip.total_cost == Decimal("22.45")

    service.cost_per_km = Decimal("9.99")
    service.save(update_fields=["cost_per_km"])
    trip.refresh_from_db()
    assert trip.cost_per_km_used == Decimal("3.00")
    assert trip.total_cost == Decimal("22.45")


@patch("apps.trips.serializers.resolve_route", return_value=ROUTE_RESULT)
def test_round_trip_return_leg_keeps_old_price(mock_route, client, _auth):
    profile = RiderProfileFactory()
    service = ServiceFactory(cost_per_km=Decimal("2.00"), base_fee=Decimal("5.00"))
    pickup_time = timezone.now() + timedelta(days=3)
    _auth(client, profile.user)

    response = client.post(
        "/api/trips/",
        _booking(
            service,
            scheduled_pickup_time=pickup_time.isoformat(),
            trip_type=TripType.ROUND_TRIP,
            return_pickup_time=(pickup_time + timedelta(hours=3)).isoformat(),
        ),
        format="json",
    )

    assert response.status_code == 201, response.data
    outbound = Trip.objects.get(id=response.data["id"])
    assert outbound.return_trip.total_cost == outbound.total_cost
    assert outbound.return_trip.cost_per_km_used == Decimal("2.00")


def test_only_active_services_are_returned_to_patients(client, _auth):
    active = ServiceFactory(name="Standard car", is_active=True)
    ServiceFactory(name="Retired van", is_active=False)
    profile = RiderProfileFactory()
    _auth(client, profile.user)

    response = client.get("/api/trips/services/")

    assert response.status_code == 200, response.data
    names = {row["name"] for row in response.data["results"]}
    assert names == {active.name}


@patch("apps.trips.serializers.resolve_route", return_value=ROUTE_RESULT)
def test_inactive_service_cannot_be_booked(mock_route, client, _auth):
    inactive = ServiceFactory(is_active=False)
    profile = RiderProfileFactory()
    _auth(client, profile.user)

    response = client.post("/api/trips/", _booking(inactive), format="json")

    assert response.status_code == 400
    assert Trip.objects.count() == 0


def test_patient_and_driver_cannot_change_prices(client, _auth):
    service = ServiceFactory()
    profile = RiderProfileFactory()
    _auth(client, profile.user)

    rider_response = client.patch(
        f"/api/trips/services/{service.id}/", {"cost_per_km": "99.00"}, format="json"
    )
    assert rider_response.status_code == 403

    driver = DriverFactory()
    _auth(client, driver)
    driver_response = client.patch(
        f"/api/trips/services/{service.id}/", {"cost_per_km": "99.00"}, format="json"
    )
    assert driver_response.status_code == 403


def test_admin_can_change_prices(client, _auth):
    service = ServiceFactory(cost_per_km=Decimal("2.50"))
    admin = AdminFactory()
    _auth(client, admin)

    response = client.patch(
        f"/api/trips/services/{service.id}/", {"cost_per_km": "3.75"}, format="json"
    )

    assert response.status_code == 200, response.data
    service.refresh_from_db()
    assert service.cost_per_km == Decimal("3.75")


@patch("apps.trips.serializers.resolve_route", return_value=ROUTE_RESULT)
def test_estimate_endpoint_returns_server_calculated_cost(mock_route, client, _auth):
    service = ServiceFactory(cost_per_km=Decimal("2.00"), base_fee=Decimal("5.00"))
    profile = RiderProfileFactory()
    _auth(client, profile.user)

    response = client.post(
        "/api/trips/estimate-cost/",
        {
            "service_id": str(service.id),
            "pickup_address": "123 Main St, Fargo, ND",
            "dropoff_address": "456 Broadway, Fargo, ND",
            "trip_type": TripType.ROUND_TRIP,
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["distance_km"] == Decimal("5.15")
    assert response.data["leg_cost"] == Decimal("15.30")
    assert response.data["total_cost"] == Decimal("30.60")
