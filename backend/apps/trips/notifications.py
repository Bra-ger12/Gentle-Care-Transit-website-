"""Bridge from trip lifecycle events to the notifications app.

Separated from views so the dependency runs one way (trips -> notifications) and so
every hook is best-effort: a notification or broadcast failure must never roll back
or 500 a trip status change. Each public hook is wrapped by `_guard`, which logs and
swallows anything that goes wrong.
"""

import logging
from functools import wraps

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.accounts.models import Role
from apps.notifications.models import NotificationCategory
from apps.notifications.services import broadcast_dispatch, broadcast_trip, notify
from apps.operations.services import render_template

from .models import TripStatus

logger = logging.getLogger(__name__)


def _guard(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:  # noqa: BLE001
            logger.exception("trip notification hook %s failed", fn.__name__)

    return wrapper


def _route(trip) -> str:
    return f"{trip.pickup_address} → {trip.dropoff_address}"


def _when(trip) -> str:
    local = timezone.localtime(trip.scheduled_pickup_time)
    # %-I isn't portable (fails on Windows); strip the leading zero by hand.
    return local.strftime("%a %b %d, ") + local.strftime("%I:%M %p").lstrip("0")


def _driver_name(trip):
    return trip.assigned_driver.user.get_full_name() if trip.assigned_driver else None


def _context(trip) -> dict:
    """Placeholders an operator may use in a message template."""
    return {
        "when": _when(trip),
        "route": _route(trip),
        "pickup": trip.pickup_address,
        "dropoff": trip.dropoff_address,
        "driver": _driver_name(trip) or "Your driver",
        "rider": trip.rider.user.get_full_name(),
    }


def _body(field: str, default: str, trip) -> str:
    """The operator's wording for this message, or the app's own."""
    return render_template(field, default, _context(trip))


def _status_payload(trip) -> dict:
    return {
        "event": "status_update",
        "status": trip.status,
        "assigned_driver_name": _driver_name(trip),
    }


def _dispatch_payload(trip) -> dict:
    return {"event": "trip_updated", "trip_id": str(trip.id), "status": trip.status}


def _admins():
    User = get_user_model()
    return User.objects.filter(role=Role.ADMIN, is_active=True)


@_guard
def trip_created(trip):
    """A rider booked a trip -- nudge the dispatch board."""
    broadcast_dispatch(_dispatch_payload(trip))


@_guard
def status_changed(trip, actor):
    """Fired for every forward transition routed through `_apply_transition`
    (confirm, assign/auto-assign, en-route, picked-up, complete, no-show, cancel)."""
    broadcast_trip(trip.id, _status_payload(trip))
    broadcast_dispatch(_dispatch_payload(trip))

    status = trip.status
    if status == TripStatus.CONFIRMED:
        notify(
            trip.rider.user,
            category=NotificationCategory.TRIP_CONFIRMED,
            title="Trip confirmed",
            body=_body(
                "template_trip_confirmed",
                f"Your trip on {_when(trip)} is confirmed. {_route(trip)}.",
                trip,
            ),
            related_trip=trip,
        )
    elif status == TripStatus.ASSIGNED and trip.assigned_driver:
        notify(
            trip.assigned_driver.user,
            category=NotificationCategory.TRIP_ASSIGNED,
            title="New trip assigned",
            body=_body(
                "template_driver_assigned",
                f"You've been assigned a trip on {_when(trip)}. {_route(trip)}. "
                "Open it to accept or decline.",
                trip,
            ),
            related_trip=trip,
        )
    elif status == TripStatus.EN_ROUTE:
        notify(
            trip.rider.user,
            category=NotificationCategory.DRIVER_EN_ROUTE,
            title="Your driver is on the way",
            body=_body(
                "template_driver_en_route",
                f"{_driver_name(trip)} is en route for your {_when(trip)} pickup. "
                "Track them live from your trip page.",
                trip,
            ),
            related_trip=trip,
        )
    elif status == TripStatus.ARRIVED:
        notify(
            trip.rider.user,
            category=NotificationCategory.DRIVER_ARRIVED,
            title="Your driver is outside",
            body=f"{_driver_name(trip)} has arrived at {trip.pickup_address}.",
            related_trip=trip,
        )
    elif status == TripStatus.PICKED_UP:
        notify(
            trip.rider.user,
            category=NotificationCategory.DRIVER_PICKED_UP,
            title="You're on your way",
            body=f"You've been picked up. {_route(trip)}.",
            related_trip=trip,
        )
    elif status == TripStatus.COMPLETED:
        notify(
            trip.rider.user,
            category=NotificationCategory.TRIP_COMPLETED,
            title="Trip completed",
            body="Your trip is complete. Open it to rate your ride.",
            related_trip=trip,
        )
    elif status == TripStatus.NO_SHOW:
        notify(
            trip.rider.user,
            category=NotificationCategory.TRIP_NO_SHOW,
            title="Trip marked no-show",
            body=f"Your {_when(trip)} trip was marked a no-show. "
            "Contact dispatch if this is a mistake.",
            related_trip=trip,
        )
    elif status == TripStatus.CANCELLED:
        _notify_cancellation(trip, actor)


def _notify_cancellation(trip, actor):
    reason = trip.cancellation_reason or "No reason given"
    recipients = []
    if trip.rider.user_id != actor.id:
        recipients.append(trip.rider.user)
    if trip.assigned_driver and trip.assigned_driver.user_id != actor.id:
        recipients.append(trip.assigned_driver.user)
    for recipient in recipients:
        notify(
            recipient,
            category=NotificationCategory.TRIP_CANCELLED,
            title="Trip cancelled",
            body=f"The {_when(trip)} trip was cancelled. {_route(trip)}. Reason: {reason}.",
            related_trip=trip,
        )


@_guard
def trip_accepted(trip):
    broadcast_trip(trip.id, _status_payload(trip))
    broadcast_dispatch(_dispatch_payload(trip))
    notify(
        trip.rider.user,
        category=NotificationCategory.TRIP_ACCEPTED,
        title="Driver confirmed",
        body=f"{_driver_name(trip)} accepted your {_when(trip)} trip.",
        related_trip=trip,
    )


@_guard
def trip_declined(trip):
    broadcast_dispatch(_dispatch_payload(trip))
    # The driver's reason is what tells dispatch whether to reassign or rebook.
    reason = trip.decline_reason or "No reason given"
    for admin in _admins():
        notify(
            admin,
            category=NotificationCategory.TRIP_DECLINED,
            title="Driver declined a trip",
            body=f"A driver declined the {_when(trip)} trip. It needs reassignment. "
            f"{_route(trip)}. Reason: {reason}.",
            related_trip=trip,
        )


@_guard
def trip_rescheduled(trip, previous_time, released_driver=None):
    """Everyone whose plans just changed gets told, including the driver who
    was released -- they had this slot blocked out."""
    broadcast_trip(trip.id, _status_payload(trip))
    broadcast_dispatch(_dispatch_payload(trip))

    was = timezone.localtime(previous_time)
    moved = was.strftime("%a %b %d, ") + was.strftime("%I:%M %p").lstrip("0")

    notify(
        trip.rider.user,
        category=NotificationCategory.TRIP_CONFIRMED,
        title="Trip moved",
        body=f"Your {moved} trip has been moved to {_when(trip)}. {_route(trip)}.",
        related_trip=trip,
    )
    if released_driver is not None:
        notify(
            released_driver.user,
            category=NotificationCategory.TRIP_CANCELLED,
            title="Trip removed from your schedule",
            body=f"The {moved} trip was rescheduled to {_when(trip)} and is back "
            "with dispatch. It is no longer on your manifest.",
            related_trip=trip,
        )


@_guard
def will_call_requested(trip):
    """A rider has finished their appointment and wants collecting now."""
    broadcast_dispatch(_dispatch_payload(trip))
    for admin in _admins():
        notify(
            admin,
            category=NotificationCategory.WILL_CALL,
            title="Will-call return requested",
            body=f"{trip.rider.user.get_full_name()} is ready to be collected from "
            f"{trip.pickup_address}. Assign a driver.",
            related_trip=trip,
        )


@_guard
def trip_reassigned(trip):
    broadcast_trip(trip.id, _status_payload(trip))
    broadcast_dispatch(_dispatch_payload(trip))
    if trip.assigned_driver:
        notify(
            trip.assigned_driver.user,
            category=NotificationCategory.TRIP_ASSIGNED,
            title="New trip assigned",
            body=f"You've been assigned a trip on {_when(trip)}. {_route(trip)}. "
            "Open it to accept or decline.",
            related_trip=trip,
        )
