from datetime import datetime, timedelta

from celery import shared_task
from django.utils import timezone

from .models import RecurringTripSeries, Trip, TripStatus


def _dates_between(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


@shared_task
def generate_recurring_trips(series_id: str | None = None, window_days: int = 14) -> int:
    """Materialize Trip rows for active RecurringTripSeries within a rolling window.

    Idempotent: re-running (e.g. after a series is created, or from a future
    periodic sweep) never duplicates a slot, backed by the Trip model's partial
    unique constraint on (recurring_series, scheduled_pickup_time).
    """
    series_qs = RecurringTripSeries.objects.filter(is_active=True)
    if series_id:
        series_qs = series_qs.filter(id=series_id)

    today = timezone.localdate()
    current_tz = timezone.get_current_timezone()
    created = 0

    for series in series_qs:
        window_end = today + timedelta(days=window_days)
        effective_end = min(series.end_date, window_end) if series.end_date else window_end
        window_start = max(series.start_date, today)
        if window_start > effective_end:
            continue

        for single_date in _dates_between(window_start, effective_end):
            if single_date.weekday() not in series.weekdays:
                continue

            naive_dt = datetime.combine(single_date, series.pickup_time)
            scheduled_pickup_time = timezone.make_aware(naive_dt, current_tz)

            _, was_created = Trip.objects.get_or_create(
                recurring_series=series,
                scheduled_pickup_time=scheduled_pickup_time,
                defaults=dict(
                    rider=series.rider,
                    status=TripStatus.REQUESTED,
                    pickup_address=series.pickup_address,
                    pickup_lat=series.pickup_lat,
                    pickup_lng=series.pickup_lng,
                    dropoff_address=series.dropoff_address,
                    dropoff_lat=series.dropoff_lat,
                    dropoff_lng=series.dropoff_lng,
                    mileage=series.mileage,
                    distance_estimated=series.distance_estimated,
                    service=series.service,  # NEW: generated rides keep the series service.
                    service_name_snapshot=series.service_name_snapshot,
                    distance_km=series.distance_km,  # NEW: copy the validated priced distance.
                    # Series price changes do not rewrite generated trips.
                    cost_per_km_used=series.cost_per_km_used,
                    base_fee_used=series.base_fee_used,  # NEW: copy fare inputs for audits.
                    minimum_fare_used=series.minimum_fare_used,  # NEW: copy fare inputs for audits.
                    total_cost=series.total_cost,
                    mobility_need=series.mobility_need,
                    notes=series.notes,
                ),
            )
            created += int(was_created)

    return created
