from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone

from apps.trips.models import Trip, TripStatus

from ..models import DriverPayRate, TripEarning


class EarningError(Exception):
    """Raised for any illegal earning generation/lifecycle operation. Translated
    to a DRF ValidationError at the view layer -- this module stays
    framework-agnostic, matching apps.billing.services.pricing."""


def get_applicable_pay_rate(trip):
    """Most recent active DriverPayRate covering the trip's completion date,
    preferring one negotiated for that specific driver and falling back to the
    house default. Uses localtime for the same reason invoicing does: completed_at
    is stored in UTC, so a naive .date() would misfile evening trips."""
    completed_date = timezone.localtime(trip.completed_at).date()
    candidates = DriverPayRate.objects.filter(
        is_active=True, effective_from__lte=completed_date
    ).filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=completed_date))

    rate = candidates.filter(driver=trip.assigned_driver).order_by("-effective_from").first()
    if rate is None:
        rate = candidates.filter(driver__isnull=True).order_by("-effective_from").first()
    return rate


@transaction.atomic
def generate_earning_for_trip(trip, actor=None) -> TripEarning:
    """Idempotent: a trip that already has an earning returns it untouched, so
    re-running generation never double-pays."""
    existing = TripEarning.objects.filter(trip=trip).first()
    if existing is not None:
        return existing

    if trip.status != TripStatus.COMPLETED:
        raise EarningError(f"Trip {trip.id} is not COMPLETED; nothing was earned.")
    if trip.completed_at is None:
        raise EarningError(f"Trip {trip.id} has no completed_at timestamp.")
    if trip.assigned_driver is None:
        raise EarningError(f"Trip {trip.id} has no assigned driver to pay.")

    rate = get_applicable_pay_rate(trip)
    if rate is None:
        completed_date = timezone.localtime(trip.completed_at).date()
        raise EarningError(
            f"No active pay rate covers trip {trip.id} (completed {completed_date}). "
            "Add a default DriverPayRate."
        )

    # Trip.mileage may still be a plain str on an in-memory instance, as in billing.
    mileage = Decimal(str(trip.mileage or 0))
    mileage_amount = (mileage * rate.per_mile_rate).quantize(Decimal("0.01"))
    total_amount = (rate.per_trip_base + mileage_amount).quantize(Decimal("0.01"))

    return TripEarning.objects.create(
        trip=trip,
        driver=trip.assigned_driver,
        pay_rate=rate,
        earned_on=timezone.localtime(trip.completed_at).date(),
        mileage_snapshot=mileage,
        per_trip_base=rate.per_trip_base,
        per_mile_rate=rate.per_mile_rate,
        mileage_amount=mileage_amount,
        total_amount=total_amount,
        generated_by=actor,
    )


def generate_pending_earnings(actor=None) -> list[TripEarning]:
    """Every completed, driven trip that has no earning row yet."""
    trips = Trip.objects.filter(
        status=TripStatus.COMPLETED, assigned_driver__isnull=False, earning__isnull=True
    ).select_related("assigned_driver")
    return [generate_earning_for_trip(trip, actor=actor) for trip in trips]


def mark_earning_paid(earning: TripEarning, actor=None, payment_reference: str = "") -> TripEarning:
    if earning.paid_at is not None:
        raise EarningError("This earning has already been paid.")
    earning.paid_at = timezone.now()
    earning.paid_by = actor
    earning.payment_reference = payment_reference
    earning.save(update_fields=["paid_at", "paid_by", "payment_reference", "updated_at"])
    return earning


def earnings_summary(driver, date_from=None, date_to=None) -> dict:
    """Totals for a driver over a date range -- what the driver's own board and
    report show, and what an admin sees per driver."""
    queryset = TripEarning.objects.filter(driver=driver)
    if date_from:
        queryset = queryset.filter(earned_on__gte=date_from)
    if date_to:
        queryset = queryset.filter(earned_on__lte=date_to)

    totals = queryset.aggregate(
        trips=models.Count("id"),
        total=models.Sum("total_amount"),
        miles=models.Sum("mileage_snapshot"),
    )
    unpaid = queryset.filter(paid_at__isnull=True).aggregate(total=models.Sum("total_amount"))
    zero = Decimal("0.00")
    return {
        "trips": totals["trips"] or 0,
        "total_earned": totals["total"] or zero,
        "total_miles": totals["miles"] or zero,
        "unpaid_amount": unpaid["total"] or zero,
    }
