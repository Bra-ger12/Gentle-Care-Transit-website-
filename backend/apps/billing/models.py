import uuid

from django.db import models

from apps.accounts.models import MobilityNeed, RiderProfile, User
from apps.trips.models import Trip


class RateSchedule(models.Model):
    """A configurable base-fare + per-mile rate, optionally scoped to a
    mobility tier and effective-dated so historical invoices keep whatever
    rate was in force when the trip was completed, even if rates change later."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mobility_need = models.CharField(max_length=20, choices=MobilityNeed.choices, blank=True)
    base_fare = models.DecimalField(max_digits=8, decimal_places=2)
    per_mile_rate = models.DecimalField(max_digits=6, decimal_places=2)

    # Surcharges for the mobility tiers that cost more to serve -- a lift-equipped
    # van and a two-person stretcher crew. Applied on top of the base fare when a
    # single schedule prices every tier; leave at zero if you instead keep a
    # separate schedule per mobility_need.
    wheelchair_surcharge = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    stretcher_surcharge = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    # Waiting at the door is real driver time. The first `free_wait_minutes` are
    # absorbed; past that it bills per minute. Measured from the driver marking
    # themselves arrived to the rider actually boarding.
    free_wait_minutes = models.PositiveSmallIntegerField(default=15)
    wait_time_rate_per_minute = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-effective_from"]
        indexes = [models.Index(fields=["mobility_need", "effective_from"])]

    def __str__(self):
        tier = self.mobility_need or "DEFAULT"
        return f"RateSchedule<{tier}@{self.effective_from}>"


class InvoiceStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    FINALIZED = "FINALIZED", "Finalized"
    PAID = "PAID", "Paid"
    VOID = "VOID", "Void"


class Invoice(models.Model):
    """One row per billable Trip. `trip` is a plain FK (not OneToOne) because
    a voided invoice must be reissuable -- correctness is enforced instead by
    the partial unique constraint below, which only counts non-VOID rows.

    Rider/rate details are snapshotted at generation time so later edits to
    RiderProfile or RateSchedule never retroactively change a historical
    invoice."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=20, unique=True)
    trip = models.ForeignKey(Trip, on_delete=models.PROTECT, related_name="invoices")
    rider = models.ForeignKey(RiderProfile, on_delete=models.PROTECT, related_name="invoices")
    rate_schedule = models.ForeignKey(
        RateSchedule, on_delete=models.PROTECT, related_name="invoices"
    )
    status = models.CharField(
        max_length=10, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT, db_index=True
    )

    rider_name_snapshot = models.CharField(max_length=255)
    medicaid_id_snapshot = models.CharField(max_length=50, null=True, blank=True)
    mobility_need_snapshot = models.CharField(max_length=20, blank=True)
    prior_auth_snapshot = models.CharField(max_length=50, blank=True)
    mileage_snapshot = models.DecimalField(max_digits=6, decimal_places=2)
    base_fare = models.DecimalField(max_digits=8, decimal_places=2)
    per_mile_rate = models.DecimalField(max_digits=6, decimal_places=2)
    mileage_amount = models.DecimalField(max_digits=8, decimal_places=2)
    # Mobility surcharge actually applied, and the wait actually billed. Stored
    # as amounts rather than recomputed, so a rate change never restates a
    # filed claim.
    surcharge_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    billable_wait_minutes = models.PositiveSmallIntegerField(default=0)
    wait_time_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=8, decimal_places=2)

    generated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices_generated"
    )
    finalized_at = models.DateTimeField(null=True, blank=True)
    finalized_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices_finalized"
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices_marked_paid"
    )
    payment_reference = models.CharField(max_length=100, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices_voided"
    )
    void_reason = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["rider", "created_at"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["trip"],
                condition=~models.Q(status=InvoiceStatus.VOID),
                name="uniq_active_invoice_per_trip",
            )
        ]

    def __str__(self):
        return f"Invoice<{self.invoice_number}>"

    @property
    def payer_type(self):
        return "MEDICAID" if self.medicaid_id_snapshot else "PRIVATE_PAY"
