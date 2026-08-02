"""Notification fan-out.

`notify()` is the single entrypoint used by the rest of the app to reach a user.
It writes the durable in-app row, then best-effort delivers over the live socket,
email, and SMS side channels -- a failure in any channel is logged and swallowed so
it can never break the HTTP request (a trip status change) that triggered it.

The `broadcast_*` helpers are thin channel-layer wrappers for realtime surfaces
(dispatch board, live trip tracking) that aren't tied to a specific recipient.
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.mail import send_mail

from .models import Notification, NotificationPreference
from .sms import send_sms

logger = logging.getLogger(__name__)

DISPATCH_GROUP = "dispatch.board"


def user_group(user_id) -> str:
    return f"notifications.user.{user_id}"


def trip_group(trip_id) -> str:
    return f"trip.{trip_id}"


def notification_to_dict(notification: Notification) -> dict:
    return {
        "id": str(notification.id),
        "category": notification.category,
        "title": notification.title,
        "body": notification.body,
        "related_trip": (
            str(notification.related_trip_id) if notification.related_trip_id else None
        ),
        "is_read": notification.is_read,
        "created_at": notification.created_at.isoformat(),
    }


def _group_send(group: str, message: dict) -> None:
    """Best-effort broadcast. Swallows channel-layer errors (e.g. Redis down in a
    Redis-backed deploy) so realtime is strictly additive to the HTTP response."""
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(group, message)
    except Exception:  # noqa: BLE001
        logger.exception("Channel broadcast to %s failed", group)


def unread_count(user) -> int:
    return Notification.objects.filter(recipient=user, is_read=False).count()


def notify(
    recipient,
    *,
    category: str,
    title: str,
    body: str = "",
    sms_body: str | None = None,
    related_trip=None,
    dedupe_key: str = "",
):
    """Create an in-app notification and fan it out to the user's side channels.

    Returns the created Notification, or None when `dedupe_key` is set and a
    notification with that key already exists (idempotent scheduled sends)."""
    if dedupe_key and Notification.objects.filter(dedupe_key=dedupe_key).exists():
        return None

    notification = Notification.objects.create(
        recipient=recipient,
        category=category,
        title=title,
        body=body,
        related_trip=related_trip,
        dedupe_key=dedupe_key,
    )

    pref = NotificationPreference.for_user(recipient)

    # In-app / live socket (always on).
    _group_send(
        user_group(recipient.id),
        {
            "type": "notification.message",
            "notification": notification_to_dict(notification),
            "unread_count": unread_count(recipient),
        },
    )

    # Email side channel.
    if pref.email_enabled and recipient.email:
        try:
            send_mail(
                subject=title,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient.email],
            )
        except Exception:  # noqa: BLE001
            logger.exception("Notification email failed (to=%s)", recipient.email)

    # SMS side channel (graceful no-op without Twilio creds).
    if pref.sms_enabled and recipient.phone_number:
        send_sms(recipient.phone_number, sms_body or f"{title} — {body}".strip(" —"))

    return notification


def broadcast_dispatch(payload: dict) -> None:
    """Nudge the admin dispatch board to refresh (trip created/assigned/status)."""
    _group_send(DISPATCH_GROUP, {"type": "dispatch.update", "payload": payload})


def broadcast_trip(trip_id, payload: dict) -> None:
    """Push a live-tracking event (status change or driver location) to everyone
    watching a specific trip."""
    _group_send(trip_group(trip_id), {"type": "trip.event", "payload": payload})
