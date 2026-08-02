import pytest
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from apps.accounts.tests.factories import RiderFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def test_request_reset_for_existing_email_sends_mail(client):
    rider = RiderFactory(email="rider@example.com")
    response = client.post(
        "/api/auth/password-reset/request/",
        {"email": "rider@example.com"},
        format="json",
    )
    assert response.status_code == 200
    assert len(mail.outbox) == 1
    assert rider.email in mail.outbox[0].to


def test_request_reset_for_unknown_email_does_not_leak(client):
    response = client.post(
        "/api/auth/password-reset/request/",
        {"email": "nobody@example.com"},
        format="json",
    )
    assert response.status_code == 200
    assert len(mail.outbox) == 0


def test_confirm_reset_with_valid_token(client):
    rider = RiderFactory(email="rider@example.com", password="OldPass123!")
    uid = urlsafe_base64_encode(force_bytes(rider.pk))
    token = default_token_generator.make_token(rider)

    response = client.post(
        "/api/auth/password-reset/confirm/",
        {"uid": uid, "token": token, "new_password": "BrandNewPass123!"},
        format="json",
    )
    assert response.status_code == 200

    rider.refresh_from_db()
    assert rider.check_password("BrandNewPass123!")


def test_confirm_reset_with_invalid_token_rejected(client):
    rider = RiderFactory(email="rider@example.com", password="OldPass123!")
    uid = urlsafe_base64_encode(force_bytes(rider.pk))

    response = client.post(
        "/api/auth/password-reset/confirm/",
        {"uid": uid, "token": "not-a-real-token", "new_password": "BrandNewPass123!"},
        format="json",
    )
    assert response.status_code == 400

    rider.refresh_from_db()
    assert rider.check_password("OldPass123!")
