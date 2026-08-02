from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import permissions
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminRole, IsDriver
from apps.audit.models import AuditAction, AuditLog
from apps.trips.models import Trip, TripStatus

from .services import exports, kpis


def _date_range(request):
    date_to = parse_date(request.query_params.get("date_to", "")) or timezone.localdate()
    default_from = date_to - timedelta(days=30)
    date_from = parse_date(request.query_params.get("date_from", "")) or default_from
    if date_from > date_to:
        raise ValidationError("date_from must be on or before date_to.")
    return date_from, date_to


class KpiSummaryView(APIView):
    """Defaults to the trailing 30 days when date_from/date_to aren't given.
    Not polled like the dispatch board -- these are aggregation queries, so
    the frontend fetches on mount/filter-change rather than every 15s."""

    permission_classes = [permissions.IsAuthenticated, IsAdminRole]

    def get(self, request):
        date_from, date_to = _date_range(request)
        return Response(
            {
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "trip_volume": kpis.trip_volume_summary(date_from, date_to),
                "cancellation_no_show": kpis.cancellation_no_show_rate(date_from, date_to),
                "cycle_time": kpis.avg_cycle_time(date_from, date_to),
                "revenue": kpis.revenue_summary(date_from, date_to),
                "on_time": kpis.on_time_performance(date_from, date_to),
                "drivers": kpis.driver_activity(date_from, date_to),
                "today": kpis.today_snapshot(),
            }
        )


class DriverPerformanceView(APIView):
    """Per-driver league table over a date range."""

    permission_classes = [permissions.IsAuthenticated, IsAdminRole]

    def get(self, request):
        date_from, date_to = _date_range(request)
        return Response(kpis.driver_performance(date_from, date_to))


class ReportExportView(APIView):
    """CSV downloads. `?report=` picks which one; the date range is shared.

    Every export is logged: these files contain rider names and Medicaid IDs,
    and who pulled them is part of the audit trail.
    """

    permission_classes = [permissions.IsAuthenticated, IsAdminRole]

    def get(self, request, *args, **kwargs):
        report = request.query_params.get("report", "trips")
        builder = exports.EXPORTS.get(report)
        if builder is None:
            raise ValidationError(
                {"report": f"Unknown report. Choose one of: {', '.join(exports.EXPORTS)}."}
            )

        date_from, date_to = _date_range(request)
        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.EXPORT,
            model_name="Report",
            object_id=report,
            metadata={"date_from": str(date_from), "date_to": str(date_to)},
        )
        return builder(date_from, date_to)


class RevenueByMonthView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]

    def get(self, request):
        date_from, date_to = _date_range(request)
        return Response(kpis.revenue_by_month(date_from, date_to))


class DriverReportView(APIView):
    """Trips & mileage summary for the signed-in driver over a date range
    (defaults to the trailing 30 days). No earnings -- driver payouts are out
    of scope. The rating figure is the driver's all-time performance rating."""

    permission_classes = [permissions.IsAuthenticated, IsDriver]

    def get(self, request):
        date_from, date_to = _date_range(request)
        driver = request.user.driverprofile

        window = Trip.objects.filter(
            assigned_driver=driver,
            scheduled_pickup_time__date__range=(date_from, date_to),
        )
        agg = window.aggregate(
            total=Count("id"),
            completed=Count("id", filter=Q(status=TripStatus.COMPLETED)),
            no_shows=Count("id", filter=Q(status=TripStatus.NO_SHOW)),
            cancelled=Count("id", filter=Q(status=TripStatus.CANCELLED)),
            miles=Sum("mileage", filter=Q(status=TripStatus.COMPLETED)),
        )
        rating = driver.assigned_trips.filter(rating__isnull=False).aggregate(
            avg=Avg("rating"), count=Count("id")
        )
        return Response(
            {
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "total_trips": agg["total"] or 0,
                "completed": agg["completed"] or 0,
                "no_shows": agg["no_shows"] or 0,
                "cancelled": agg["cancelled"] or 0,
                "total_miles": float(agg["miles"]) if agg["miles"] is not None else 0.0,
                "average_rating": round(rating["avg"], 2) if rating["avg"] is not None else None,
                "ratings_count": rating["count"] or 0,
            }
        )
