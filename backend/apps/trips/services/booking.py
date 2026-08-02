"""Composing a booking out of trips.

A round trip is two Trip rows. The alternative -- one row carrying two pickup
times -- falls apart the moment dispatch needs to send a different driver home
than out, which is the normal case when an appointment overruns.
"""

from datetime import timedelta

from ..models import Trip, TripStatus, TripType

# How long after drop-off a will-call return is provisionally pencilled in for.
# It is only a placeholder to keep the leg on the schedule; the real time is set
# when the rider calls. Two hours is a typical dialysis or specialist visit.
WILL_CALL_PLACEHOLDER_HOURS = 2


def default_return_time(outbound: Trip):
    """Provisional pickup time for a will-call return leg."""
    travel = timedelta(minutes=outbound.estimated_duration_minutes or 30)
    return outbound.scheduled_pickup_time + travel + timedelta(hours=WILL_CALL_PLACEHOLDER_HOURS)


def create_return_leg(outbound: Trip, return_time=None, is_will_call: bool = False) -> Trip:
    """Build the homeward leg of a round trip.

    The route is the outbound one reversed, so the coordinates and mileage are
    carried across rather than geocoded again -- same two points, same distance,
    and one fewer chance for the two legs to disagree about where the rider lives.
    """
    scheduled = default_return_time(outbound) if is_will_call else return_time

    return Trip.objects.create(
        rider=outbound.rider,
        created_by=outbound.created_by,
        status=TripStatus.REQUESTED,
        trip_type=TripType.ROUND_TRIP,
        outbound_trip=outbound,
        is_will_call=is_will_call,
        scheduled_pickup_time=scheduled,
        pickup_address=outbound.dropoff_address,
        pickup_lat=outbound.dropoff_lat,
        pickup_lng=outbound.dropoff_lng,
        dropoff_address=outbound.pickup_address,
        dropoff_lat=outbound.pickup_lat,
        dropoff_lng=outbound.pickup_lng,
        mileage=outbound.mileage,
        distance_estimated=outbound.distance_estimated,
        estimated_duration_minutes=outbound.estimated_duration_minutes,
        mobility_need=outbound.mobility_need,
        escort_count=outbound.escort_count,
        notes=outbound.notes,
    )
