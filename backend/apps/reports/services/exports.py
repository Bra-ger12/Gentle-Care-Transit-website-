"""CSV downloads for the reports screen.

Each export answers one question an operator gets asked: what did we run, what
did we bill, who drove, how far. They stream through Django's HttpResponse
rather than building a file, so a wide date range doesn't sit in memory twice.
"""

import csv

from django.http import HttpResponse
from django.utils import timezone

from apps.billing.models import Invoice, InvoiceStatus
from apps.trips.models import Trip, TripStatus

from . import kpis


def _csv_response(filename: str, columns: list[str], rows) -> HttpResponse:
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(columns)
    for row in rows:
        writer.writerow(row)
    return response


def _local_date(value):
    return timezone.localtime(value).date().isoformat() if value else ""


def _local_time(value):
    return timezone.localtime(value).strftime("%H:%M") if value else ""


TRIP_COLUMNS = [
    "trip_id",
    "date",
    "scheduled_pickup",
    "status",
    "rider",
    "medicaid_id",
    "driver",
    "pickup_address",
    "dropoff_address",
    "mileage",
    "mileage_estimated",
    "mobility_need",
    "escorts",
    "trip_type",
    "picked_up",
    "completed",
    "no_show_waited_minutes",
]


def trips_csv(date_from, date_to) -> HttpResponse:
    trips = (
        Trip.objects.filter(scheduled_pickup_time__date__range=(date_from, date_to))
        .select_related("rider__user", "assigned_driver__user")
        .order_by("scheduled_pickup_time")
    )
    rows = (
        [
            str(trip.id),
            _local_date(trip.scheduled_pickup_time),
            _local_time(trip.scheduled_pickup_time),
            trip.status,
            trip.rider.user.get_full_name(),
            trip.rider.medicaid_id or "",
            trip.assigned_driver.user.get_full_name() if trip.assigned_driver else "",
            trip.pickup_address,
            trip.dropoff_address,
            str(trip.mileage),
            "yes" if trip.distance_estimated else "no",
            trip.mobility_need,
            trip.escort_count,
            trip.trip_type,
            _local_time(trip.picked_up_at),
            _local_time(trip.completed_at),
            trip.no_show_waited_minutes if trip.no_show_waited_minutes is not None else "",
        ]
        for trip in trips
    )
    return _csv_response(f"trips_{date_from}_{date_to}.csv", TRIP_COLUMNS, rows)


REVENUE_COLUMNS = [
    "invoice_number",
    "status",
    "trip_date",
    "rider",
    "medicaid_id",
    "prior_auth",
    "mileage",
    "base_fare",
    "mileage_amount",
    "surcharge_amount",
    "wait_minutes",
    "wait_amount",
    "total_amount",
    "paid_at",
]


def revenue_csv(date_from, date_to) -> HttpResponse:
    invoices = (
        Invoice.objects.filter(trip__completed_at__date__range=(date_from, date_to))
        .exclude(status=InvoiceStatus.VOID)
        .select_related("trip")
        .order_by("trip__completed_at")
    )
    rows = (
        [
            invoice.invoice_number,
            invoice.status,
            _local_date(invoice.trip.completed_at),
            invoice.rider_name_snapshot,
            invoice.medicaid_id_snapshot or "",
            invoice.prior_auth_snapshot,
            str(invoice.mileage_snapshot),
            str(invoice.base_fare),
            str(invoice.mileage_amount),
            str(invoice.surcharge_amount),
            invoice.billable_wait_minutes,
            str(invoice.wait_time_amount),
            str(invoice.total_amount),
            _local_date(invoice.paid_at),
        ]
        for invoice in invoices
    )
    return _csv_response(f"revenue_{date_from}_{date_to}.csv", REVENUE_COLUMNS, rows)


DRIVER_COLUMNS = [
    "driver",
    "vehicle_plate",
    "trips",
    "completed",
    "no_shows",
    "miles",
    "average_rating",
]


def driver_performance_csv(date_from, date_to) -> HttpResponse:
    rows = (
        [
            row["name"],
            row["vehicle_plate"],
            row["trips"],
            row["completed"],
            row["no_shows"],
            row["miles"],
            row["average_rating"] if row["average_rating"] is not None else "",
        ]
        for row in kpis.driver_performance(date_from, date_to)
    )
    return _csv_response(f"drivers_{date_from}_{date_to}.csv", DRIVER_COLUMNS, rows)


MILEAGE_COLUMNS = ["date", "driver", "trips", "miles", "estimated_miles"]


def mileage_csv(date_from, date_to) -> HttpResponse:
    """Miles per driver per day -- the shape a mileage reimbursement claim wants.

    Estimated miles are broken out because a haversine figure and a measured one
    should not be totalled as though they carry the same authority.
    """
    trips = (
        Trip.objects.filter(
            status=TripStatus.COMPLETED,
            completed_at__date__range=(date_from, date_to),
            assigned_driver__isnull=False,
        )
        .select_related("assigned_driver__user")
        .order_by("completed_at")
    )

    buckets: dict[tuple, dict] = {}
    for trip in trips:
        key = (_local_date(trip.completed_at), trip.assigned_driver.user.get_full_name())
        bucket = buckets.setdefault(key, {"trips": 0, "miles": 0.0, "estimated": 0.0})
        bucket["trips"] += 1
        bucket["miles"] += float(trip.mileage)
        if trip.distance_estimated:
            bucket["estimated"] += float(trip.mileage)

    rows = (
        [day, driver, data["trips"], round(data["miles"], 2), round(data["estimated"], 2)]
        for (day, driver), data in sorted(buckets.items())
    )
    return _csv_response(f"mileage_{date_from}_{date_to}.csv", MILEAGE_COLUMNS, rows)


EXPORTS = {
    "trips": trips_csv,
    "revenue": revenue_csv,
    "drivers": driver_performance_csv,
    "mileage": mileage_csv,
}
