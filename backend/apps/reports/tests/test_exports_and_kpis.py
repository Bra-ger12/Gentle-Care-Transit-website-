"""Report CSV downloads, and the KPI figures the dashboard reads."""

import csv
import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import AdminFactory, DriverProfileFactory, RiderProfileFactory
from apps.audit.models import AuditAction, AuditLog
from apps.reports.services import kpis
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


def rows_of(response):
    return list(csv.reader(io.StringIO(response.content.decode())))


def completed(minutes_late=0, **overrides):
    scheduled = timezone.now() - timedelta(days=1)
    fields = {
        "status": TripStatus.COMPLETED,
        "scheduled_pickup_time": scheduled,
        "arrived_at": scheduled - timedelta(minutes=3),
        "picked_up_at": scheduled + timedelta(minutes=minutes_late),
        "completed_at": scheduled + timedelta(minutes=minutes_late + 25),
        "mileage": Decimal("12.00"),
    }
    fields.update(overrides)
    return TripFactory(**fields)


def window():
    today = timezone.localdate()
    return f"date_from={today - timedelta(days=7)}&date_to={today + timedelta(days=1)}"


# --- on-time performance -------------------------------------------------


def test_a_prompt_pickup_counts_as_on_time():
    completed(minutes_late=2)
    result = kpis.on_time_performance(
        timezone.localdate() - timedelta(days=7), timezone.localdate() + timedelta(days=1)
    )
    assert result["on_time"] == 1
    assert result["on_time_rate"] == 1.0


def test_a_pickup_past_the_grace_window_counts_as_late():
    completed(minutes_late=45)
    result = kpis.on_time_performance(
        timezone.localdate() - timedelta(days=7), timezone.localdate() + timedelta(days=1)
    )
    assert result["late"] == 1
    assert result["on_time_rate"] == 0.0


def test_cancelled_trips_do_not_count_against_punctuality():
    """A trip that never happened has no pickup to be late for."""
    TripFactory(
        status=TripStatus.CANCELLED, scheduled_pickup_time=timezone.now() - timedelta(days=1)
    )
    result = kpis.on_time_performance(
        timezone.localdate() - timedelta(days=7), timezone.localdate() + timedelta(days=1)
    )
    assert result["total"] == 0
    assert result["on_time_rate"] is None


# --- driver activity and today's tiles -----------------------------------


def test_driver_activity_counts_the_fleet():
    DriverProfileFactory(is_approved=True, is_available=True)
    DriverProfileFactory(is_approved=True, is_available=False)
    DriverProfileFactory(is_approved=False)

    result = kpis.driver_activity(
        timezone.localdate() - timedelta(days=7), timezone.localdate()
    )

    assert result["approved_drivers"] == 2
    assert result["on_duty_now"] == 1
    assert result["awaiting_approval"] == 1


def test_today_snapshot_separates_pending_from_active():
    TripFactory(
        status=TripStatus.REQUESTED,
        scheduled_pickup_time=timezone.now() + timedelta(days=1),
    )
    TripFactory(status=TripStatus.EN_ROUTE, scheduled_pickup_time=timezone.now())
    TripFactory(status=TripStatus.ASSIGNED, scheduled_pickup_time=timezone.now(), accepted_at=None)

    snapshot = kpis.today_snapshot()

    assert snapshot["pending"] == 1
    assert snapshot["active"] == 2
    assert snapshot["awaiting_acceptance"] == 1


def test_kpi_summary_carries_the_new_sections(client, _auth):
    completed()
    _auth(client, AdminFactory())

    response = client.get(f"/api/reports/kpis/summary/?{window()}")

    assert response.status_code == 200, response.data
    assert {"on_time", "drivers", "today"} <= set(response.data)


# --- driver performance --------------------------------------------------


def test_driver_performance_ranks_by_completed_trips(client, _auth):
    busy = DriverProfileFactory()
    quiet = DriverProfileFactory()
    completed(assigned_driver=busy)
    completed(assigned_driver=busy)
    completed(assigned_driver=quiet)
    _auth(client, AdminFactory())

    response = client.get(f"/api/reports/driver-performance/?{window()}")

    assert response.status_code == 200, response.data
    assert response.data[0]["driver_id"] == busy.id
    assert response.data[0]["completed"] == 2
    assert response.data[0]["miles"] == 24.0


def test_driver_performance_is_admin_only(client, _auth):
    _auth(client, RiderProfileFactory().user)
    assert client.get("/api/reports/driver-performance/").status_code == 403


# --- CSV exports ---------------------------------------------------------


@pytest.mark.parametrize("report", ["trips", "revenue", "drivers", "mileage"])
def test_every_report_downloads_as_csv(client, _auth, report):
    completed(assigned_driver=DriverProfileFactory())
    _auth(client, AdminFactory())

    response = client.get(f"/api/reports/export/?report={report}&{window()}")

    assert response.status_code == 200, response.content[:200]
    assert response["Content-Type"] == "text/csv"
    assert "attachment;" in response["Content-Disposition"]
    assert len(rows_of(response)[0]) > 1  # a real header row


def test_the_trips_export_contains_the_trip(client, _auth):
    driver = DriverProfileFactory()
    trip = completed(assigned_driver=driver)
    _auth(client, AdminFactory())

    rows = rows_of(client.get(f"/api/reports/export/?report=trips&{window()}"))

    body = [row for row in rows[1:] if row[0] == str(trip.id)]
    assert len(body) == 1
    assert body[0][3] == TripStatus.COMPLETED


def test_the_trips_export_flags_estimated_mileage(client, _auth):
    """A computed distance must not read like a measured one on a claim."""
    completed(distance_estimated=True, assigned_driver=DriverProfileFactory())
    _auth(client, AdminFactory())

    rows = rows_of(client.get(f"/api/reports/export/?report=trips&{window()}"))
    header, body = rows[0], rows[1]

    assert body[header.index("mileage_estimated")] == "yes"


def test_the_mileage_export_totals_per_driver_per_day(client, _auth):
    driver = DriverProfileFactory()
    completed(assigned_driver=driver)
    completed(assigned_driver=driver)
    _auth(client, AdminFactory())

    rows = rows_of(client.get(f"/api/reports/export/?report=mileage&{window()}"))

    assert len(rows) == 2  # header plus one aggregated row
    assert rows[1][2] == "2"
    assert rows[1][3] == "24.0"


def test_an_unknown_report_is_rejected(client, _auth):
    _auth(client, AdminFactory())
    response = client.get(f"/api/reports/export/?report=nonsense&{window()}")
    assert response.status_code == 400
    assert "report" in response.data


def test_exports_are_admin_only(client, _auth):
    _auth(client, RiderProfileFactory().user)
    assert client.get("/api/reports/export/?report=trips").status_code == 403


def test_pulling_an_export_is_audited(client, _auth):
    """These files carry rider names and Medicaid IDs."""
    admin = AdminFactory()
    _auth(client, admin)

    client.get(f"/api/reports/export/?report=trips&{window()}")

    entry = AuditLog.objects.filter(action=AuditAction.EXPORT, model_name="Report").first()
    assert entry is not None
    assert entry.actor == admin
    assert entry.object_id == "trips"
