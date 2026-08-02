import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import RiderFactory
from apps.billing.tests.factories import RateScheduleFactory

pytestmark = pytest.mark.django_db


def _admin():
    return RiderFactory(role=Role.ADMIN, is_staff=True)


def test_admin_can_create_rate_schedule(client, _auth):
    _auth(client, _admin())

    response = client.post(
        "/api/billing/rate-schedules/",
        {
            "mobility_need": "WHEELCHAIR",
            "base_fare": "10.00",
            "per_mile_rate": "3.00",
            "effective_from": "2026-01-01",
            "is_active": True,
        },
    )

    assert response.status_code == 201, response.data
    assert response.data["mobility_need"] == "WHEELCHAIR"


def test_non_admin_cannot_create_rate_schedule(client, _auth):
    _auth(client, RiderFactory())

    response = client.post(
        "/api/billing/rate-schedules/",
        {"base_fare": "10.00", "per_mile_rate": "3.00", "effective_from": "2026-01-01"},
    )

    assert response.status_code == 403


def test_admin_can_list_rate_schedules(client, _auth):
    RateScheduleFactory()
    RateScheduleFactory()
    _auth(client, _admin())

    response = client.get("/api/billing/rate-schedules/")

    assert response.status_code == 200
    assert response.data["count"] == 2


def test_admin_can_update_rate_schedule(client, _auth):
    schedule = RateScheduleFactory(is_active=True)
    _auth(client, _admin())

    response = client.patch(f"/api/billing/rate-schedules/{schedule.id}/", {"is_active": False})

    assert response.status_code == 200
    schedule.refresh_from_db()
    assert schedule.is_active is False
