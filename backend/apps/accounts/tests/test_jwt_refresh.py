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


def test_login_sets_refresh_and_csrf_cookies(client):
    # FIX #6: the browser needs csrftoken before it can call refresh.
    RiderFactory(email="cookie-rider@example.com", password="CorrectPass123!")

    response = client.post(
        "/api/auth/login/",
        {"identifier": "cookie-rider@example.com", "password": "CorrectPass123!"},
        format="json",
    )

    assert response.status_code == 200
    assert "refresh_token" in response.cookies
    assert "csrftoken" in response.cookies
    assert response.data["csrf"]
    assert response.cookies["csrftoken"].value


def test_csrf_endpoint_issues_token(client):
    # FIX #6: SPA can bootstrap a token before refreshing from an httpOnly cookie.
    response = client.get("/api/auth/csrf/")

    assert response.status_code == 200
    assert response.data["csrf"]
    assert "csrftoken" in response.cookies


def test_refresh_requires_csrf_header_when_csrf_checks_are_enforced():
    # FIX #6: refresh uses an httpOnly cookie, so browser-style CSRF checks matter.
    client = APIClient(enforce_csrf_checks=True)
    RiderFactory(email="csrf-rider@example.com", password="CorrectPass123!")
    login = client.post(
        "/api/auth/login/",
        {"identifier": "csrf-rider@example.com", "password": "CorrectPass123!"},
        format="json",
    )
    refresh_value = login.cookies["refresh_token"].value
    csrf_value = login.cookies["csrftoken"].value
    client.cookies["refresh_token"] = refresh_value

    missing_header = client.post("/api/auth/refresh/", format="json")
    assert missing_header.status_code == 403

    with_header = client.post(
        "/api/auth/refresh/",
        HTTP_X_CSRFTOKEN=csrf_value,
        format="json",
    )
    assert with_header.status_code == 200
    assert "access" in with_header.data
    assert "csrf" in with_header.data


def test_logout_blacklists_refresh_token(logged_in_client):
    client, access, refresh_value = logged_in_client
    client.cookies["refresh_token"] = refresh_value
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    logout_response = client.post("/api/auth/logout/", format="json")
    assert logout_response.status_code == 205

    client.cookies["refresh_token"] = refresh_value
    reuse_attempt = client.post("/api/auth/refresh/", format="json")
    assert reuse_attempt.status_code == 401
