import pytest

from apps.accounts.tests.factories import DriverFactory, RiderFactory

pytestmark = pytest.mark.django_db


def test_rider_cannot_view_kpi_summary(client, _auth):
    _auth(client, RiderFactory())

    response = client.get("/api/reports/kpis/summary/")

    assert response.status_code == 403


def test_driver_cannot_view_revenue_by_month(client, _auth):
    _auth(client, DriverFactory())

    response = client.get("/api/reports/kpis/revenue-by-month/")

    assert response.status_code == 403


def test_unauthenticated_cannot_view_kpi_summary(client):
    response = client.get("/api/reports/kpis/summary/")

    assert response.status_code == 401
