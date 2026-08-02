import uuid

from django.contrib.postgres.fields import ArrayField
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.accounts.models import DriverProfile, MobilityNeed, RiderProfile, User


class Weekday(models.IntegerChoices):
    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


class TripStatus(models.TextChoices):
    REQUESTED = "REQUESTED", "Requested"
    CONFIRMED = "CONFIRMED", "Confirmed"
    ASSIGNED = "ASSIGNED", "Assigned"
    EN_ROUTE = "EN_ROUTE", "En route"
    ARRIVED = "ARRIVED", "Arrived at pickup"
    PICKED_UP = "PICKED_UP", "Picked up"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"
    NO_SHOW = "NO_SHOW", "No-show"


class TripType(models.TextChoices):
    ONE_WAY = "ONE_WAY", "One way"
    ROUND_TRIP = "ROUND_TRIP", "Round trip"


# Legal next-states per current status. `accept`/`decline`/`reassign` bypass
# this dict entirely (they don't represent forward progress) -- keeping it
# forward-only is what makes it legible by inspection.
STATUS_TRANSITIONS: dict[str, set[str]] = {
    TripStatus.REQUESTED: {TripStatus.CONFIRMED, TripStatus.CANCELLED},
    TripStatus.CONFIRMED: {TripStatus.ASSIGNED, TripStatus.CANCELLED},
    TripStatus.ASSIGNED: {TripStatus.EN_ROUTE, TripStatus.CANCELLED},
    TripStatus.EN_ROUTE: {TripStatus.ARRIVED, TripStatus.CANCELLED},
    # A no-show can only be declared from ARRIVED: the driver has to be at the
    # door, and the wait clock that justifies the claim starts on arrival.
    TripStatus.ARRIVED: {TripStatus.PICKED_UP, TripStatus.NO_SHOW, TripStatus.CANCELLED},
    TripStatus.PICKED_UP: {TripStatus.COMPLETED, TripStatus.CANCELLED},
    TripStatus.COMPLETED: set(),
    TripStatus.CANCELLED: set(),
    TripStatus.NO_SHOW: set(),
}


class RecurringTripSeries(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rider = models.ForeignKey(
        RiderProfile, on_delete=models.CASCADE, related_name="recurring_series"
    )
    pickup_address = models.CharField(max_length=255)
    pickup_lat = models.DecimalField(max_digits=9, decimal_places=6)
    pickup_lng = models.DecimalField(max_digits=9, decimal_places=6)
    dropoff_address = models.CharField(max_length=255)
    dropoff_lat = models.DecimalField(max_digits=9, decimal_places=6)
    dropoff_lng = models.DecimalField(max_digits=9, decimal_places=6)
    mileage = models.DecimalField(max_digits=6, decimal_places=2)
    distance_estimated = models.BooleanField(default=False)
    pickup_time = models.TimeField()
    weekdays = ArrayField(models.PositiveSmallIntegerField(choices=Weekday.choices))
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    mobility_need = models.CharField(max_length=20, choices=MobilityNeed.choices, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Newest first, and deterministic: an unordered queryset makes paginated
        # results shuffle between pages.
        ordering = ["-created_at"]

    def __str__(self):
        return f"RecurringTripSeries<{self.rider.user.email}>"


class Trip(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rider = models.ForeignKey(RiderProfile, on_delete=models.PROTECT, related_name="trips")
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="trips_created"
    )
    recurring_series = models.ForeignKey(
        RecurringTripSeries,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trips",
    )
    status = models.CharField(
        max_length=10, choices=TripStatus.choices, default=TripStatus.REQUESTED, db_index=True
    )
    scheduled_pickup_time = models.DateTimeField(db_index=True)
    pickup_address = models.CharField(max_length=255)
    pickup_lat = models.DecimalField(max_digits=9, decimal_places=6)
    pickup_lng = models.DecimalField(max_digits=9, decimal_places=6)
    dropoff_address = models.CharField(max_length=255)
    dropoff_lat = models.DecimalField(max_digits=9, decimal_places=6)
    dropoff_lng = models.DecimalField(max_digits=9, decimal_places=6)
    mileage = models.DecimalField(max_digits=6, decimal_places=2)
    # True when mileage came from the offline haversine estimate rather than a
    # measured Google route. Surfaced wherever the figure is billed or paid on,
    # so nobody mistakes a computed distance for a driven one.
    distance_estimated = models.BooleanField(default=False)
    estimated_duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    mobility_need = models.CharField(max_length=20, choices=MobilityNeed.choices, blank=True)
    # People travelling with the rider (family, aide, interpreter). They occupy
    # seats, so assignment has to know about them before it picks a vehicle.
    escort_count = models.PositiveSmallIntegerField(default=0)
    notes = models.TextField(blank=True)

    # --- round trips -------------------------------------------------------
    # A round trip is two Trip rows, not one row with two times: each leg is
    # separately dispatched, driven, and billed, and the return leg routinely
    # gets a different driver. `outbound_trip` links the pair.
    trip_type = models.CharField(max_length=12, choices=TripType.choices, default=TripType.ONE_WAY)
    outbound_trip = models.OneToOneField(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="return_trip",
        help_text="Set on the return leg, pointing at the outbound leg.",
    )
    # Will-call: the rider doesn't know when the appointment will end, so the
    # scheduled time is a placeholder and dispatch waits to be called. Cleared
    # when the rider requests the ride.
    is_will_call = models.BooleanField(default=False)
    will_call_requested_at = models.DateTimeField(null=True, blank=True)

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trips_cancelled",
    )
    cancellation_reason = models.CharField(max_length=255, blank=True)

    assigned_driver = models.ForeignKey(
        DriverProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_trips",
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trips_assigned",
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.CharField(max_length=255, blank=True)
    en_route_at = models.DateTimeField(null=True, blank=True)
    # When the driver reached the pickup point. This is the moment the no-show
    # wait clock starts, so it is what makes a no-show claim defensible.
    arrived_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    no_show_at = models.DateTimeField(null=True, blank=True)
    no_show_reason = models.CharField(max_length=255, blank=True)
    # Minutes actually waited at the door, computed from arrived_at at the moment
    # the no-show was filed. Snapshotted because it is evidence on a claim.
    no_show_waited_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    odometer_start = models.PositiveIntegerField(null=True, blank=True)
    odometer_end = models.PositiveIntegerField(null=True, blank=True)
    completion_attestation = models.CharField(max_length=255, blank=True)
    # Drawn signature captured on the driver's screen at drop-off. The typed
    # attestation above stays as the readable name; this is the mark itself,
    # and it is what a Medicaid claim references.
    signature_image = models.ImageField(upload_to="trip_signatures/%Y/%m/", null=True, blank=True)

    # Rider's post-trip rating of the driver. Only set once, after the trip is
    # COMPLETED; feeds each driver's average performance rating.
    rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    review = models.CharField(max_length=500, blank=True)
    rated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_pickup_time"]
        indexes = [
            models.Index(fields=["rider", "scheduled_pickup_time"]),
            models.Index(fields=["assigned_driver", "scheduled_pickup_time"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["recurring_series", "scheduled_pickup_time"],
                condition=models.Q(recurring_series__isnull=False),
                name="uniq_series_trip_per_slot",
            )
        ]

    def __str__(self):
        return f"Trip<{self.rider.user.email}@{self.scheduled_pickup_time}>"
