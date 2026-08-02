import pytest
from django.utils import timezone

from apps.billing.models import InvoiceStatus
from apps.billing.services.pricing import (
    InvoiceError,
    finalize_invoice,
    generate_invoice_for_trip,
    mark_invoice_paid,
    void_invoice,
)
from apps.billing.tests.factories import RateScheduleFactory
from apps.trips.models import TripStatus
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


def _invoice():
    RateScheduleFactory()
    trip = TripFactory(status=TripStatus.COMPLETED, completed_at=timezone.now())
    return generate_invoice_for_trip(trip)


def test_finalize_then_mark_paid():
    invoice = _invoice()

    finalize_invoice(invoice)
    assert invoice.status == InvoiceStatus.FINALIZED
    assert invoice.finalized_at is not None

    mark_invoice_paid(invoice, payment_reference="CHK-123")
    assert invoice.status == InvoiceStatus.PAID
    assert invoice.payment_reference == "CHK-123"


def test_cannot_mark_paid_before_finalized():
    invoice = _invoice()

    with pytest.raises(InvoiceError):
        mark_invoice_paid(invoice)


def test_cannot_finalize_twice():
    invoice = _invoice()
    finalize_invoice(invoice)

    with pytest.raises(InvoiceError):
        finalize_invoice(invoice)


def test_void_from_draft():
    invoice = _invoice()

    void_invoice(invoice, reason="duplicate")

    assert invoice.status == InvoiceStatus.VOID
    assert invoice.void_reason == "duplicate"


def test_void_from_finalized():
    invoice = _invoice()
    finalize_invoice(invoice)

    void_invoice(invoice, reason="rider disputed charge")

    assert invoice.status == InvoiceStatus.VOID


def test_cannot_void_paid_invoice():
    invoice = _invoice()
    finalize_invoice(invoice)
    mark_invoice_paid(invoice)

    with pytest.raises(InvoiceError):
        void_invoice(invoice, reason="too late")


def test_void_then_reissue_creates_a_second_row():
    invoice = _invoice()
    trip = invoice.trip
    void_invoice(invoice, reason="wrong rate applied")

    reissued = generate_invoice_for_trip(trip)

    assert reissued.id != invoice.id
    assert trip.invoices.count() == 2
    assert trip.invoices.exclude(status=InvoiceStatus.VOID).count() == 1
