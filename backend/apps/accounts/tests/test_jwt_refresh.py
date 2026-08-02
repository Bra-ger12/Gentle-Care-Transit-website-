import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from apps.accounts.tests.factories import RiderFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def logged_in_client(client):
    RiderFactory(email="rider@example.com", password="CorrectPass123!")
    login = client.post(
        "/api/auth/login/",
        {"identifier": "rider@example.com", "password": "CorrectPass123!"},
        format="json",
    )
    return client, login.data["access"], login.cookies["refresh_token"].value


def test_refresh_rotates_and_returns_new_access(logged_in_client):
    client, access, refresh_value = logged_in_client
    client.cookies["refresh_token"] = refresh_value

    response = client.post("/api/auth/refresh/", format="json")
    assert response.status_code == 200
    assert "access" in response.data
    assert response.data["access"] != access
    assert response.cookies["refresh_token"].value != refresh_value


def test_old_refresh_token_blacklisted_after_rotation(logged_in_client):
    client, _access, refresh_value = logged_in_client
    client.cookies["refresh_token"] = refresh_value
    client.post("/api/auth/refresh/", format="json")

    assert (
        BlacklistedToken.objects.filter(token__token__endswith=refresh_value[-20:]).exists()
        or BlacklistedToken.objects.exists()
    )

    # Reusing the old (now-blacklisted) refresh token cookie must fail.
    client.cookies["refresh_token"] = refresh_value
    second_attempt = client.post("/api/auth/refresh/", format="json")
    assert second_attempt.status_code == 401


def test_refresh_without_cookie_rejected(client):
    response = client.post("/api/auth/refresh/", format="json")
    assert response.status_code == 401


def test_logout_blacklists_refresh_token(logged_in_client):
    client, access, refresh_value = logged_in_client
    client.cookies["refresh_token"] = refresh_value
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    logout_response = client.post("/api/auth/logout/", format="json")
    assert logout_response.status_code == 205

    client.cookies["refresh_token"] = refresh_value
    reuse_attempt = client.post("/api/auth/refresh/", format="json")
    assert reuse_attempt.status_code == 401
