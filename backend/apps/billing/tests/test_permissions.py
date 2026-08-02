import pytest

from apps.accounts.models import Role
from apps.accounts.tests.factories import DriverFactory, RiderFactory, RiderProfileFactory
from apps.billing.tests.factories import InvoiceFactory
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


def _admin():
    return RiderFactory(role=Role.ADMIN, is_staff=True)


def test_rider_sees_only_own_invoices(client, _auth):
    mine = RiderProfileFactory()
    other = RiderProfileFactory()
    my_invoice = InvoiceFactory(trip=TripFactory(rider=mine))
    InvoiceFactory(trip=TripFactory(rider=other))
    _auth(client, mine.user)

    response = client.get("/api/billing/invoices/")

    assert response.status_code == 200
    ids = {row["id"] for row in response.data["results"]}
    assert ids == {str(my_invoice.id)}


def test_admin_sees_all_invoices(client, _auth):
    InvoiceFactory()
    InvoiceFactory()
    _auth(client, _admin())

    response = client.get("/api/billing/invoices/")

    assert response.status_code == 200
    assert response.data["count"] == 2


def test_driver_sees_no_invoices(client, _auth):
    InvoiceFactory()
    driver = DriverFactory()
    _auth(client, driver)

    response = client.get("/api/billing/invoices/")

    assert response.status_code == 200
    assert response.data["count"] == 0


def test_rider_cannot_retrieve_another_riders_invoice(client, _auth):
    owner = RiderProfileFactory()
    other = RiderProfileFactory()
    invoice = InvoiceFactory(trip=TripFactory(rider=owner))
    _auth(client, other.user)

    response = client.get(f"/api/billing/invoices/{invoice.id}/")

    assert response.status_code == 404


def test_rider_cannot_generate_invoices(client, _auth):
    _auth(client, RiderFactory())

    response = client.post("/api/billing/invoices/generate/", {})

    assert response.status_code == 403


def test_rider_cannot_finalize_own_invoice(client, _auth):
    invoice = InvoiceFactory()
    _auth(client, invoice.rider.user)

    response = client.post(f"/api/billing/invoices/{invoice.id}/finalize/")

    assert response.status_code == 403


def test_non_admin_cannot_create_rate_schedule(client, _auth):
    _auth(client, RiderFactory())

    response = client.post("/api/billing/rate-schedules/", {})

    assert response.status_code == 403


def test_unauthenticated_cannot_list_invoices(client):
    response = client.get("/api/billing/invoices/")

    assert response.status_code == 401
