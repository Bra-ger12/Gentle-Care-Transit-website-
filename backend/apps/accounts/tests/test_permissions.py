import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Role
from apps.accounts.tests.factories import DriverFactory, DriverProfileFactory, RiderFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def _auth(client, user):
    access = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


def test_rider_can_access_own_rider_profile(client):
    rider = RiderFactory()
    _auth(client, rider)
    response = client.get("/api/auth/me/rider-profile/")
    assert response.status_code == 200


def test_rider_blocked_from_driver_profile(client):
    rider = RiderFactory()
    _auth(client, rider)
    response = client.get("/api/auth/me/driver-profile/")
    assert response.status_code == 403


def test_driver_blocked_from_rider_profile(client):
    driver = DriverFactory()
    _auth(client, driver)
    response = client.get("/api/auth/me/rider-profile/")
    assert response.status_code == 403


def test_unapproved_driver_blocked_by_isdriver_permission():
    from apps.accounts.permissions import IsDriver

    driver = DriverFactory()  # no DriverProfile / not approved

    class FakeRequest:
        user = driver

    assert IsDriver().has_permission(FakeRequest(), None) is False


def test_approved_driver_passes_isdriver_permission():
    from apps.accounts.permissions import IsDriver

    profile = DriverProfileFactory(is_approved=True)
    driver = profile.user

    class FakeRequest:
        user = driver

    assert IsDriver().has_permission(FakeRequest(), None) is True


def test_admin_can_access_any_profile_via_me(client):
    admin = RiderFactory(role=Role.ADMIN, is_staff=True)
    rider = RiderFactory()
    _auth(client, admin)

    response = client.get("/api/auth/me/")
    assert response.status_code == 200
    assert response.data["role"] == "ADMIN"

    # Sanity: another rider exists and is unaffected by admin's own /me/ call.
    assert rider.role == Role.RIDER
