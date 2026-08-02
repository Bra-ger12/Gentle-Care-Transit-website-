from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone

from apps.accounts.models import MobilityNeed
from apps.trips.models import Trip, TripStatus

from ..models import Invoice, InvoiceStatus, RateSchedule


class InvoiceError(Exception):
    """Raised for any illegal invoice generation/lifecycle operation. Caught
    and translated to a DRF ValidationError at the view layer -- this module
    stays framework-agnostic, matching apps.trips.services."""


def get_applicable_rate_schedule(trip):
    """Most recent active RateSchedule covering the trip's completion date,
    preferring a schedule matching the trip's mobility_need and falling back
    to the blank/default tier. Uses localtime, not a naive .date(), since
    TIME_ZONE=America/Chicago but Trip.completed_at is stored in UTC -- a
    naive .date() would misfile evening trips into the wrong day's rate."""
    completed_date = timezone.localtime(trip.completed_at).date()
    candidates = RateSchedule.objects.filter(
        is_active=True, effective_from__lte=completed_date
    ).filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=completed_date))

    schedule = (
        candidates.filter(mobility_need=trip.mobility_need).order_by("-effective_from").first()
    )
    if schedule is None:
        schedule = candidates.filter(mobility_need="").order_by("-effective_from").first()
    return schedule


def mobility_surcharge(schedule, mobility_need) -> Decimal:
    """Extra charged for the tiers that cost more to serve.

    Zero when the operator prices tiers with separate rate schedules instead --
    the two mechanisms are alternatives, and charging both would double-bill.
    """
    if mobility_need == MobilityNeed.WHEELCHAIR:
        return schedule.wheelchair_surcharge
    if mobility_need == MobilityNeed.STRETCHER:
        return schedule.stretcher_surcharge
    return Decimal("0.00")


def billable_wait_minutes(trip, schedule) -> int:
    """Minutes the driver waited at the door beyond the free allowance.

    Runs from the driver marking themselves arrived to the rider boarding. A
    trip that never recorded an arrival bills no wait -- an unmeasured wait is
    not a chargeable one.
    """
    if trip.arrived_at is None or trip.picked_up_at is None:
        return 0
    waited = (trip.picked_up_at - trip.arrived_at).total_seconds() / 60
    return max(0, int(waited) - schedule.free_wait_minutes)


def _next_invoice_number(year: int) -> str:
    prefix = f"INV-{year}-"
    candidates = Invoice.objects.filter(invoice_number__startswith=prefix)
    last = candidates.order_by("-invoice_number").first()
    next_seq = int(last.invoice_number.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{next_seq:06d}"


@transaction.atomic
def generate_invoice_for_trip(trip, actor=None) -> Invoice:
    """Idempotent: returns the existing active (non-VOID) invoice for this
    trip if one already exists, rather than creating a duplicate."""
    existing = Invoice.objects.filter(trip=trip).exclude(status=InvoiceStatus.VOID).first()
    if existing is not None:
        return existing

    if trip.status != TripStatus.COMPLETED:
        raise InvoiceError(f"Trip {trip.id} is not COMPLETED; cannot invoice.")
    if trip.completed_at is None:
        raise InvoiceError(f"Trip {trip.id} has no completed_at timestamp.")

    schedule = get_applicable_rate_schedule(trip)
    if schedule is None:
        completed_date = timezone.localtime(trip.completed_at).date()
        raise InvoiceError(
            f"No active rate schedule covers trip {trip.id} "
            f"(completed {completed_date}, mobility_need={trip.mobility_need!r})."
        )

    # Trip.mileage may still be a plain str on an in-memory instance that
    # hasn't round-tripped through the DB (DecimalField doesn't coerce
    # assigned values until then) -- coerce explicitly rather than assume.
    mileage = Decimal(str(trip.mileage))
    mileage_amount = (mileage * schedule.per_mile_rate).quantize(Decimal("0.01"))
    surcharge_amount = mobility_surcharge(schedule, trip.mobility_need)
    wait_minutes = billable_wait_minutes(trip, schedule)
    wait_time_amount = (wait_minutes * schedule.wait_time_rate_per_minute).quantize(Decimal("0.01"))
    total_amount = (
        schedule.base_fare + mileage_amount + surcharge_amount + wait_time_amount
    ).quantize(Decimal("0.01"))
    rider = trip.rider

    return Invoice.objects.create(
        trip=trip,
        rider=rider,
        rate_schedule=schedule,
        invoice_number=_next_invoice_number(timezone.localtime(trip.completed_at).year),
        status=InvoiceStatus.DRAFT,
        rider_name_snapshot=rider.user.get_full_name(),
        medicaid_id_snapshot=rider.medicaid_id or None,
        prior_auth_snapshot=rider.prior_auth_number or "",
        mobility_need_snapshot=trip.mobility_need,
        mileage_snapshot=mileage,
        base_fare=schedule.base_fare,
        per_mile_rate=schedule.per_mile_rate,
        mileage_amount=mileage_amount,
        surcharge_amount=surcharge_amount,
        billable_wait_minutes=wait_minutes,
        wait_time_amount=wait_time_amount,
        total_amount=total_amount,
        generated_by=actor,
    )


def generate_pending_invoices(actor=None) -> list[Invoice]:
    """Bulk-generate invoices for every COMPLETED trip that lacks an active
    (non-VOID) invoice -- covers both never-invoiced trips and trips whose
    prior invoice was voided and needs reissuing."""
    trips = Trip.objects.filter(status=TripStatus.COMPLETED).exclude(
        invoices__status__in=[InvoiceStatus.DRAFT, InvoiceStatus.FINALIZED, InvoiceStatus.PAID]
    )
    return [generate_invoice_for_trip(trip, actor=actor) for trip in trips]


def finalize_invoice(invoice: Invoice, actor=None) -> Invoice:
    if invoice.status != InvoiceStatus.DRAFT:
        raise InvoiceError("Only DRAFT invoices can be finalized.")
    invoice.status = InvoiceStatus.FINALIZED
    invoice.finalized_at = timezone.now()
    invoice.finalized_by = actor
    invoice.save(update_fields=["status", "finalized_at", "finalized_by", "updated_at"])
    return invoice


def mark_invoice_paid(invoice: Invoice, actor=None, payment_reference: str = "") -> Invoice:
    if invoice.status != InvoiceStatus.FINALIZED:
        raise InvoiceError("Only FINALIZED invoices can be marked paid.")
    invoice.status = InvoiceStatus.PAID
    invoice.paid_at = timezone.now()
    invoice.paid_by = actor
    invoice.payment_reference = payment_reference
    invoice.save(update_fields=["status", "paid_at", "paid_by", "payment_reference", "updated_at"])
    return invoice


def void_invoice(invoice: Invoice, actor=None, reason: str = "") -> Invoice:
    if invoice.status not in (InvoiceStatus.DRAFT, InvoiceStatus.FINALIZED):
        raise InvoiceError("Only DRAFT or FINALIZED invoices can be voided.")
    invoice.status = InvoiceStatus.VOID
    invoice.voided_at = timezone.now()
    invoice.voided_by = actor
    invoice.void_reason = reason
    invoice.save(update_fields=["status", "voided_at", "voided_by", "void_reason", "updated_at"])
    return invoice
