from datetime import date, datetime
from datetime import timezone as dt_timezone
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.billing.models import Invoice
from apps.billing.services.pricing import InvoiceError, generate_invoice_for_trip
from apps.billing.tests.factories import RateScheduleFactory
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


def _completed_trip(**kwargs):
    defaults = dict(status=TripStatus.COMPLETED, completed_at=timezone.now(), mileage="4.00")
    defaults.update(kwargs)
    return TripFactory(**defaults)


def test_generate_invoice_computes_correct_amounts():
    RateScheduleFactory(base_fare="5.00", per_mile_rate="2.50", mobility_need="")
    trip = _completed_trip(mileage="4.00", mobility_need="")

    invoice = generate_invoice_for_trip(trip)

    assert invoice.base_fare == Decimal("5.00")
    assert invoice.mileage_amount == Decimal("10.00")
    assert invoice.total_amount == Decimal("15.00")


def test_generate_invoice_is_idempotent():
    RateScheduleFactory()
    trip = _completed_trip()

    first = generate_invoice_for_trip(trip)
    second = generate_invoice_for_trip(trip)

    assert first.id == second.id
    assert Invoice.objects.filter(trip=trip).count() == 1


def test_generate_invoice_rejects_non_completed_trip():
    RateScheduleFactory()
    trip = TripFactory(status=TripStatus.REQUESTED)

    with pytest.raises(InvoiceError):
        generate_invoice_for_trip(trip)


def test_generate_invoice_raises_when_no_schedule_applies():
    trip = _completed_trip(mobility_need="OXYGEN")

    with pytest.raises(InvoiceError):
        generate_invoice_for_trip(trip)


def test_mobility_specific_schedule_preferred_over_default():
    RateScheduleFactory(mobility_need="", base_fare="5.00", per_mile_rate="1.00")
    RateScheduleFactory(mobility_need="WHEELCHAIR", base_fare="15.00", per_mile_rate="3.00")
    trip = _completed_trip(mobility_need="WHEELCHAIR", mileage="2.00")

    invoice = generate_invoice_for_trip(trip)

    assert invoice.base_fare == Decimal("15.00")
    assert invoice.total_amount == Decimal("21.00")


def test_rate_lookup_uses_local_date_not_utc_date():
    """Trip completes 2026-01-02 02:00 UTC == 2026-01-01 20:00 America/Chicago
    (CST, UTC-6 in January). A schedule covering only 2026-01-01 must still
    apply -- a naive .date() on the UTC value would wrongly land on
    2026-01-02 and miss it entirely."""
    RateScheduleFactory(
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 1, 1),
        base_fare="8.00",
        per_mile_rate="2.00",
    )
    completed_at = datetime(2026, 1, 2, 2, 0, tzinfo=dt_timezone.utc)
    trip = _completed_trip(completed_at=completed_at, mileage="1.00")

    invoice = generate_invoice_for_trip(trip)

    assert invoice.total_amount == Decimal("10.00")
