"""Insurance document upload.

This file arrives from an unapproved account -- someone who registered minutes
ago and whom nobody has vetted. It is the least trusted input in the system, so
it is checked on its actual bytes rather than on what the browser claims.
"""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.accounts.tests.factories import DriverProfileFactory
from apps.accounts.validators import MAX_DOCUMENT_BYTES

pytestmark = pytest.mark.django_db

PDF_BYTES = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>"


def png_bytes(size=(40, 40)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 200, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


def upload(client, file):
    return client.patch(
        "/api/auth/me/driver-profile/",
        {"insurance_document": file},
        format="multipart",
    )


@pytest.fixture
def driver(client, _auth):
    profile = DriverProfileFactory(is_approved=False)
    _auth(client, profile.user)
    return profile


def test_a_pdf_is_accepted(client, driver):
    response = upload(
        client, SimpleUploadedFile("policy.pdf", PDF_BYTES, content_type="application/pdf")
    )

    assert response.status_code == 200, response.data
    driver.refresh_from_db()
    assert driver.insurance_document.name.endswith(".pdf")


def test_a_photo_is_accepted(client, driver):
    response = upload(
        client, SimpleUploadedFile("policy.png", png_bytes(), content_type="image/png")
    )
    assert response.status_code == 200, response.data


def test_an_executable_is_refused(client, driver):
    response = upload(
        client,
        SimpleUploadedFile("payload.exe", b"MZ\x90\x00", content_type="application/octet-stream"),
    )
    assert response.status_code == 400
    assert "insurance_document" in response.data


def test_a_script_renamed_to_pdf_is_refused(client, driver):
    """The extension and the declared type are both attacker-controlled."""
    response = upload(
        client,
        SimpleUploadedFile(
            "invoice.pdf", b"<?php system($_GET['c']); ?>", content_type="application/pdf"
        ),
    )

    assert response.status_code == 400
    assert "readable PDF or image" in str(response.data["insurance_document"])
    driver.refresh_from_db()
    assert not driver.insurance_document


def test_an_html_file_claiming_to_be_a_png_is_refused(client, driver):
    response = upload(
        client,
        SimpleUploadedFile(
            "x.png", b"<html><script>alert(1)</script></html>", content_type="image/png"
        ),
    )
    assert response.status_code == 400


def test_an_empty_file_is_refused(client, driver):
    response = upload(client, SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf"))
    assert response.status_code == 400


def test_an_oversized_file_is_refused(client, driver):
    oversized = b"%PDF-1.4" + b"0" * (MAX_DOCUMENT_BYTES + 1)
    response = upload(
        client, SimpleUploadedFile("huge.pdf", oversized, content_type="application/pdf")
    )

    assert response.status_code == 400
    assert "limit is" in str(response.data["insurance_document"])


def test_a_disallowed_extension_is_refused(client, driver):
    response = upload(
        client, SimpleUploadedFile("policy.svg", PDF_BYTES, content_type="image/svg+xml")
    )
    assert response.status_code == 400


def test_an_expired_licence_date_is_refused(client, driver):
    from datetime import timedelta

    from django.utils import timezone

    response = client.patch(
        "/api/auth/me/driver-profile/",
        {"license_expiry_date": (timezone.localdate() - timedelta(days=1)).isoformat()},
        format="json",
    )

    assert response.status_code == 400
    assert "license_expiry_date" in response.data


def test_a_valid_licence_date_is_accepted(client, driver):
    from datetime import timedelta

    from django.utils import timezone

    response = client.patch(
        "/api/auth/me/driver-profile/",
        {"license_expiry_date": (timezone.localdate() + timedelta(days=200)).isoformat()},
        format="json",
    )
    assert response.status_code == 200, response.data
