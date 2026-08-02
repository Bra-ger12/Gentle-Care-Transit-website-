"""Upload validation for driver documents.

A driver's insurance certificate is uploaded by an unapproved account -- someone
who has registered but whom nobody has vetted yet. That makes it the least
trusted input in the system, so it is checked on content rather than on what the
browser claims: extension, declared MIME type, real size, and the file's own
magic bytes.
"""

from django.core.exceptions import ValidationError

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024  # 10 MB — a photographed certificate, generously

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
ALLOWED_CONTENT_TYPES = {"application/pdf", "image/png", "image/jpeg"}

# First bytes of each format we accept. A browser's declared content type is
# attacker-controlled; these are not.
MAGIC_PREFIXES = (
    b"%PDF-",  # PDF
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"\xff\xd8\xff",  # JPEG
)


def validate_document(upload):
    """Raise ValidationError unless this really is a PDF or a photo."""
    if upload is None:
        return upload

    name = (getattr(upload, "name", "") or "").lower()
    if not any(name.endswith(extension) for extension in ALLOWED_EXTENSIONS):
        raise ValidationError(
            "Upload a PDF or a photo (.pdf, .png, .jpg)."
        )

    size = getattr(upload, "size", 0) or 0
    if size > MAX_DOCUMENT_BYTES:
        raise ValidationError(
            f"That file is {size // (1024 * 1024)} MB. The limit is "
            f"{MAX_DOCUMENT_BYTES // (1024 * 1024)} MB."
        )
    if size == 0:
        raise ValidationError("That file is empty.")

    content_type = getattr(upload, "content_type", None)
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError(f"{content_type} files aren't accepted here.")

    head = upload.read(8)
    upload.seek(0)
    if not any(head.startswith(prefix) for prefix in MAGIC_PREFIXES):
        raise ValidationError(
            "That file isn't a readable PDF or image, whatever its name says."
        )

    return upload
