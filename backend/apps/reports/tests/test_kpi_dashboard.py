from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import RiderFactory
from apps.billing.services.pricing import finalize_invoice, generate_invoice_for_trip
from apps.billing.tests.factories import RateScheduleFactory
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


def _admin():
    return RiderFactory(role=Role.ADMIN, is_staff=True)


def test_kpi_summary_reports_trip_volume_and_revenue(client, _auth):
    now = timezone.now()
    RateScheduleFactory(base_fare="5.00", per_mile_rate="1.00")
    completed = TripFactory(
        status=TripStatus.COMPLETED, scheduled_pickup_time=now, completed_at=now, mileage="2.00"
    )
    TripFactory(status=TripStatus.CANCELLED, scheduled_pickup_time=now)
    invoice = generate_invoice_for_trip(completed)
    finalize_invoice(invoice)
    _auth(client, _admin())

    today = timezone.localdate().isoformat()
    response = client.get(f"/api/reports/kpis/summary/?date_from={today}&date_to={today}")

    assert response.status_code == 200
    data = response.data
    assert data["trip_volume"]["total"] >= 1
    assert data["cancellation_no_show"]["total"] >= 1
    assert data["revenue"]["outstanding_total"] == Decimal("7.00")


def test_kpi_summary_defaults_to_trailing_30_days(client, _auth):
    _auth(client, _admin())

    response = client.get("/api/reports/kpis/summary/")

    assert response.status_code == 200
    assert "date_from" in response.data
    assert "date_to" in response.data


def test_kpi_summary_rejects_inverted_date_range(client, _auth):
    _auth(client, _admin())

    response = client.get("/api/reports/kpis/summary/?date_from=2026-02-01&date_to=2026-01-01")

    assert response.status_code == 400


def test_revenue_by_month_returns_list(client, _auth):
    now = timezone.now()
    RateScheduleFactory()
    trip = TripFactory(status=TripStatus.COMPLETED, completed_at=now)
    invoice = generate_invoice_for_trip(trip)
    finalize_invoice(invoice)
    _auth(client, _admin())

    today = timezone.localdate()
    date_from = (today - timedelta(days=60)).isoformat()
    response = client.get(
        f"/api/reports/kpis/revenue-by-month/?date_from={date_from}&date_to={today.isoformat()}"
    )

    assert response.status_code == 200
    assert isinstance(response.data, list)
    assert len(response.data) >= 1
