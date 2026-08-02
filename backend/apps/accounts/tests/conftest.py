import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


@pytest.fixture
def client():
    """APIClient rather than pytest-django's plain test client, so these tests
    can set credentials and post JSON the same way the rest of the suite does."""
    return APIClient()


@pytest.fixture
def _auth():
    def _apply(client, user):
        access = str(RefreshToken.for_user(user).access_token)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        return client

    return _apply
