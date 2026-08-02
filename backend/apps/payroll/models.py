import uuid

from django.db import models

from apps.accounts.models import DriverProfile, User
from apps.trips.models import Trip


class DriverPayRate(models.Model):
    """What a driver earns for a completed trip: a flat amount plus a per-mile
    rate. Effective-dated and optionally scoped to one driver, so a negotiated
    rate overrides the house default without disturbing anyone else's pay, and
    historical earnings keep whatever rate was in force when the trip ran.

    Deliberately the mirror of `billing.RateSchedule` (what the *rider* is
    charged); the two move independently."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    driver = models.ForeignKey(
        DriverProfile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="pay_rates",
        help_text="Leave blank for the default rate that applies to every driver.",
    )
    per_trip_base = models.DecimalField(max_digits=8, decimal_places=2)
    per_mile_rate = models.DecimalField(max_digits=6, decimal_places=2)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-effective_from"]
        indexes = [models.Index(fields=["driver", "effective_from"])]

    def __str__(self):
        scope = self.driver_id or "DEFAULT"
        return f"DriverPayRate<{scope}@{self.effective_from}>"


class TripEarning(models.Model):
    """One row per completed trip, snapshotting the pay rate that produced it.

    Snapshotted for the same reason invoices are: changing a pay rate later must
    never silently restate what a driver was already told they earned."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trip = models.OneToOneField(Trip, on_delete=models.PROTECT, related_name="earning")
    driver = models.ForeignKey(DriverProfile, on_delete=models.PROTECT, related_name="earnings")
    pay_rate = models.ForeignKey(DriverPayRate, on_delete=models.PROTECT, related_name="earnings")

    earned_on = models.DateField(help_text="Local date the trip was completed.")
    mileage_snapshot = models.DecimalField(max_digits=6, decimal_places=2)
    per_trip_base = models.DecimalField(max_digits=8, decimal_places=2)
    per_mile_rate = models.DecimalField(max_digits=6, decimal_places=2)
    mileage_amount = models.DecimalField(max_digits=8, decimal_places=2)
    total_amount = models.DecimalField(max_digits=8, decimal_places=2)

    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="earnings_marked_paid"
    )
    payment_reference = models.CharField(max_length=100, blank=True)

    generated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="earnings_generated"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-earned_on", "-created_at"]
        indexes = [
            models.Index(fields=["driver", "earned_on"]),
            models.Index(fields=["paid_at"]),
        ]

    def __str__(self):
        return f"TripEarning<{self.driver_id}:{self.total_amount}>"

    @property
    def is_paid(self) -> bool:
        return self.paid_at is not None
