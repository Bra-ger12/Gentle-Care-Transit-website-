import pytest
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.tests.factories import RiderFactory, RiderProfileFactory
from apps.billing.services.pricing import finalize_invoice, generate_invoice_for_trip
from apps.billing.tests.factories import RateScheduleFactory
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


def _admin():
    return RiderFactory(role=Role.ADMIN, is_staff=True)


def _finalized_invoice(medicaid_id=None, completed_at=None):
    RateScheduleFactory()
    rider = RiderProfileFactory(medicaid_id=medicaid_id)
    trip = TripFactory(
        rider=rider, status=TripStatus.COMPLETED, completed_at=completed_at or timezone.now()
    )
    invoice = generate_invoice_for_trip(trip)
    finalize_invoice(invoice)
    return invoice


def test_csv_export_includes_medicaid_invoices_in_range(client, _auth):
    invoice = _finalized_invoice(medicaid_id="MC-12345")
    _auth(client, _admin())
    today = timezone.localdate().isoformat()

    response = client.get(
        f"/api/billing/medicaid-export/?date_from={today}&date_to={today}&export_format=csv"
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    body = response.content.decode()
    assert invoice.invoice_number in body
    assert "MC-12345" in body


def test_csv_export_excludes_riders_without_medicaid_id(client, _auth):
    _finalized_invoice(medicaid_id=None)
    _auth(client, _admin())
    today = timezone.localdate().isoformat()

    response = client.get(
        f"/api/billing/medicaid-export/?date_from={today}&date_to={today}&export_format=csv"
    )

    assert response.status_code == 200
    lines = response.content.decode().strip().splitlines()
    assert len(lines) == 1  # header row only


def test_export_requires_date_range(client, _auth):
    _auth(client, _admin())

    response = client.get("/api/billing/medicaid-export/?export_format=csv")

    assert response.status_code == 400


def test_non_admin_cannot_export(client, _auth):
    _finalized_invoice(medicaid_id="MC-1")
    _auth(client, RiderFactory())
    today = timezone.localdate().isoformat()

    response = client.get(
        f"/api/billing/medicaid-export/?date_from={today}&date_to={today}&export_format=csv"
    )

    assert response.status_code == 403


def test_pdf_export_returns_pdf_content_type(client, _auth):
    """No skip guard: ReportLab is pure Python, so this runs everywhere."""
    _finalized_invoice(medicaid_id="MC-999")
    _auth(client, _admin())
    today = timezone.localdate().isoformat()

    response = client.get(
        f"/api/billing/medicaid-export/?date_from={today}&date_to={today}&export_format=pdf"
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")


def test_pdf_export_is_produced_even_with_no_claims(client, _auth):
    """An empty period is a valid answer, not an error."""
    _auth(client, _admin())
    today = timezone.localdate().isoformat()

    response = client.get(
        f"/api/billing/medicaid-export/?date_from={today}&date_to={today}&export_format=pdf"
    )

    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-")
