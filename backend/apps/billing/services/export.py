"""ND Medicaid NEMT reimbursement export.

This produces a reasonable, generic NEMT reimbursement export (trip date,
member ID, prior authorisation, rider name, mileage, pickup/drop-off times,
mobility tier, fare breakdown, signature reference, total) -- it is NOT a
certified replica of North Dakota's official DHS claim form. The actual state
billing-manual field layout wasn't available when this was built; adjust
CSV_COLUMNS and the PDF table to match once it is.

The PDF is drawn with ReportLab rather than rendered from HTML. WeasyPrint needs
native GTK/Pango/cairo libraries that pip cannot install, so on a plain Windows
or slim Linux box the export simply failed. A claim export that only works on
some machines is not an export.
"""

import csv

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .. import models as billing_models

CSV_COLUMNS = [
    "invoice_number",
    "trip_date",
    "medicaid_id",
    "prior_auth_number",
    "rider_name",
    "pickup_address",
    "pickup_time",
    "dropoff_address",
    "dropoff_time",
    "mileage",
    "mileage_source",
    "mobility_need",
    "escorts",
    "base_fare",
    "mileage_amount",
    "surcharge_amount",
    "wait_minutes",
    "wait_amount",
    "total_amount",
    "signature_reference",
    "status",
]

# Columns that fit legibly on a landscape page. The CSV carries everything; the
# PDF is the human-readable summary that accompanies it.
PDF_COLUMNS = [
    "Invoice",
    "Date",
    "Member ID",
    "Prior auth",
    "Rider",
    "Miles",
    "Pickup",
    "Drop-off",
    "Signature",
    "Total",
]


def medicaid_export_queryset(date_from, date_to):
    return (
        billing_models.Invoice.objects.filter(
            status__in=[
                billing_models.InvoiceStatus.FINALIZED,
                billing_models.InvoiceStatus.PAID,
            ],
            trip__completed_at__date__range=(date_from, date_to),
        )
        .exclude(medicaid_id_snapshot__isnull=True)
        .exclude(medicaid_id_snapshot="")
        .select_related("trip", "rider__user")
        .order_by("trip__completed_at")
    )


def _local_time(value) -> str:
    return timezone.localtime(value).strftime("%H:%M") if value else ""


def signature_reference(trip) -> str:
    """What the claim points at as proof the ride was delivered.

    Prefers the stored signature file, which is the actual mark the rider made.
    Falls back to the typed attestation, and says so, rather than implying a
    signature exists when only a typed name does.
    """
    if trip.signature_image:
        return trip.signature_image.name
    if trip.completion_attestation:
        return f"attested: {trip.completion_attestation}"
    return ""


def _row_for(invoice):
    trip = invoice.trip
    return [
        invoice.invoice_number,
        timezone.localtime(trip.completed_at).date().isoformat(),
        invoice.medicaid_id_snapshot,
        invoice.prior_auth_snapshot,
        invoice.rider_name_snapshot,
        trip.pickup_address,
        _local_time(trip.picked_up_at),
        trip.dropoff_address,
        _local_time(trip.completed_at),
        str(invoice.mileage_snapshot),
        "estimated" if trip.distance_estimated else "measured",
        invoice.mobility_need_snapshot,
        trip.escort_count,
        str(invoice.base_fare),
        str(invoice.mileage_amount),
        str(invoice.surcharge_amount),
        invoice.billable_wait_minutes,
        str(invoice.wait_time_amount),
        str(invoice.total_amount),
        signature_reference(trip),
        invoice.status,
    ]


def render_medicaid_csv(date_from, date_to) -> HttpResponse:
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="medicaid_export_{date_from}_{date_to}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(CSV_COLUMNS)
    for invoice in medicaid_export_queryset(date_from, date_to):
        writer.writerow(_row_for(invoice))
    return response


def _pdf_row(invoice):
    trip = invoice.trip
    reference = signature_reference(trip)
    return [
        invoice.invoice_number,
        timezone.localtime(trip.completed_at).date().isoformat(),
        invoice.medicaid_id_snapshot,
        invoice.prior_auth_snapshot or "—",
        invoice.rider_name_snapshot,
        str(invoice.mileage_snapshot),
        _local_time(trip.picked_up_at),
        _local_time(trip.completed_at),
        "on file" if trip.signature_image else ("typed" if reference else "—"),
        f"${invoice.total_amount}",
    ]


def render_medicaid_pdf(date_from, date_to) -> HttpResponse:
    invoices = list(medicaid_export_queryset(date_from, date_to))
    total = sum(invoice.total_amount for invoice in invoices)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="medicaid_export_{date_from}_{date_to}.pdf"'
    )

    document = SimpleDocTemplate(
        response,
        pagesize=landscape(letter),
        title=f"NEMT reimbursement {date_from} to {date_to}",
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )

    styles = getSampleStyleSheet()
    right = ParagraphStyle("right", parent=styles["Normal"], alignment=TA_RIGHT)
    story = [
        Paragraph("Gentle Care Transit — NEMT reimbursement claim", styles["Title"]),
        Paragraph(
            f"Trips completed {date_from} to {date_to} · "
            f"{len(invoices)} claim(s) · generated "
            f"{timezone.localtime().strftime('%Y-%m-%d %H:%M')}",
            styles["Normal"],
        ),
        Spacer(1, 0.25 * inch),
    ]

    if invoices:
        data = [PDF_COLUMNS] + [_pdf_row(invoice) for invoice in invoices]
        table = Table(data, repeatRows=1, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0E1B26")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ALIGN", (5, 1), (5, -1), "RIGHT"),
                    ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B9C6D1")),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#F2F5F8")],
                    ),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story += [table, Spacer(1, 0.2 * inch), Paragraph(f"<b>Total claimed: ${total}</b>", right)]
    else:
        story.append(
            Paragraph(
                "No finalised or paid Medicaid trips completed in this period.",
                styles["Normal"],
            )
        )

    document.build(story)
    return response
