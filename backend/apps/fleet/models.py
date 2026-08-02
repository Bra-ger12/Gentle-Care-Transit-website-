import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.accounts.models import DriverProfile, User


class InspectionType(models.TextChoices):
    PRE_TRIP = "PRE_TRIP", "Pre-trip"
    POST_TRIP = "POST_TRIP", "Post-trip"


class DefectItem(models.TextChoices):
    """The checklist a driver walks. The wheelchair lift, securements and oxygen
    items are what make this an NEMT inspection rather than a generic one."""

    BRAKES = "BRAKES", "Brakes"
    STEERING = "STEERING", "Steering"
    TIRES = "TIRES", "Tires & wheels"
    LIGHTS = "LIGHTS", "Lights & reflectors"
    MIRRORS = "MIRRORS", "Mirrors & glass"
    WIPERS = "WIPERS", "Windshield wipers"
    HORN = "HORN", "Horn"
    SEATBELTS = "SEATBELTS", "Seat belts"
    FLUIDS = "FLUIDS", "Fluid levels & leaks"
    BODY = "BODY", "Body, doors & steps"
    WHEELCHAIR_LIFT = "WHEELCHAIR_LIFT", "Wheelchair lift / ramp"
    SECUREMENTS = "SECUREMENTS", "Wheelchair securements"
    OXYGEN_MOUNT = "OXYGEN_MOUNT", "Oxygen tank mount"
    EMERGENCY_KIT = "EMERGENCY_KIT", "First aid & emergency equipment"
    CLEANLINESS = "CLEANLINESS", "Interior cleanliness / sanitation"


class VehicleInspection(models.Model):
    """A Driver Vehicle Inspection Report. The driver records the vehicle's
    condition before or after a shift; anything they flag is a defect an admin
    has to clear before the vehicle is used again.

    The plate is snapshotted because a driver can be reassigned a different
    vehicle later, and this report describes the one they inspected."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    driver = models.ForeignKey(DriverProfile, on_delete=models.PROTECT, related_name="inspections")
    inspection_type = models.CharField(max_length=10, choices=InspectionType.choices)
    performed_at = models.DateTimeField()
    inspected_on = models.DateField(help_text="Local date of the inspection.")

    vehicle_plate_snapshot = models.CharField(max_length=20, blank=True)
    vehicle_type_snapshot = models.CharField(max_length=20, blank=True)
    odometer = models.PositiveIntegerField()

    defects = ArrayField(
        models.CharField(max_length=20, choices=DefectItem.choices),
        default=list,
        blank=True,
        help_text="Items found defective. Empty means no defects noted.",
    )
    defect_notes = models.TextField(blank=True)
    safe_to_operate = models.BooleanField()
    signature = models.CharField(
        max_length=150, help_text="Typed name of the driver certifying this report."
    )

    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="inspections_reviewed"
    )
    resolution_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-performed_at"]
        indexes = [
            models.Index(fields=["driver", "inspected_on"]),
            models.Index(fields=["safe_to_operate", "reviewed_at"]),
        ]
        constraints = [
            # One pre-trip and one post-trip per driver per day: re-submitting
            # should correct that day's report, not stack duplicates.
            models.UniqueConstraint(
                fields=["driver", "inspected_on", "inspection_type"],
                name="unique_inspection_per_driver_day_type",
            )
        ]

    def __str__(self):
        return f"VehicleInspection<{self.driver_id}:{self.inspected_on}:{self.inspection_type}>"

    @property
    def has_defects(self) -> bool:
        return bool(self.defects)

    @property
    def needs_attention(self) -> bool:
        """Unreviewed reports that flagged something, or grounded the vehicle."""
        return self.reviewed_at is None and (self.has_defects or not self.safe_to_operate)
