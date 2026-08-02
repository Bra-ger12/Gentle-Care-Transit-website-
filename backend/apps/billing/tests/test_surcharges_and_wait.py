"""Mobility surcharges and billable wait time.

The wait charge is why the driver's ARRIVED timestamp exists: without a recorded
arrival there is no defensible start for the clock, and nothing is billed.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import MobilityNeed
from apps.billing.models import RateSchedule
from apps.billing.services.pricing import (
    billable_wait_minutes,
    generate_invoice_for_trip,
    mobility_surcharge,
)
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def schedule():
    return RateSchedule.objects.create(
        mobility_need="",
        base_fare=Decimal("18.00"),
        per_mile_rate=Decimal("2.00"),
        wheelchair_surcharge=Decimal("10.00"),
        stretcher_surcharge=Decimal("37.00"),
        free_wait_minutes=15,
        wait_time_rate_per_minute=Decimal("0.75"),
        effective_from=timezone.localdate() - timedelta(days=30),
    )


def completed_trip(**overrides):
    completed = timezone.now() - timedelta(hours=1)
    fields = {
        "status": TripStatus.COMPLETED,
        "mileage": Decimal("10.00"),
        "completed_at": completed,
        "arrived_at": completed - timedelta(minutes=30),
        "picked_up_at": completed - timedelta(minutes=30),
    }
    fields.update(overrides)
    return TripFactory(**fields)


# --- surcharges ----------------------------------------------------------


def test_ambulatory_pays_no_surcharge(schedule):
    assert mobility_surcharge(schedule, MobilityNeed.AMBULATORY) == Decimal("0.00")
    assert mobility_surcharge(schedule, "") == Decimal("0.00")


def test_wheelchair_and_stretcher_each_have_their_own_surcharge(schedule):
    assert mobility_surcharge(schedule, MobilityNeed.WHEELCHAIR) == Decimal("10.00")
    assert mobility_surcharge(schedule, MobilityNeed.STRETCHER) == Decimal("37.00")


def test_surcharge_lands_on_the_invoice(schedule):
    trip = completed_trip(mobility_need=MobilityNeed.WHEELCHAIR)
    invoice = generate_invoice_for_trip(trip)

    assert invoice.surcharge_amount == Decimal("10.00")
    # 18 base + (10 mi x 2.00) + 10 surcharge
    assert invoice.total_amount == Decimal("48.00")


def test_an_operator_using_tiered_schedules_is_not_double_billed():
    """Zero surcharges on a tier-specific schedule: the tier IS the price."""
    RateSchedule.objects.create(
        mobility_need=MobilityNeed.WHEELCHAIR,
        base_fare=Decimal("28.00"),
        per_mile_rate=Decimal("2.00"),
        effective_from=timezone.localdate() - timedelta(days=30),
    )
    trip = completed_trip(mobility_need=MobilityNeed.WHEELCHAIR)
    invoice = generate_invoice_for_trip(trip)

    assert invoice.surcharge_amount == Decimal("0.00")
    assert invoice.total_amount == Decimal("48.00")  # 28 + 20


# --- wait time -----------------------------------------------------------


def test_a_wait_inside_the_free_allowance_costs_nothing(schedule):
    trip = completed_trip()
    trip.picked_up_at = trip.arrived_at + timedelta(minutes=9)
    trip.save()

    assert billable_wait_minutes(trip, schedule) == 0
    assert generate_invoice_for_trip(trip).wait_time_amount == Decimal("0.00")


def test_only_the_minutes_past_the_allowance_are_billed(schedule):
    trip = completed_trip()
    trip.picked_up_at = trip.arrived_at + timedelta(minutes=40)
    trip.save()

    assert billable_wait_minutes(trip, schedule) == 25  # 40 - 15 free
    invoice = generate_invoice_for_trip(trip)
    assert invoice.billable_wait_minutes == 25
    assert invoice.wait_time_amount == Decimal("18.75")  # 25 x 0.75
    assert invoice.total_amount == Decimal("56.75")  # 18 + 20 + 18.75


def test_a_trip_that_never_recorded_an_arrival_bills_no_wait(schedule):
    """An unmeasured wait is not a chargeable one."""
    trip = completed_trip(arrived_at=None)
    assert billable_wait_minutes(trip, schedule) == 0
    assert generate_invoice_for_trip(trip).wait_time_amount == Decimal("0.00")


def test_wait_is_never_negative(schedule):
    """Clock skew or a corrected timestamp must not produce a credit."""
    trip = completed_trip()
    trip.picked_up_at = trip.arrived_at - timedelta(minutes=5)
    trip.save()
    assert billable_wait_minutes(trip, schedule) == 0


def test_everything_stacks_on_one_invoice(schedule):
    trip = completed_trip(mobility_need=MobilityNeed.STRETCHER)
    trip.picked_up_at = trip.arrived_at + timedelta(minutes=35)
    trip.save()

    invoice = generate_invoice_for_trip(trip)

    assert invoice.base_fare == Decimal("18.00")
    assert invoice.mileage_amount == Decimal("20.00")
    assert invoice.surcharge_amount == Decimal("37.00")
    assert invoice.wait_time_amount == Decimal("15.00")  # 20 billable x 0.75
    assert invoice.total_amount == Decimal("90.00")


def test_amounts_are_snapshotted_against_later_rate_changes(schedule):
    trip = completed_trip(mobility_need=MobilityNeed.WHEELCHAIR)
    invoice = generate_invoice_for_trip(trip)
    original = invoice.total_amount

    schedule.wheelchair_surcharge = Decimal("99.00")
    schedule.save()
    invoice.refresh_from_db()

    assert invoice.total_amount == original
    assert invoice.surcharge_amount == Decimal("10.00")


def test_prior_auth_is_snapshotted_onto_the_claim(schedule):
    trip = completed_trip()
    trip.rider.prior_auth_number = "PA-2026-88134"
    trip.rider.save()

    invoice = generate_invoice_for_trip(trip)

    assert invoice.prior_auth_snapshot == "PA-2026-88134"
