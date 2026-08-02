"""DVIR: the driver's daily vehicle check, and the admin sign-off that clears
whatever it flagged."""

import pytest
from django.utils import timezone

from apps.accounts.models import Role, VehicleType
from apps.accounts.tests.factories import DriverProfileFactory, RiderFactory
from apps.fleet.models import VehicleInspection

pytestmark = pytest.mark.django_db

CLEAN = {
    "inspection_type": "PRE_TRIP",
    "odometer": 41200,
    "defects": [],
    "defect_notes": "",
    "safe_to_operate": True,
    "signature": "Dana Whitfield",
}

WITH_DEFECT = {
    **CLEAN,
    "defects": ["WHEELCHAIR_LIFT", "TIRES"],
    "defect_notes": "Lift stalls halfway; front left tire down to the wear bar.",
    "safe_to_operate": False,
}


@pytest.fixture
def admin_user():
    return RiderFactory(role=Role.ADMIN, is_staff=True)


@pytest.fixture
def driver():
    return DriverProfileFactory(vehicle_plate="ND-7788", vehicle_type=VehicleType.WHEELCHAIR_VAN)


def test_driver_files_a_clean_report(client, _auth, driver):
    _auth(client, driver.user)

    response = client.post("/api/fleet/inspections/", CLEAN, format="json")

    assert response.status_code == 201, response.data
    assert response.data["has_defects"] is False
    assert response.data["needs_attention"] is False
    # The plate is snapshotted, not looked up later.
    assert response.data["vehicle_plate_snapshot"] == "ND-7788"
    assert response.data["inspected_on"] == timezone.localdate().isoformat()


def test_defects_flag_the_report_for_an_admin(client, _auth, driver):
    _auth(client, driver.user)

    response = client.post("/api/fleet/inspections/", WITH_DEFECT, format="json")

    assert response.status_code == 201, response.data
    assert response.data["has_defects"] is True
    assert response.data["needs_attention"] is True
    assert response.data["safe_to_operate"] is False


def test_a_defect_needs_a_description(client, _auth, driver):
    _auth(client, driver.user)

    response = client.post(
        "/api/fleet/inspections/", {**WITH_DEFECT, "defect_notes": "  "}, format="json"
    )

    assert response.status_code == 400
    assert "defect_notes" in response.data


def test_report_must_be_signed(client, _auth, driver):
    _auth(client, driver.user)

    response = client.post("/api/fleet/inspections/", {**CLEAN, "signature": ""}, format="json")

    assert response.status_code == 400
    assert "signature" in response.data


def test_unknown_checklist_items_are_rejected(client, _auth, driver):
    _auth(client, driver.user)

    response = client.post(
        "/api/fleet/inspections/",
        {**CLEAN, "defects": ["FLUX_CAPACITOR"], "defect_notes": "n/a"},
        format="json",
    )

    assert response.status_code == 400
    assert "defects" in response.data


def test_resubmitting_corrects_the_days_report(client, _auth, driver):
    """One pre-trip report per driver per day -- a second submission replaces it."""
    _auth(client, driver.user)

    client.post("/api/fleet/inspections/", CLEAN, format="json")
    second = client.post("/api/fleet/inspections/", WITH_DEFECT, format="json")

    assert second.status_code == 201, second.data
    assert VehicleInspection.objects.filter(driver=driver, inspection_type="PRE_TRIP").count() == 1
    assert VehicleInspection.objects.get(driver=driver).has_defects is True


def test_pre_and_post_trip_coexist(client, _auth, driver):
    _auth(client, driver.user)

    client.post("/api/fleet/inspections/", CLEAN, format="json")
    client.post("/api/fleet/inspections/", {**CLEAN, "inspection_type": "POST_TRIP"}, format="json")

    assert VehicleInspection.objects.filter(driver=driver).count() == 2


def test_today_endpoint_backs_the_boards_dvir_status(client, _auth, driver):
    _auth(client, driver.user)
    client.post("/api/fleet/inspections/", CLEAN, format="json")

    response = client.get("/api/fleet/inspections/today/")

    assert response.status_code == 200, response.data
    assert len(response.data) == 1
    assert response.data[0]["inspection_type"] == "PRE_TRIP"


def test_driver_sees_only_their_own_reports(client, _auth, driver):
    other = DriverProfileFactory()
    _auth(client, other.user)
    client.post("/api/fleet/inspections/", CLEAN, format="json")

    _auth(client, driver.user)
    response = client.get("/api/fleet/inspections/")

    assert response.status_code == 200, response.data
    assert response.data["count"] == 0


def test_admin_reviews_a_flagged_report(client, _auth, driver, admin_user):
    _auth(client, driver.user)
    created = client.post("/api/fleet/inspections/", WITH_DEFECT, format="json")
    inspection_id = created.data["id"]

    _auth(client, admin_user)
    outstanding = client.get("/api/fleet/inspections/?needs_attention=true")
    assert outstanding.data["count"] == 1

    reviewed = client.post(
        f"/api/fleet/inspections/{inspection_id}/review/",
        {"resolution_notes": "Lift serviced, tire replaced. Van back in service."},
        format="json",
    )

    assert reviewed.status_code == 200, reviewed.data
    assert reviewed.data["needs_attention"] is False
    assert reviewed.data["reviewed_at"] is not None

    assert client.get("/api/fleet/inspections/?needs_attention=true").data["count"] == 0


def test_driver_cannot_review(client, _auth, driver):
    _auth(client, driver.user)
    created = client.post("/api/fleet/inspections/", WITH_DEFECT, format="json")

    response = client.post(f"/api/fleet/inspections/{created.data['id']}/review/")

    assert response.status_code == 403


def test_checklist_is_served_from_the_model(client, _auth, driver):
    _auth(client, driver.user)

    response = client.get("/api/fleet/inspection-checklist/")

    assert response.status_code == 200, response.data
    values = [item["value"] for item in response.data["items"]]
    assert "WHEELCHAIR_LIFT" in values
    assert "SECUREMENTS" in values
    assert len(response.data["inspection_types"]) == 2
