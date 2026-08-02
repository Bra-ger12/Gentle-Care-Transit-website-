"""Canvas signature capture at drop-off.

The signature is evidence on a Medicaid claim, so what lands on disk has to be
a real PNG and nothing else.
"""

import base64
import io

import pytest
from django.utils import timezone
from PIL import Image

from apps.accounts.tests.factories import DriverProfileFactory
from apps.trips.models import TripStatus
from apps.trips.services.signature import SignatureError, decode_signature
from apps.trips.tests.factories import TripFactory

pytestmark = pytest.mark.django_db


def png_data_url(size=(240, 90)) -> str:
    """What a signature canvas produces via `toDataURL('image/png')`."""
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{encoded}"


def _completion(**overrides):
    payload = {
        "odometer_start": 41000,
        "odometer_end": 41012,
        "completion_attestation": "Tom Nguyen",
    }
    payload.update(overrides)
    return payload


# --- the decoder ---------------------------------------------------------


def test_a_real_png_data_url_decodes():
    file = decode_signature(png_data_url())
    assert file.name.endswith(".png")
    assert file.read().startswith(b"\x89PNG")


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not a data url",
        "data:image/jpeg;base64,/9j/4AAQSkZJRg==",  # wrong declared type
        "data:image/png;base64,!!!!not base64!!!!",
    ],
)
def test_junk_is_refused(value):
    with pytest.raises(SignatureError):
        decode_signature(value)


def test_a_non_png_masquerading_as_one_is_refused():
    """Declared type is not evidence; the magic bytes are."""
    fake = base64.b64encode(b"GIF89a this is not a png").decode()
    with pytest.raises(SignatureError):
        decode_signature(f"data:image/png;base64,{fake}")


def test_an_oversized_signature_is_refused():
    from apps.trips.services import signature as sig

    payload = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * (sig.MAX_SIGNATURE_BYTES + 1))
    with pytest.raises(SignatureError):
        decode_signature(f"data:image/png;base64,{payload.decode()}")


# --- through the API -----------------------------------------------------


def _arrived_trip(driver):
    return TripFactory(
        status=TripStatus.PICKED_UP,
        assigned_driver=driver,
        arrived_at=timezone.now(),
        picked_up_at=timezone.now(),
    )


def test_completing_with_a_signature_stores_the_file(client, _auth):
    driver = DriverProfileFactory()
    trip = _arrived_trip(driver)
    _auth(client, driver.user)

    response = client.post(
        f"/api/trips/{trip.id}/complete/",
        _completion(signature_image=png_data_url()),
        format="json",
    )

    assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert trip.status == TripStatus.COMPLETED
    assert trip.signature_image.name.startswith("trip_signatures/")
    assert trip.signature_image.read().startswith(b"\x89PNG")


def test_completion_still_works_without_a_drawn_signature(client, _auth):
    """A typed attestation alone remains valid -- gloves, cracked screens, cold."""
    driver = DriverProfileFactory()
    trip = _arrived_trip(driver)
    _auth(client, driver.user)

    response = client.post(f"/api/trips/{trip.id}/complete/", _completion(), format="json")

    assert response.status_code == 200, response.data
    trip.refresh_from_db()
    assert trip.completion_attestation == "Tom Nguyen"
    assert not trip.signature_image


def test_a_bad_signature_fails_the_whole_completion(client, _auth):
    driver = DriverProfileFactory()
    trip = _arrived_trip(driver)
    _auth(client, driver.user)

    response = client.post(
        f"/api/trips/{trip.id}/complete/",
        _completion(signature_image="data:image/png;base64,????"),
        format="json",
    )

    assert response.status_code == 400
    assert "signature_image" in response.data
    trip.refresh_from_db()
    assert trip.status == TripStatus.PICKED_UP


def test_an_impossible_odometer_reading_is_rejected(client, _auth):
    driver = DriverProfileFactory()
    trip = _arrived_trip(driver)
    _auth(client, driver.user)

    response = client.post(
        f"/api/trips/{trip.id}/complete/",
        _completion(odometer_start=41000, odometer_end=99000),
        format="json",
    )

    assert response.status_code == 400
    assert "odometer_end" in response.data


def test_the_signature_is_readable_on_the_trip_record(client, _auth):
    driver = DriverProfileFactory()
    trip = _arrived_trip(driver)
    _auth(client, driver.user)
    client.post(
        f"/api/trips/{trip.id}/complete/",
        _completion(signature_image=png_data_url()),
        format="json",
    )

    detail = client.get(f"/api/trips/{trip.id}/")

    assert detail.status_code == 200
    assert detail.data["signature_image"].endswith(".png")
