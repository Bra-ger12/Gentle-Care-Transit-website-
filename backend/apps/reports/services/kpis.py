from datetime import timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.accounts.models import DriverProfile
from apps.billing.models import Invoice, InvoiceStatus
from apps.trips.models import Trip, TripStatus


def trip_volume_summary(date_from, date_to):
    trips = Trip.objects.filter(scheduled_pickup_time__date__range=(date_from, date_to))
    status_counts = trips.values("status").annotate(count=Count("id"))
    by_status = {row["status"]: row["count"] for row in status_counts}
    return {"total": trips.count(), "by_status": by_status}


def cancellation_no_show_rate(date_from, date_to):
    trips = Trip.objects.filter(scheduled_pickup_time__date__range=(date_from, date_to))
    total = trips.count()
    if total == 0:
        return {
            "total": 0,
            "cancelled": 0,
            "no_show": 0,
            "cancellation_rate": 0.0,
            "no_show_rate": 0.0,
        }

    cancelled = trips.filter(status=TripStatus.CANCELLED).count()
    no_show = trips.filter(status=TripStatus.NO_SHOW).count()
    return {
        "total": total,
        "cancelled": cancelled,
        "no_show": no_show,
        "cancellation_rate": round(cancelled / total, 4),
        "no_show_rate": round(no_show / total, 4),
    }


def avg_cycle_time(date_from, date_to):
    """Average minutes from Trip.created_at to Trip.completed_at, for trips
    completed within the window."""
    trips = Trip.objects.filter(
        status=TripStatus.COMPLETED, completed_at__date__range=(date_from, date_to)
    )
    result = trips.annotate(
        cycle_duration=ExpressionWrapper(
            F("completed_at") - F("created_at"), output_field=DurationField()
        )
    ).aggregate(avg=Avg("cycle_duration"))
    avg_duration = result["avg"]
    if avg_duration is None:
        return {"avg_cycle_minutes": None, "sample_size": 0}
    return {
        "avg_cycle_minutes": round(avg_duration.total_seconds() / 60, 1),
        "sample_size": trips.count(),
    }


def revenue_summary(date_from, date_to):
    invoices = Invoice.objects.filter(trip__completed_at__date__range=(date_from, date_to))

    def _sum(status):
        return invoices.filter(status=status).aggregate(s=Sum("total_amount"))["s"] or 0

    outstanding_total = _sum(InvoiceStatus.FINALIZED)
    paid_total = _sum(InvoiceStatus.PAID)
    return {
        "draft_total": _sum(InvoiceStatus.DRAFT),
        "outstanding_total": outstanding_total,
        "paid_total": paid_total,
        "billed_total": outstanding_total + paid_total,
    }


def revenue_by_month(date_from, date_to):
    invoices = Invoice.objects.filter(
        status__in=[InvoiceStatus.FINALIZED, InvoiceStatus.PAID],
        trip__completed_at__date__range=(date_from, date_to),
    )
    rows = (
        invoices.annotate(month=TruncMonth("trip__completed_at"))
        .values("month")
        .annotate(total=Sum("total_amount"))
        .order_by("month")
    )
    return [{"month": row["month"].date().isoformat(), "total": row["total"]} for row in rows]


# A pickup counts as on time if the driver had the rider aboard within this many
# minutes of the scheduled slot. NEMT riders have appointments to keep, and a
# 15-minute window is the usual contractual standard.
ON_TIME_GRACE_MINUTES = 15


def on_time_performance(date_from, date_to):
    """Share of served trips where pickup happened inside the grace window.

    Only trips that actually recorded a pickup are counted. A cancelled or
    no-show trip has no pickup to be late for, and folding them in would
    conflate two different failures.
    """
    served = Trip.objects.filter(
        status__in=[TripStatus.PICKED_UP, TripStatus.COMPLETED],
        picked_up_at__isnull=False,
        scheduled_pickup_time__date__range=(date_from, date_to),
    )
    total = served.count()
    if total == 0:
        return {"total": 0, "on_time": 0, "late": 0, "on_time_rate": None}

    on_time = served.filter(
        picked_up_at__lte=F("scheduled_pickup_time")
        + timedelta(minutes=ON_TIME_GRACE_MINUTES)
    ).count()
    return {
        "total": total,
        "on_time": on_time,
        "late": total - on_time,
        "on_time_rate": round(on_time / total, 4),
    }


def driver_activity(date_from, date_to):
    """How much of the fleet is actually working."""
    approved = DriverProfile.objects.filter(is_approved=True)
    drove = (
        Trip.objects.filter(
            assigned_driver__isnull=False,
            scheduled_pickup_time__date__range=(date_from, date_to),
        )
        .values("assigned_driver")
        .distinct()
        .count()
    )
    return {
        "approved_drivers": approved.count(),
        "on_duty_now": approved.filter(is_available=True).count(),
        "drivers_with_trips": drove,
        "awaiting_approval": DriverProfile.objects.filter(is_approved=False).count(),
    }


def today_snapshot():
    """The tiles a dispatcher reads first thing: what is happening right now."""
    today = timezone.localdate()
    todays = Trip.objects.filter(scheduled_pickup_time__date=today)
    return {
        "date": today.isoformat(),
        "trips_today": todays.count(),
        "pending": Trip.objects.filter(status=TripStatus.REQUESTED).count(),
        "unassigned": Trip.objects.filter(
            status=TripStatus.CONFIRMED, scheduled_pickup_time__date=today
        ).count(),
        "active": Trip.objects.filter(
            status__in=[
                TripStatus.ASSIGNED,
                TripStatus.EN_ROUTE,
                TripStatus.ARRIVED,
                TripStatus.PICKED_UP,
            ]
        ).count(),
        "completed_today": todays.filter(status=TripStatus.COMPLETED).count(),
        "awaiting_acceptance": Trip.objects.filter(
            status=TripStatus.ASSIGNED, accepted_at__isnull=True
        ).count(),
        "will_call_waiting": Trip.objects.filter(
            is_will_call=True,
            will_call_requested_at__isnull=False,
            status__in=[TripStatus.REQUESTED, TripStatus.CONFIRMED],
        ).count(),
    }


def driver_performance(date_from, date_to):
    """Per-driver league table for the reports screen."""
    rows = (
        DriverProfile.objects.filter(is_approved=True)
        .select_related("user")
        .annotate(
            trips=Count(
                "assigned_trips",
                filter=Q(
                    assigned_trips__scheduled_pickup_time__date__range=(date_from, date_to)
                ),
            ),
            completed=Count(
                "assigned_trips",
                filter=Q(
                    assigned_trips__status=TripStatus.COMPLETED,
                    assigned_trips__scheduled_pickup_time__date__range=(date_from, date_to),
                ),
            ),
            no_shows=Count(
                "assigned_trips",
                filter=Q(
                    assigned_trips__status=TripStatus.NO_SHOW,
                    assigned_trips__scheduled_pickup_time__date__range=(date_from, date_to),
                ),
            ),
            miles=Sum(
                "assigned_trips__mileage",
                filter=Q(
                    assigned_trips__status=TripStatus.COMPLETED,
                    assigned_trips__scheduled_pickup_time__date__range=(date_from, date_to),
                ),
            ),
            rating=Avg("assigned_trips__rating"),
        )
        .order_by("-completed", "user__last_name")
    )
    return [
        {
            "driver_id": row.id,
            "name": row.user.get_full_name(),
            "vehicle_plate": row.vehicle_plate,
            "trips": row.trips,
            "completed": row.completed,
            "no_shows": row.no_shows,
            "miles": float(row.miles) if row.miles is not None else 0.0,
            "average_rating": round(row.rating, 2) if row.rating is not None else None,
        }
        for row in rows
    ]
