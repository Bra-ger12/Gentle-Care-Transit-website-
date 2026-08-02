from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import BackgroundCheckStatus, Role
from apps.accounts.tests.factories import DriverProfileFactory, RiderFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def _auth(client, user):
    access = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def _admin():
    return RiderFactory(role=Role.ADMIN, is_staff=True)


def test_admin_can_list_drivers(client):
    DriverProfileFactory()
    DriverProfileFactory()
    _auth(client, _admin())

    response = client.get("/api/auth/drivers/")

    assert response.status_code == 200
    assert response.data["count"] == 2


def test_is_approved_filter(client):
    DriverProfileFactory(is_approved=True)
    DriverProfileFactory(is_approved=False)
    _auth(client, _admin())

    response = client.get("/api/auth/drivers/?is_approved=true")
    assert response.data["count"] == 1

    response = client.get("/api/auth/drivers/?is_approved=false")
    assert response.data["count"] == 1


def test_admin_can_approve_a_driver(client):
    driver = DriverProfileFactory(
        is_approved=False, background_check_status=BackgroundCheckStatus.PENDING
    )
    admin = _admin()
    _auth(client, admin)

    response = client.post(f"/api/auth/drivers/{driver.id}/approve/")

    assert response.status_code == 200, response.data
    driver.refresh_from_db()
    assert driver.is_approved is True
    assert driver.background_check_status == BackgroundCheckStatus.APPROVED
    assert driver.approved_at is not None
    assert driver.approved_by == admin

    from apps.notifications.models import Notification, NotificationCategory

    assert Notification.objects.filter(
        recipient=driver.user, category=NotificationCategory.DRIVER_APPROVED
    ).exists()


def test_admin_can_reject_a_driver(client):
    driver = DriverProfileFactory()
    _auth(client, _admin())

    response = client.post(f"/api/auth/drivers/{driver.id}/reject/", {"reason": "expired license"})

    assert response.status_code == 200, response.data
    driver.refresh_from_db()
    assert driver.is_approved is False
    assert driver.background_check_status == BackgroundCheckStatus.REJECTED
    assert driver.rejection_reason == "expired license"


def test_non_admin_forbidden_from_driver_admin_endpoints(client):
    driver = DriverProfileFactory()
    rider = RiderFactory()
    _auth(client, rider)

    assert client.get("/api/auth/drivers/").status_code == 403
    assert client.post(f"/api/auth/drivers/{driver.id}/approve/").status_code == 403
    assert client.post(f"/api/auth/drivers/{driver.id}/reject/").status_code == 403


@pytest.mark.parametrize(
    "days_until_expiry,expiring_soon,expired",
    [
        (10, True, False),
        (31, False, False),
        (-5, False, True),
    ],
)
def test_license_expiry_flags(client, days_until_expiry, expiring_soon, expired):
    driver = DriverProfileFactory(
        license_expiry_date=timezone.localdate() + timedelta(days=days_until_expiry)
    )
    _auth(client, _admin())

    response = client.get(f"/api/auth/drivers/{driver.id}/")

    assert response.data["license_expiring_soon"] is expiring_soon
    assert response.data["license_expired"] is expired


def test_license_expiry_flags_false_when_no_expiry_date(client):
    driver = DriverProfileFactory(license_expiry_date=None)
    _auth(client, _admin())

    response = client.get(f"/api/auth/drivers/{driver.id}/")

    assert response.data["license_expiring_soon"] is False
    assert response.data["license_expired"] is False
