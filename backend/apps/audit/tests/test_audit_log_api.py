import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import RiderFactory
from apps.audit.models import AuditAction
from apps.audit.tests.factories import AuditLogFactory

pytestmark = pytest.mark.django_db


def _admin():
    return RiderFactory(role=Role.ADMIN, is_staff=True)


def test_admin_can_list_audit_logs(client, _auth):
    AuditLogFactory()
    AuditLogFactory()
    _auth(client, _admin())

    response = client.get("/api/audit/logs/")

    assert response.status_code == 200
    assert response.data["count"] == 2


def test_filter_by_action(client, _auth):
    AuditLogFactory(action=AuditAction.VIEW)
    AuditLogFactory(action=AuditAction.EXPORT)
    _auth(client, _admin())

    response = client.get("/api/audit/logs/?action=EXPORT")

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["action"] == AuditAction.EXPORT


def test_filter_by_model_name(client, _auth):
    AuditLogFactory(model_name="Trip")
    AuditLogFactory(model_name="Invoice")
    _auth(client, _admin())

    response = client.get("/api/audit/logs/?model_name=Invoice")

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["model_name"] == "Invoice"


def test_filter_by_actor(client, _auth):
    admin = _admin()
    mine = AuditLogFactory(actor=admin)
    AuditLogFactory()
    _auth(client, admin)

    response = client.get(f"/api/audit/logs/?actor={admin.id}")

    assert response.status_code == 200
    ids = {row["id"] for row in response.data["results"]}
    assert ids == {mine.id}
