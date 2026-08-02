from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts.models import DriverProfile, MobilityNeed, VehicleType

from ..models import Trip, TripStatus
from .geo import haversine_miles

ACTIVE_STATUSES = [
    TripStatus.ASSIGNED,
    TripStatus.EN_ROUTE,
    TripStatus.ARRIVED,
    TripStatus.PICKED_UP,
]
CONFLICT_WINDOW = timedelta(minutes=90)

# A position older than this tells us nothing about where a driver is now, so
# proximity matching ignores it and falls back to workload order.
LOCATION_FRESHNESS = timedelta(minutes=20)

VEHICLE_CAPABILITY: dict[str, set[str]] = {
    MobilityNeed.STRETCHER: {VehicleType.STRETCHER_VAN},
    MobilityNeed.WHEELCHAIR: {VehicleType.WHEELCHAIR_VAN, VehicleType.STRETCHER_VAN},
}


def _vehicle_capable_drivers(queryset, mobility_need):
    required_vehicle_types = VEHICLE_CAPABILITY.get(mobility_need)
    if not required_vehicle_types:
        return queryset
    return queryset.filter(vehicle_type__in=required_vehicle_types)


def _seats_for(queryset, trip):
    """Exclude vans too small for the rider plus their escorts.

    A driver who hasn't recorded a capacity is left in rather than filtered out:
    an unknown seat count is a missing record, not a small vehicle, and dropping
    them would quietly shrink the pool.
    """
    needed = 1 + (trip.escort_count or 0)
    return queryset.filter(Q(vehicle_capacity__isnull=True) | Q(vehicle_capacity__gte=needed))


def _exclude_double_booked(queryset, trip):
    window_start = trip.scheduled_pickup_time - CONFLICT_WINDOW
    window_end = trip.scheduled_pickup_time + CONFLICT_WINDOW
    busy_driver_ids = (
        Trip.objects.filter(
            status__in=ACTIVE_STATUSES,
            scheduled_pickup_time__range=(window_start, window_end),
        )
        .exclude(pk=trip.pk)
        .values_list("assigned_driver_id", flat=True)
    )
    return queryset.exclude(id__in=busy_driver_ids)


def _exclude_off_shift(queryset, trip):
    """Drop drivers whose calendar says they aren't working at this time.

    A driver with no shift windows recorded is treated as always available --
    that is what every driver was before the calendar existed, and an empty
    calendar means "not configured", not "never works".
    """
    local = timezone.localtime(trip.scheduled_pickup_time)
    weekday, at = local.weekday(), local.time()
    trip_date = local.date()

    unavailable = []
    for driver in queryset.prefetch_related("availability", "time_off"):
        if any(
            period.start_date <= trip_date <= period.end_date for period in driver.time_off.all()
        ):
            unavailable.append(driver.id)
            continue

        windows = list(driver.availability.all())
        if not windows:
            continue
        if not any(
            window.weekday == weekday and window.start_time <= at <= window.end_time
            for window in windows
        ):
            unavailable.append(driver.id)

    return queryset.exclude(id__in=unavailable)


def eligible_drivers(trip):
    """Approved, vehicle-capable, big-enough, on-shift, not double-booked."""
    queryset = DriverProfile.objects.filter(is_approved=True)
    queryset = _vehicle_capable_drivers(queryset, trip.mobility_need)
    queryset = _seats_for(queryset, trip)
    queryset = _exclude_double_booked(queryset, trip)
    return _exclude_off_shift(queryset, trip)


def distance_to_pickup(driver, trip):
    """Miles from a driver's last known position to the pickup, or None.

    None means "we don't know", which is different from "far away" -- callers
    must not treat a driver with no recent fix as the worst candidate.
    """
    location = getattr(driver, "location", None)
    if location is None:
        return None
    if timezone.now() - location.reported_at > LOCATION_FRESHNESS:
        return None
    return haversine_miles(
        (location.lat, location.lng), (trip.pickup_lat, trip.pickup_lng)
    )


def rank_drivers(trip, drivers=None):
    """Eligible drivers, nearest first, with the reason they placed where they did.

    Drivers with a fresh position sort by distance. Drivers without one sort
    after them by workload, because an unknown position is not evidence of
    being far away -- it just can't be used to prefer them.
    """
    queryset = eligible_drivers(trip) if drivers is None else drivers
    queryset = queryset.select_related("user", "location").annotate(
        active_trip_count=Count(
            "assigned_trips", filter=Q(assigned_trips__status__in=ACTIVE_STATUSES)
        )
    )

    ranked = []
    for driver in queryset:
        miles = distance_to_pickup(driver, trip)
        ranked.append(
            {
                "driver": driver,
                "miles_away": miles,
                "active_trip_count": driver.active_trip_count,
                "is_available": driver.is_available,
            }
        )

    ranked.sort(
        key=lambda row: (
            not row["is_available"],  # on-duty first
            row["miles_away"] is None,  # then those we can actually locate
            row["miles_away"] if row["miles_away"] is not None else 0,
            row["active_trip_count"],
            row["driver"].user.date_joined,
        )
    )
    return ranked


def find_available_driver(trip):
    """Best auto-assignment candidate: nearest on-duty driver, else the freest.

    Availability only gates auto-assignment; an admin can still manually assign
    a specific approved driver who is offline.
    """
    ranked = [row for row in rank_drivers(trip) if row["is_available"]]
    return ranked[0]["driver"] if ranked else None
