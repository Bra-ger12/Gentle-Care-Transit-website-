"""Operator-configurable policy: where the service runs, and the rules it runs by.

These are the knobs an administrator turns without a deploy. Everything here is
read at the point of use rather than cached at import, so a change on the
settings screen takes effect on the next request.
"""

import uuid

from django.core.exceptions import ValidationError
from django.db import models

from apps.accounts.models import User


class ServiceAreaKind(models.TextChoices):
    PLACE = "PLACE", "Town or city"
    RADIUS = "RADIUS", "Radius around a point"


class ServiceArea(models.Model):
    """One rule describing somewhere the service will pick up and drop off.

    Two kinds, because North Dakota needs both. `PLACE` names a town outright,
    which is how a city council or a county's seat list is expressed. `RADIUS`
    covers everything within N miles of a point, which is how you describe a
    county or a catchment area without enumerating every hamlet in it.

    An address must satisfy at least one active rule at *both* ends to be
    bookable. With no active rules at all, the service area is unrestricted --
    that is the default a fresh install starts in.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(
        max_length=120, help_text="How this area appears on the settings screen."
    )
    kind = models.CharField(max_length=10, choices=ServiceAreaKind.choices)

    place = models.CharField(
        max_length=120,
        blank=True,
        help_text="Town name for a PLACE rule, e.g. 'Bismarck'.",
    )
    center_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    center_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    radius_miles = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"ServiceArea<{self.name}>"

    def clean(self):
        if self.kind == ServiceAreaKind.PLACE and not self.place:
            raise ValidationError({"place": "A town rule needs a town name."})
        if self.kind == ServiceAreaKind.RADIUS and (
            self.center_lat is None or self.center_lng is None or not self.radius_miles
        ):
            raise ValidationError(
                {"radius_miles": "A radius rule needs a centre point and a radius."}
            )


class SystemSetting(models.Model):
    """Singleton row holding the policy an operator can change at runtime.

    A single row (pk=1) rather than a key/value table: these settings are few,
    typed, and always read together, so a table with real columns validates
    itself and reads in one query.
    """

    SINGLETON_PK = 1

    id = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON_PK, editable=False)

    enforce_service_area = models.BooleanField(
        default=True,
        help_text="Turn off to accept bookings anywhere, ignoring the areas below.",
    )
    cancellation_cutoff_hours = models.PositiveSmallIntegerField(
        default=24,
        help_text="How long before pickup a rider may still cancel or reschedule. "
        "Admins are never subject to this.",
    )
    require_verified_email_to_book = models.BooleanField(
        default=True,
        help_text="Riders must confirm their email address before booking. Turn off "
        "if you take bookings from people without reliable email.",
    )
    booking_lead_time_minutes = models.PositiveSmallIntegerField(
        default=60,
        help_text="Minimum notice for a new booking. 0 allows booking right up to now.",
    )
    no_show_wait_minutes = models.PositiveSmallIntegerField(
        default=10,
        help_text="How long a driver must wait at the door before a no-show may be filed.",
    )

    # Message bodies for rider-facing notifications. Blank means "use the wording
    # built into the app". Placeholders are filled from the trip; an unknown
    # placeholder is left as literal text rather than raising.
    template_trip_confirmed = models.TextField(blank=True)
    template_driver_assigned = models.TextField(blank=True)
    template_driver_en_route = models.TextField(blank=True)
    template_trip_reminder = models.TextField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    def __str__(self):
        return "SystemSetting"

    def save(self, *args, **kwargs):
        self.id = self.SINGLETON_PK
        return super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "SystemSetting":
        """The settings row, created with defaults on first use."""
        setting, _ = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return setting
