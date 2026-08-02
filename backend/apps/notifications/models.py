import uuid

from django.conf import settings
from django.db import models


class NotificationCategory(models.TextChoices):
    TRIP_CONFIRMED = "TRIP_CONFIRMED", "Trip confirmed"
    TRIP_ASSIGNED = "TRIP_ASSIGNED", "Trip assigned"
    TRIP_ACCEPTED = "TRIP_ACCEPTED", "Trip accepted"
    TRIP_DECLINED = "TRIP_DECLINED", "Trip declined"
    DRIVER_EN_ROUTE = "DRIVER_EN_ROUTE", "Driver en route"
    DRIVER_ARRIVED = "DRIVER_ARRIVED", "Driver arrived"
    DRIVER_PICKED_UP = "DRIVER_PICKED_UP", "Rider picked up"
    TRIP_COMPLETED = "TRIP_COMPLETED", "Trip completed"
    TRIP_CANCELLED = "TRIP_CANCELLED", "Trip cancelled"
    TRIP_NO_SHOW = "TRIP_NO_SHOW", "Trip no-show"
    TRIP_REMINDER = "TRIP_REMINDER", "Trip reminder"
    DOC_EXPIRY = "DOC_EXPIRY", "Document expiry"
    DRIVER_APPROVED = "DRIVER_APPROVED", "Driver approved"
    WILL_CALL = "WILL_CALL", "Will-call return requested"


class Notification(models.Model):
    """A single in-app notification. Email/SMS are fire-and-forget side channels;
    this row is the durable, user-visible record shown in the notification bell."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    category = models.CharField(max_length=20, choices=NotificationCategory.choices)
    title = models.CharField(max_length=150)
    body = models.TextField(blank=True)
    related_trip = models.ForeignKey(
        "trips.Trip",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    is_read = models.BooleanField(default=False, db_index=True)
    # Set for scheduled/system sends (reminders, expiry alerts) to make them
    # idempotent -- a repeated sweep with the same key is a no-op. Empty for
    # event-driven sends (each trip transition is its own distinct event).
    dedupe_key = models.CharField(max_length=100, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
        ]

    def __str__(self):
        return f"Notification<{self.recipient_id}:{self.category}>"


class NotificationPreference(models.Model):
    """Per-user opt-outs for the side channels. In-app notifications are always on
    (they're the durable record); email and SMS default on and can be disabled."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
    )
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"NotificationPreference<{self.user_id}>"

    @classmethod
    def for_user(cls, user):
        pref, _ = cls.objects.get_or_create(user=user)
        return pref
