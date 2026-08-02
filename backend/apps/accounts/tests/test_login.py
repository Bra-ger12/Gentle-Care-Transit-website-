import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import RiderFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def rider():
    return RiderFactory(
        email="rider@example.com",
        phone_number="+17015551234",
        password="CorrectPass123!",
    )


def test_login_with_email(client, rider):
    response = client.post(
        "/api/auth/login/",
        {"identifier": "rider@example.com", "password": "CorrectPass123!"},
        format="json",
    )
    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh_token" in response.cookies
    assert response.cookies["refresh_token"]["httponly"]


def test_login_with_phone(client, rider):
    response = client.post(
        "/api/auth/login/",
        {"identifier": "+17015551234", "password": "CorrectPass123!"},
        format="json",
    )
    assert response.status_code == 200
    assert "access" in response.data


def test_login_wrong_password(client, rider):
    response = client.post(
        "/api/auth/login/",
        {"identifier": "rider@example.com", "password": "WrongPassword!"},
        format="json",
    )
    assert response.status_code == 401


def test_login_inactive_user_rejected(client, rider):
    rider.is_active = False
    rider.save(update_fields=["is_active"])

    response = client.post(
        "/api/auth/login/",
        {"identifier": "rider@example.com", "password": "CorrectPass123!"},
        format="json",
    )
    assert response.status_code == 401
