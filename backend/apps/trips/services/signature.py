"""Turning a canvas signature into a stored PNG.

The driver's screen produces a data URL (`data:image/png;base64,...`). This
module is the only place that is trusted to become a file on disk, so it does
the checking: declared type, real decoded bytes, a genuine PNG header, and a
size ceiling. A trip record is evidence on a Medicaid claim; a corrupt or
oversized blob in that field is worse than no signature at all.
"""

import base64
import re
import uuid

from django.core.files.base import ContentFile

# A signature drawn on a phone-sized canvas is a few tens of KB. A megabyte is
# far past anything legitimate and well inside what a request can carry.
MAX_SIGNATURE_BYTES = 1_000_000

_DATA_URL = re.compile(r"^data:image/png;base64,(?P<payload>[A-Za-z0-9+/=\s]+)$")
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class SignatureError(ValueError):
    """The submitted signature isn't a usable PNG."""


def decode_signature(data_url: str, filename: str | None = None) -> ContentFile:
    """Validate a canvas data URL and return it as a saveable file."""
    match = _DATA_URL.match((data_url or "").strip())
    if match is None:
        raise SignatureError("Signature must be a base64 PNG data URL.")

    try:
        raw = base64.b64decode(match.group("payload"), validate=True)
    except (base64.binascii.Error, ValueError) as exc:
        raise SignatureError("Signature image could not be decoded.") from exc

    if not raw.startswith(_PNG_MAGIC):
        raise SignatureError("Signature image is not a PNG.")
    if len(raw) > MAX_SIGNATURE_BYTES:
        raise SignatureError("Signature image is too large.")

    return ContentFile(raw, name=filename or f"{uuid.uuid4().hex}.png")
