"""Email verification: the link, the gate it opens, and the ways it can fail."""

import re
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.emails import email_verification_token
from apps.accounts.models import Role, User
from apps.accounts.tests.factories import RiderProfileFactory
from apps.operations.models import SystemSetting
from apps.trips.models import Trip

pytestmark = pytest.mark.django_db

REGISTRATION = {
    "email": "newrider@example.com",
    "password": "SturdyPassphrase!2026",
    "first_name": "New",
    "last_name": "Rider",
    "role": Role.RIDER,
}


def link_parts(url):
    match = re.search(r"uid=([^&]+)&token=(\S+)", url)
    return {"uid": match.group(1), "token": match.group(2)}


def sent_link():
    body = mail.outbox[-1].body
    return link_parts(re.search(r"(http\S+)", body).group(1))


# --- sending -------------------------------------------------------------


def test_registering_sends_a_verification_email(client):
    response = client.post("/api/auth/register/", REGISTRATION, format="json")

    assert response.status_code == 201, response.data
    assert len(mail.outbox) == 1
    assert "newrider@example.com" in mail.outbox[0].to
    assert "verify-email.html" in mail.outbox[0].body


def test_a_new_account_starts_unverified(client):
    client.post("/api/auth/register/", REGISTRATION, format="json")
    assert User.objects.get(email=REGISTRATION["email"]).is_verified is False


def test_registration_survives_a_mail_failure(client, monkeypatch):
    """Losing the account because SMTP blipped would be far worse than a missing email."""
    from apps.accounts import emails

    monkeypatch.setattr(
        emails, "send_mail", lambda *a, **k: (_ for _ in ()).throw(OSError("smtp down"))
    )

    response = client.post("/api/auth/register/", REGISTRATION, format="json")

    assert response.status_code == 201
    assert User.objects.filter(email=REGISTRATION["email"]).exists()


# --- confirming ----------------------------------------------------------


def test_the_emailed_link_verifies_the_account(client):
    client.post("/api/auth/register/", REGISTRATION, format="json")

    response = client.post("/api/auth/verify-email/confirm/", sent_link(), format="json")

    assert response.status_code == 200, response.data
    assert response.data["verified"] is True
    assert User.objects.get(email=REGISTRATION["email"]).is_verified is True


def test_confirming_needs_no_login(client):
    """The link is opened from a mail client, often on another device."""
    client.post("/api/auth/register/", REGISTRATION, format="json")
    client.credentials()  # no auth header

    assert (
        client.post("/api/auth/verify-email/confirm/", sent_link(), format="json").status_code
        == 200
    )


def test_clicking_the_same_link_twice_is_not_an_error(client):
    client.post("/api/auth/register/", REGISTRATION, format="json")
    parts = sent_link()

    assert client.post("/api/auth/verify-email/confirm/", parts, format="json").status_code == 200
    second = client.post("/api/auth/verify-email/confirm/", parts, format="json")
    assert second.status_code == 200
    assert "already confirmed" in second.data["detail"]


def test_a_tampered_token_is_refused(client):
    client.post("/api/auth/register/", REGISTRATION, format="json")
    parts = sent_link()
    parts["token"] = parts["token"][:-4] + "aaaa"

    response = client.post("/api/auth/verify-email/confirm/", parts, format="json")
    assert response.status_code == 400
    assert User.objects.get(email=REGISTRATION["email"]).is_verified is False


def test_an_unknown_uid_is_refused(client):
    response = client.post(
        "/api/auth/verify-email/confirm/", {"uid": "bm9wZQ", "token": "x"}, format="json"
    )
    assert response.status_code == 400


def test_a_password_reset_token_cannot_verify_an_email(client):
    """Separate salts: one kind of link must never do the other's job."""
    from django.contrib.auth.tokens import default_token_generator

    from apps.accounts.serializers import make_password_reset_link

    profile = RiderProfileFactory()
    profile.user.is_verified = False
    profile.user.save()
    reset = link_parts(make_password_reset_link(profile.user, "http://x"))

    assert default_token_generator.check_token(profile.user, reset["token"]) is True
    response = client.post("/api/auth/verify-email/confirm/", reset, format="json")
    assert response.status_code == 400


def test_verifying_invalidates_outstanding_links(client):
    profile = RiderProfileFactory()
    profile.user.is_verified = False
    profile.user.save()
    token = email_verification_token.make_token(profile.user)

    profile.user.is_verified = True
    profile.user.save()

    assert email_verification_token.check_token(profile.user, token) is False


# --- resending -----------------------------------------------------------


def test_a_signed_in_user_can_request_a_new_link(client, _auth):
    profile = RiderProfileFactory()
    profile.user.is_verified = False
    profile.user.save()
    _auth(client, profile.user)

    response = client.post("/api/auth/verify-email/resend/", {}, format="json")

    assert response.status_code == 200
    assert len(mail.outbox) == 1
    assert profile.user.email in mail.outbox[0].to


def test_resending_when_already_verified_says_so(client, _auth):
    profile = RiderProfileFactory()
    profile.user.is_verified = True
    profile.user.save()
    _auth(client, profile.user)

    response = client.post("/api/auth/verify-email/resend/", {}, format="json")
    assert response.status_code == 200
    assert response.data["verified"] is True
    assert len(mail.outbox) == 0


def test_resending_requires_a_login(client):
    assert client.post("/api/auth/verify-email/resend/", {}).status_code == 401


def test_the_new_link_works(client, _auth):
    profile = RiderProfileFactory()
    profile.user.is_verified = False
    profile.user.save()
    _auth(client, profile.user)
    client.post("/api/auth/verify-email/resend/", {}, format="json")

    response = client.post("/api/auth/verify-email/confirm/", sent_link(), format="json")

    assert response.status_code == 200
    profile.user.refresh_from_db()
    assert profile.user.is_verified is True


# --- the gate ------------------------------------------------------------


def _booking():
    return {
        "scheduled_pickup_time": (timezone.now() + timedelta(days=2)).isoformat(),
        "pickup_address": "1420 Boulevard Ave, Bismarck, ND",
        "dropoff_address": "Sanford Health, 300 N 7th St, Bismarck, ND",
    }


def test_an_unverified_rider_cannot_book(client, _auth):
    profile = RiderProfileFactory()
    profile.user.is_verified = False
    profile.user.save()
    _auth(client, profile.user)

    response = client.post("/api/trips/", _booking(), format="json")

    assert response.status_code == 400
    assert "email" in response.data
    assert Trip.objects.count() == 0


def test_a_verified_rider_can_book(client, _auth):
    profile = RiderProfileFactory()
    profile.user.is_verified = True
    profile.user.save()
    _auth(client, profile.user)

    assert client.post("/api/trips/", _booking(), format="json").status_code == 201


def test_verifying_unblocks_booking(client, _auth):
    profile = RiderProfileFactory()
    profile.user.is_verified = False
    profile.user.save()
    _auth(client, profile.user)
    assert client.post("/api/trips/", _booking(), format="json").status_code == 400

    client.post("/api/auth/verify-email/resend/", {}, format="json")
    client.post("/api/auth/verify-email/confirm/", sent_link(), format="json")

    assert client.post("/api/trips/", _booking(), format="json").status_code == 201


def test_an_operator_can_turn_the_requirement_off(client, _auth):
    setting = SystemSetting.load()
    setting.require_verified_email_to_book = False
    setting.save()

    profile = RiderProfileFactory()
    profile.user.is_verified = False
    profile.user.save()
    _auth(client, profile.user)

    assert client.post("/api/trips/", _booking(), format="json").status_code == 201
