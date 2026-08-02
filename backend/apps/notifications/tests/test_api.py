import pytest

from apps.accounts.tests.factories import RiderFactory
from apps.notifications.models import Notification, NotificationCategory

pytestmark = pytest.mark.django_db


def _mk(user, **kwargs):
    return Notification.objects.create(
        recipient=user,
        category=NotificationCategory.TRIP_CONFIRMED,
        title="Title",
        body="Body",
        **kwargs,
    )


def test_list_only_returns_own_notifications(client, _auth):
    me = RiderFactory()
    other = RiderFactory()
    _mk(me)
    _mk(other)
    _auth(client, me)

    response = client.get("/api/notifications/")

    assert response.status_code == 200
    assert response.data["count"] == 1


def test_unread_filter_and_count(client, _auth):
    me = RiderFactory()
    _mk(me)
    _mk(me, is_read=True)
    _auth(client, me)

    assert client.get("/api/notifications/unread-count/").data["unread_count"] == 1
    assert client.get("/api/notifications/?unread=true").data["count"] == 1


def test_mark_read(client, _auth):
    me = RiderFactory()
    notification = _mk(me)
    _auth(client, me)

    response = client.post(f"/api/notifications/{notification.id}/mark-read/")

    assert response.status_code == 200
    notification.refresh_from_db()
    assert notification.is_read is True


def test_mark_all_read(client, _auth):
    me = RiderFactory()
    _mk(me)
    _mk(me)
    _auth(client, me)

    response = client.post("/api/notifications/mark-all-read/")

    assert response.status_code == 200
    assert Notification.objects.filter(recipient=me, is_read=False).count() == 0


def test_cannot_mark_another_users_notification(client, _auth):
    me = RiderFactory()
    other = RiderFactory()
    notification = _mk(other)
    _auth(client, me)

    response = client.post(f"/api/notifications/{notification.id}/mark-read/")

    assert response.status_code == 404


def test_update_preferences(client, _auth):
    me = RiderFactory()
    _auth(client, me)

    response = client.patch(
        "/api/notifications/preferences/", {"sms_enabled": False}, format="json"
    )

    assert response.status_code == 200
    assert response.data["sms_enabled"] is False


def test_public_config_is_open(client):
    response = client.get("/api/public-config/")
    assert response.status_code == 200
    assert "google_maps_browser_key" in response.data
