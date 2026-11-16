"""The runtime policy knobs, and the behaviour that reads them."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import AdminFactory, RiderProfileFactory
from apps.notifications.models import Notification, NotificationCategory
from apps.operations.models import SystemSetting
from apps.operations.services import render_template
from apps.trips.tests.factories import ServiceFactory, TripFactory

pytestmark = pytest.mark.django_db

BISMARCK = "1420 Boulevard Ave, Bismarck, ND"
CLINIC = "Sanford Health, 300 N 7th St, Bismarck, ND"


def test_settings_start_at_sensible_defaults():
    setting = SystemSetting.load()
    assert setting.cancellation_cutoff_hours == 24
    assert setting.no_show_wait_minutes == 10
    assert setting.enforce_service_area is True


def test_load_is_a_singleton():
    first = SystemSetting.load()
    first.cancellation_cutoff_hours = 6
    first.save()
    assert SystemSetting.load().pk == first.pk
    assert SystemSetting.objects.count() == 1


def test_only_admins_may_read_or_change_settings(client, _auth):
    profile = RiderProfileFactory()
    _auth(client, profile.user)
    assert client.get("/api/operations/settings/").status_code == 403
    assert (
        client.patch(
            "/api/operations/settings/", {"cancellation_cutoff_hours": 2}, format="json"
        ).status_code
        == 403
    )


def test_admin_can_change_the_cancellation_cutoff(client, _auth):
    admin = AdminFactory()
    _auth(client, admin)

    response = client.patch(
        "/api/operations/settings/", {"cancellation_cutoff_hours": 4}, format="json"
    )

    assert response.status_code == 200, response.data
    assert SystemSetting.load().cancellation_cutoff_hours == 4


def test_the_configured_cutoff_is_what_blocks_a_rider_cancellation(client, _auth):
    setting = SystemSetting.load()
    setting.cancellation_cutoff_hours = 48
    setting.save()

    profile = RiderProfileFactory()
    trip = TripFactory(rider=profile, scheduled_pickup_time=timezone.now() + timedelta(hours=30))
    _auth(client, profile.user)

    response = client.post(f"/api/trips/{trip.id}/cancel/", {}, format="json")

    assert response.status_code == 400
    assert "48 hours" in str(response.data)


def test_a_shorter_cutoff_lets_the_same_cancellation_through(client, _auth):
    setting = SystemSetting.load()
    setting.cancellation_cutoff_hours = 4
    setting.save()

    profile = RiderProfileFactory()
    trip = TripFactory(rider=profile, scheduled_pickup_time=timezone.now() + timedelta(hours=30))
    _auth(client, profile.user)

    response = client.post(f"/api/trips/{trip.id}/cancel/", {}, format="json")
    assert response.status_code == 200, response.data


def test_booking_lead_time_is_enforced(client, _auth):
    setting = SystemSetting.load()
    setting.booking_lead_time_minutes = 120
    setting.save()

    profile = RiderProfileFactory()
    service = ServiceFactory()
    _auth(client, profile.user)

    response = client.post(
        "/api/trips/",
        {
            "scheduled_pickup_time": (timezone.now() + timedelta(minutes=30)).isoformat(),
            "pickup_address": BISMARCK,
            "dropoff_address": CLINIC,
            "service_id": str(service.id),
        },
        format="json",
    )

    assert response.status_code == 400
    assert "120 minutes" in str(response.data)


def test_an_absurd_cutoff_is_rejected(client, _auth):
    admin = AdminFactory()
    _auth(client, admin)
    response = client.patch(
        "/api/operations/settings/", {"cancellation_cutoff_hours": 400}, format="json"
    )
    assert response.status_code == 400


def test_a_two_hour_driver_wait_is_rejected(client, _auth):
    admin = AdminFactory()
    _auth(client, admin)
    response = client.patch(
        "/api/operations/settings/", {"no_show_wait_minutes": 300}, format="json"
    )
    assert response.status_code == 400


# --- message templates ---------------------------------------------------


def test_blank_template_uses_the_built_in_wording():
    assert render_template("template_trip_confirmed", "built in", {}) == "built in"


def test_template_placeholders_are_filled():
    setting = SystemSetting.load()
    setting.template_trip_confirmed = "Ride {when} from {pickup}."
    setting.save()

    rendered = render_template(
        "template_trip_confirmed", "built in", {"when": "Mon", "pickup": "Home"}
    )
    assert rendered == "Ride Mon from Home."


def test_a_typo_in_a_template_does_not_break_the_notification():
    """An unknown placeholder must not stop a rider being told about their trip."""
    setting = SystemSetting.load()
    setting.template_trip_confirmed = "Ride {nonsense}."
    setting.save()

    assert render_template("template_trip_confirmed", "built in", {"when": "Mon"}) == (
        "Ride {nonsense}."
    )


def test_operator_template_reaches_the_rider(client, _auth):
    setting = SystemSetting.load()
    setting.template_trip_confirmed = "Confirmed for {when}. Call 701-555-0100 to change it."
    setting.save()

    admin = AdminFactory()
    trip = TripFactory(status="REQUESTED")
    _auth(client, admin)

    response = client.post(f"/api/trips/{trip.id}/confirm/", {}, format="json")

    assert response.status_code == 200, response.data
    notification = Notification.objects.get(
        recipient=trip.rider.user, category=NotificationCategory.TRIP_CONFIRMED
    )
    assert "Call 701-555-0100" in notification.body
