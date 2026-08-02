import pytest
from rest_framework.test import APIClient

from apps.accounts.models import DriverProfile, RiderProfile, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def test_rider_registration_creates_rider_profile(client):
    response = client.post(
        "/api/auth/register/",
        {
            "email": "rider@example.com",
            "password": "StrongPass123!",
            "first_name": "Rae",
            "last_name": "Rider",
            "role": "RIDER",
        },
        format="json",
    )
    assert response.status_code == 201
    user = User.objects.get(email="rider@example.com")
    assert user.role == "RIDER"
    assert RiderProfile.objects.filter(user=user).exists()
    assert not DriverProfile.objects.filter(user=user).exists()


def test_driver_registration_creates_driver_profile(client):
    response = client.post(
        "/api/auth/register/",
        {
            "email": "driver@example.com",
            "password": "StrongPass123!",
            "first_name": "Dee",
            "last_name": "Driver",
            "role": "DRIVER",
        },
        format="json",
    )
    assert response.status_code == 201
    user = User.objects.get(email="driver@example.com")
    assert user.role == "DRIVER"
    assert DriverProfile.objects.filter(user=user).exists()


def test_duplicate_email_rejected(client):
    payload = {
        "email": "dup@example.com",
        "password": "StrongPass123!",
        "role": "RIDER",
    }
    first = client.post("/api/auth/register/", payload, format="json")
    assert first.status_code == 201

    second = client.post("/api/auth/register/", payload, format="json")
    assert second.status_code == 400
    assert "email" in second.data


def test_duplicate_phone_rejected(client):
    base_payload = {
        "password": "StrongPass123!",
        "role": "RIDER",
        "phone_number": "+17015551234",
    }
    first = client.post(
        "/api/auth/register/", {**base_payload, "email": "a@example.com"}, format="json"
    )
    assert first.status_code == 201

    second = client.post(
        "/api/auth/register/", {**base_payload, "email": "b@example.com"}, format="json"
    )
    assert second.status_code == 400
    assert "phone_number" in second.data


def test_weak_password_rejected(client):
    response = client.post(
        "/api/auth/register/",
        {"email": "weak@example.com", "password": "123", "role": "RIDER"},
        format="json",
    )
    assert response.status_code == 400
    assert "password" in response.data
