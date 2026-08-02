import pytest

from apps.accounts.tests.factories import DriverFactory, RiderFactory
from apps.audit.tests.factories import AuditLogFactory

pytestmark = pytest.mark.django_db


def test_rider_cannot_list_audit_logs(client, _auth):
    AuditLogFactory()
    _auth(client, RiderFactory())

    response = client.get("/api/audit/logs/")

    assert response.status_code == 403


def test_driver_cannot_list_audit_logs(client, _auth):
    AuditLogFactory()
    _auth(client, DriverFactory())

    response = client.get("/api/audit/logs/")

    assert response.status_code == 403


def test_unauthenticated_cannot_list_audit_logs(client):
    response = client.get("/api/audit/logs/")

    assert response.status_code == 401
