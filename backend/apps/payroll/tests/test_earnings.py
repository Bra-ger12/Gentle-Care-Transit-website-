"""Driver pay: an effective-dated per-trip base + per-mile rate, snapshotted onto
each completed trip so later rate changes never restate what was already earned."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import DriverProfileFactory, RiderFactory
from apps.payroll.models import TripEarning
from apps.payroll.services.earnings import (
    EarningError,
    generate_earning_for_trip,
    generate_pending_earnings,
)
from apps.payroll.tests.factories import DriverPayRateFactory
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


def _completed_trip(driver, mileage="4.60", **kwargs):
    return TripFactory(
        status=TripStatus.COMPLETED,
        assigned_driver=driver,
        completed_at=timezone.now(),
        mileage=mileage,
        **kwargs,
    )


@pytest.fixture
def admin_user():
    return RiderFactory(role=Role.ADMIN, is_staff=True)


def test_earning_is_base_plus_mileage():
    DriverPayRateFactory(per_trip_base="12.00", per_mile_rate="1.35")
    driver = DriverProfileFactory()
    trip = _completed_trip(driver, mileage="4.60")

    earning = generate_earning_for_trip(trip)

    assert earning.per_trip_base == Decimal("12.00")
    assert earning.mileage_amount == Decimal("6.21")  # 4.60 * 1.35
    assert earning.total_amount == Decimal("18.21")
    assert earning.driver == driver
    assert earning.is_paid is False


def test_driver_specific_rate_beats_the_default():
    DriverPayRateFactory(per_trip_base="12.00", per_mile_rate="1.35")
    driver = DriverProfileFactory()
    DriverPayRateFactory(driver=driver, per_trip_base="20.00", per_mile_rate="2.00")
    trip = _completed_trip(driver, mileage="10.00")

    earning = generate_earning_for_trip(trip)

    assert earning.per_trip_base == Decimal("20.00")
    assert earning.total_amount == Decimal("40.00")


def test_rate_change_does_not_restate_past_earnings():
    rate = DriverPayRateFactory(per_trip_base="12.00", per_mile_rate="1.35")
    driver = DriverProfileFactory()
    earning = generate_earning_for_trip(_completed_trip(driver))

    rate.per_trip_base = Decimal("99.00")
    rate.save()
    earning.refresh_from_db()

    assert earning.per_trip_base == Decimal("12.00")
    assert earning.total_amount == Decimal("18.21")


def test_generation_is_idempotent():
    DriverPayRateFactory()
    driver = DriverProfileFactory()
    trip = _completed_trip(driver)

    first = generate_earning_for_trip(trip)
    second = generate_earning_for_trip(trip)

    assert first.id == second.id
    assert TripEarning.objects.count() == 1


def test_only_completed_driven_trips_earn():
    DriverPayRateFactory()
    driver = DriverProfileFactory()
    assigned = TripFactory(status=TripStatus.ASSIGNED, assigned_driver=driver)
    unassigned = TripFactory(status=TripStatus.COMPLETED, completed_at=timezone.now())

    with pytest.raises(EarningError):
        generate_earning_for_trip(assigned)
    with pytest.raises(EarningError):
        generate_earning_for_trip(unassigned)

    _completed_trip(driver)
    assert len(generate_pending_earnings()) == 1


def test_missing_rate_is_refused_not_guessed():
    driver = DriverProfileFactory()
    trip = _completed_trip(driver)

    with pytest.raises(EarningError, match="No active pay rate"):
        generate_earning_for_trip(trip)


def test_rate_outside_its_window_does_not_apply():
    today = timezone.localdate()
    DriverPayRateFactory(
        effective_from=today - timedelta(days=30), effective_to=today - timedelta(days=1)
    )
    driver = DriverProfileFactory()

    with pytest.raises(EarningError, match="No active pay rate"):
        generate_earning_for_trip(_completed_trip(driver))


# --- API ---


def test_driver_sees_only_their_own_earnings(client, _auth):
    DriverPayRateFactory()
    mine, theirs = DriverProfileFactory(), DriverProfileFactory()
    generate_earning_for_trip(_completed_trip(mine))
    generate_earning_for_trip(_completed_trip(theirs))
    _auth(client, mine.user)

    response = client.get("/api/payroll/earnings/")

    assert response.status_code == 200, response.data
    assert response.data["count"] == 1
    assert response.data["results"][0]["driver"] == mine.id


def test_driver_cannot_generate_or_mark_paid(client, _auth):
    DriverPayRateFactory()
    driver = DriverProfileFactory()
    earning = generate_earning_for_trip(_completed_trip(driver))
    _auth(client, driver.user)

    assert client.post("/api/payroll/earnings/generate/").status_code == 403
    assert client.post(f"/api/payroll/earnings/{earning.id}/mark-paid/").status_code == 403


def test_admin_generates_then_marks_paid(client, _auth, admin_user):
    DriverPayRateFactory()
    driver = DriverProfileFactory()
    _completed_trip(driver)
    _auth(client, admin_user)

    generated = client.post("/api/payroll/earnings/generate/")
    assert generated.status_code == 200, generated.data
    assert generated.data["generated"] == 1

    earning_id = generated.data["results"][0]["id"]
    paid = client.post(
        f"/api/payroll/earnings/{earning_id}/mark-paid/",
        {"payment_reference": "ACH-2026-07-31"},
        format="json",
    )

    assert paid.status_code == 200, paid.data
    assert paid.data["is_paid"] is True
    assert paid.data["payment_reference"] == "ACH-2026-07-31"

    # Paying twice is refused rather than silently repeated.
    assert client.post(f"/api/payroll/earnings/{earning_id}/mark-paid/").status_code == 400


def test_summary_totals_for_the_signed_in_driver(client, _auth):
    DriverPayRateFactory(per_trip_base="12.00", per_mile_rate="1.35")
    driver = DriverProfileFactory()
    for _ in range(3):
        generate_earning_for_trip(_completed_trip(driver))
    _auth(client, driver.user)

    response = client.get("/api/payroll/earnings-summary/")

    assert response.status_code == 200, response.data
    assert response.data["trips"] == 3
    assert Decimal(response.data["total_earned"]) == Decimal("54.63")
    assert Decimal(response.data["unpaid_amount"]) == Decimal("54.63")


def test_pay_rates_are_admin_only(client, _auth, admin_user):
    driver = DriverProfileFactory()
    _auth(client, driver.user)
    assert client.get("/api/payroll/pay-rates/").status_code == 403

    _auth(client, admin_user)
    response = client.post(
        "/api/payroll/pay-rates/",
        {
            "per_trip_base": "15.00",
            "per_mile_rate": "1.50",
            "effective_from": timezone.localdate().isoformat(),
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.data["driver"] is None  # the house default
