import uuid

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.contrib.postgres.fields import ArrayField
from django.db import models

from .managers import UserManager


class Role(models.TextChoices):
    RIDER = "RIDER", "Rider"
    DRIVER = "DRIVER", "Driver"
    ADMIN = "ADMIN", "Admin"


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=10, choices=Role.choices, db_index=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.email} ({self.role})"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def get_short_name(self):
        return self.first_name or self.email


class MobilityNeed(models.TextChoices):
    AMBULATORY = "AMBULATORY", "Ambulatory"
    WHEELCHAIR = "WHEELCHAIR", "Wheelchair"
    STRETCHER = "STRETCHER", "Stretcher"
    WALKER = "WALKER", "Walker"
    OXYGEN = "OXYGEN", "Oxygen support"


class RiderProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="riderprofile")
    date_of_birth = models.DateField(null=True, blank=True)
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=2, default="ND", blank=True)
    zip_code = models.CharField(max_length=10, blank=True)
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    mobility_needs = ArrayField(
        models.CharField(max_length=20, choices=MobilityNeed.choices),
        default=list,
        blank=True,
    )
    medicaid_id = models.CharField(max_length=50, null=True, blank=True)
    # ND Medicaid requires a prior-authorisation number on NEMT claims for
    # standing/long-distance transport. Snapshotted onto each invoice at
    # generation time, so changing it here never restates a filed claim.
    prior_auth_number = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"RiderProfile<{self.user.email}>"


class BackgroundCheckStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class VehicleType(models.TextChoices):
    SEDAN = "SEDAN", "Sedan"
    WHEELCHAIR_VAN = "WHEELCHAIR_VAN", "Wheelchair van"
    STRETCHER_VAN = "STRETCHER_VAN", "Stretcher van"


class DriverProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="driverprofile")
    license_number = models.CharField(max_length=50, blank=True)
    license_expiry_date = models.DateField(null=True, blank=True)
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices, blank=True)
    vehicle_plate = models.CharField(max_length=20, blank=True)
    vehicle_capacity = models.PositiveSmallIntegerField(null=True, blank=True)
    insurance_document = models.FileField(upload_to="driver_docs/insurance/", null=True, blank=True)
    background_check_status = models.CharField(
        max_length=10,
        choices=BackgroundCheckStatus.choices,
        default=BackgroundCheckStatus.PENDING,
    )
    is_approved = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drivers_approved",
    )
    rejection_reason = models.CharField(max_length=255, blank=True)
    # Driver-controlled online/offline status. Approved drivers are online by
    # default; only online drivers are picked by auto-assignment.
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"DriverProfile<{self.user.email}>"


class DriverAvailability(models.Model):
    """One recurring shift window: "Tuesdays, 07:00-15:30".

    A driver with no windows at all is treated as always available, which is
    what every existing driver was before this existed. Once they add a single
    window, the calendar becomes authoritative and auto-assignment will only
    reach them inside it.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    driver = models.ForeignKey(
        "DriverProfile", on_delete=models.CASCADE, related_name="availability"
    )
    weekday = models.PositiveSmallIntegerField(
        choices=[
            (0, "Monday"),
            (1, "Tuesday"),
            (2, "Wednesday"),
            (3, "Thursday"),
            (4, "Friday"),
            (5, "Saturday"),
            (6, "Sunday"),
        ]
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["weekday", "start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["driver", "weekday", "start_time"],
                name="unique_driver_shift_start",
            ),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="shift_ends_after_it_starts",
            ),
        ]

    def __str__(self):
        return f"DriverAvailability<{self.driver_id}:{self.weekday}>"


class DriverTimeOff(models.Model):
    """A date range the driver is unavailable, whatever their usual shifts say.

    Holiday, illness, vehicle in the shop. Inclusive of both end dates, because
    that is how a person means "I'm off Monday to Friday".
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    driver = models.ForeignKey(
        "DriverProfile", on_delete=models.CASCADE, related_name="time_off"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="time_off_ends_after_it_starts",
            )
        ]

    def __str__(self):
        return f"DriverTimeOff<{self.driver_id}:{self.start_date}>"


class DriverLocation(models.Model):
    """The last position a driver's app reported.

    One row per driver, overwritten in place: dispatch needs "where is everyone
    now", not a movement history, and keeping a trail of a person's whereabouts
    is data we have no reason to hold. The live per-trip stream in
    apps.notifications is what drives the moving map; this is what survives
    between page loads and what nearest-driver matching reads.
    """

    driver = models.OneToOneField(
        "DriverProfile", on_delete=models.CASCADE, related_name="location", primary_key=True
    )
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    reported_at = models.DateTimeField()

    def __str__(self):
        return f"DriverLocation<{self.driver_id}>"
