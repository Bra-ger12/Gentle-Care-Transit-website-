"""The demo seeder.

Two things matter beyond "it ran": the dataset must cover every status a screen
renders, and it must never touch an account that isn't demo data.
"""

from io import StringIO

import pytest
from django.core.management import call_command

from apps.accounts.management.commands.seed_demo import DEMO_DOMAIN, DEMO_PASSWORD
from apps.accounts.models import DriverProfile, RiderProfile, Role, User
from apps.billing.models import Invoice
from apps.payroll.models import TripEarning
from apps.trips.models import RecurringTripSeries, Trip, TripStatus

pytestmark = pytest.mark.django_db


def seed(*args):
    out = StringIO()
    call_command("seed_demo", *args, stdout=out)
    return out.getvalue()


def demo_users():
    return User.objects.filter(email__endswith=f"@{DEMO_DOMAIN}")


def test_seed_creates_the_documented_dataset():
    seed()

    assert demo_users().filter(role=Role.ADMIN).count() == 1
    assert RiderProfile.objects.count() == 5
    assert DriverProfile.objects.count() == 3
    assert Trip.objects.count() == 23  # 21 one-way + a round trip's two legs
    assert RecurringTripSeries.objects.count() == 1
    assert Trip.objects.filter(trip_type="ROUND_TRIP").count() == 2
    assert Trip.objects.filter(is_will_call=True).count() == 1


def test_seed_covers_every_trip_status():
    """Every status has a screen; every screen needs something to render."""
    seed()
    seeded = set(Trip.objects.values_list("status", flat=True))
    assert seeded == set(TripStatus.values)


def test_seed_produces_a_usable_login():
    seed()
    admin = demo_users().get(role=Role.ADMIN)
    assert admin.check_password(DEMO_PASSWORD)
    assert admin.is_verified is True


def test_completed_trips_are_invoiced_and_paid_out():
    seed()
    completed = Trip.objects.filter(status=TripStatus.COMPLETED)
    assert completed.exists()
    assert Invoice.objects.count() == completed.count()
    assert TripEarning.objects.count() == completed.count()


def test_invoices_span_the_billing_lifecycle():
    seed()
    statuses = set(Invoice.objects.values_list("status", flat=True))
    assert {"DRAFT", "FINALIZED", "PAID"} <= statuses


def test_completed_trips_carry_a_full_record():
    seed()
    for trip in Trip.objects.filter(status=TripStatus.COMPLETED):
        assert trip.assigned_driver is not None
        assert trip.picked_up_at is not None
        assert trip.completed_at > trip.picked_up_at
        assert trip.odometer_end >= trip.odometer_start
        assert trip.completion_attestation


def test_running_twice_does_not_duplicate():
    seed()
    output = seed()
    assert "already present" in output
    assert Trip.objects.count() == 23  # 21 one-way + a round trip's two legs


def test_flush_rebuilds_cleanly():
    seed()
    first = set(Trip.objects.values_list("id", flat=True))
    seed("--flush")

    assert Trip.objects.count() == 23  # 21 one-way + a round trip's two legs
    assert set(Trip.objects.values_list("id", flat=True)) != first
    assert demo_users().count() == 9  # 1 admin + 5 riders + 3 drivers


def test_flush_leaves_real_accounts_alone():
    """The guard that makes --flush safe on a database with live accounts."""
    real = User.objects.create_user(
        email="someone@gentlecaretransit.org", password="x", role=Role.ADMIN
    )
    seed()
    seed("--flush")

    assert User.objects.filter(pk=real.pk).exists()


def test_mileage_is_flagged_when_estimated(settings):
    settings.GOOGLE_MAPS_API_KEY = ""
    seed()
    assert Trip.objects.filter(distance_estimated=True).count() == 23
    assert not Trip.objects.filter(mileage__lte=0).exists()
