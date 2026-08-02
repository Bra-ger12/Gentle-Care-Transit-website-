from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.accounts.models import DriverProfile, Role
from apps.trips.models import Trip, TripStatus

from .models import NotificationCategory
from .services import notify

# Two escalating reminder windows before pickup. Each (trip, window) pair is sent
# at most once, enforced by the dedupe_key -- so a 15-min beat sweep is safe to run
# repeatedly without spamming riders.
REMINDER_WINDOWS = [("24h", timedelta(hours=24)), ("1h", timedelta(hours=1))]
UPCOMING_STATUSES = [TripStatus.CONFIRMED, TripStatus.ASSIGNED]


@shared_task
def send_trip_reminders() -> int:
    """Notify riders (and assigned drivers) of trips coming up within each reminder
    window. Idempotent via dedupe_key; returns the number of notifications sent."""
    now = timezone.now()
    sent = 0
    for label, delta in REMINDER_WINDOWS:
        trips = Trip.objects.select_related("rider__user", "assigned_driver__user").filter(
            status__in=UPCOMING_STATUSES,
            scheduled_pickup_time__gt=now,
            scheduled_pickup_time__lte=now + delta,
        )
        for trip in trips:
            # %-I is unavailable on Windows; format hour manually for portability.
            local = timezone.localtime(trip.scheduled_pickup_time)
            when = local.strftime("%a %b %d, ") + local.strftime("%I:%M %p").lstrip("0")
            route = f"{trip.pickup_address} → {trip.dropoff_address}"

            if notify(
                trip.rider.user,
                category=NotificationCategory.TRIP_REMINDER,
                title="Upcoming trip reminder",
                body=f"Your trip is scheduled for {when}. {route}.",
                sms_body=f"Gentle Care Transit: your ride is {when}. {route}.",
                related_trip=trip,
                dedupe_key=f"reminder:{trip.id}:{label}:rider",
            ):
                sent += 1

            if trip.assigned_driver and notify(
                trip.assigned_driver.user,
                category=NotificationCategory.TRIP_REMINDER,
                title="Upcoming pickup reminder",
                body=f"You have a scheduled pickup at {when}. {route}.",
                sms_body=f"Gentle Care Transit: pickup at {when}. {route}.",
                related_trip=trip,
                dedupe_key=f"reminder:{trip.id}:{label}:driver",
            ):
                sent += 1
    return sent


@shared_task
def check_document_expiry() -> int:
    """Alert drivers (and admins) about licenses that are expired or expiring soon.
    License is the only document with an expiry date on DriverProfile today.
    Idempotent per (driver, bucket) via dedupe_key."""
    today = timezone.localdate()
    User = get_user_model()
    admins = list(User.objects.filter(role=Role.ADMIN, is_active=True))
    sent = 0

    drivers = DriverProfile.objects.select_related("user").filter(license_expiry_date__isnull=False)
    for driver in drivers:
        days = (driver.license_expiry_date - today).days
        if days < 0:
            bucket, phrase = "expired", "has expired"
        elif days <= 7:
            bucket, phrase = "7d", f"expires in {days} day(s)"
        elif days <= 30:
            bucket, phrase = "30d", f"expires in {days} days"
        else:
            continue

        on = driver.license_expiry_date.strftime("%b %d, %Y")
        name = driver.user.get_full_name()

        if notify(
            driver.user,
            category=NotificationCategory.DOC_EXPIRY,
            title="Driver's license expiring",
            body=(
                f"Your driver's license {phrase} (on {on}). "
                "Please update it with dispatch to keep accepting trips."
            ),
            dedupe_key=f"licexp:{driver.pk}:{bucket}:driver",
        ):
            sent += 1

        for admin in admins:
            if notify(
                admin,
                category=NotificationCategory.DOC_EXPIRY,
                title="Driver license expiring",
                body=f"{name}'s driver's license {phrase} (on {on}).",
                dedupe_key=f"licexp:{driver.pk}:{bucket}:admin:{admin.pk}",
            ):
                sent += 1
    return sent
