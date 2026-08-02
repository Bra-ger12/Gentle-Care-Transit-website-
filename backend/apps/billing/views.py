from django.utils.dateparse import parse_date
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import IsAdminRole
from apps.audit.mixins import AuditedViewSetMixin, _client_ip
from apps.audit.models import AuditAction, AuditLog

from .models import Invoice, RateSchedule
from .permissions import IsInvoiceOwnerOrAdmin
from .serializers import (
    InvoiceDetailSerializer,
    InvoiceGenerateSerializer,
    InvoiceListSerializer,
    InvoiceMarkPaidSerializer,
    InvoiceVoidSerializer,
    RateScheduleSerializer,
)
from .services import export as export_services
from .services.pricing import (
    InvoiceError,
    finalize_invoice,
    generate_invoice_for_trip,
    generate_pending_invoices,
    mark_invoice_paid,
    void_invoice,
)


class RateScheduleViewSet(AuditedViewSetMixin, viewsets.ModelViewSet):
    queryset = RateSchedule.objects.all()
    serializer_class = RateScheduleSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]
    audit_model_name = "RateSchedule"

    def perform_create(self, serializer):
        schedule = serializer.save()
        self._log(AuditAction.CREATE, schedule)

    def perform_update(self, serializer):
        schedule = serializer.save()
        self._log(AuditAction.UPDATE, schedule)


class InvoiceViewSet(
    AuditedViewSetMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Invoices are never created/edited through generic create/update --
    only through the generate/finalize/void/mark-paid actions below, which
    route through apps.billing.services.pricing so the immutable-once-
    finalized + audited invariants can't be bypassed."""

    queryset = Invoice.objects.select_related("trip", "rider__user", "rate_schedule")
    audit_model_name = "Invoice"

    def get_serializer_class(self):
        if self.action == "list":
            return InvoiceListSerializer
        return InvoiceDetailSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if user.role == Role.ADMIN or user.is_staff:
            return queryset
        if user.role == Role.RIDER:
            return queryset.filter(rider__user=user)
        return queryset.none()

    def get_permissions(self):
        if self.action in ("generate", "finalize", "void", "mark_paid"):
            return [permissions.IsAuthenticated(), IsAdminRole()]
        return [permissions.IsAuthenticated(), IsInvoiceOwnerOrAdmin()]

    @action(detail=False, methods=["post"])
    def generate(self, request):
        serializer = InvoiceGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trip_id = serializer.validated_data.get("trip_id")

        try:
            if trip_id:
                from apps.trips.models import Trip

                trip = Trip.objects.filter(id=trip_id).first()
                if trip is None:
                    raise ValidationError("No trip with that id.")
                invoices = [generate_invoice_for_trip(trip, actor=request.user)]
            else:
                invoices = generate_pending_invoices(actor=request.user)
        except InvoiceError as exc:
            raise ValidationError(str(exc)) from exc

        for invoice in invoices:
            self._log(AuditAction.CREATE, invoice)
        return Response(InvoiceDetailSerializer(invoices, many=True).data)

    @action(detail=True, methods=["post"])
    def finalize(self, request, pk=None):
        invoice = self.get_object()
        try:
            finalize_invoice(invoice, actor=request.user)
        except InvoiceError as exc:
            raise ValidationError(str(exc)) from exc
        self._log(AuditAction.UPDATE, invoice, metadata={"action": "finalized"})
        return Response(InvoiceDetailSerializer(invoice).data)

    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        invoice = self.get_object()
        serializer = InvoiceVoidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            void_invoice(invoice, actor=request.user, reason=serializer.validated_data["reason"])
        except InvoiceError as exc:
            raise ValidationError(str(exc)) from exc
        metadata = {"action": "voided", "reason": invoice.void_reason}
        self._log(AuditAction.UPDATE, invoice, metadata=metadata)
        return Response(InvoiceDetailSerializer(invoice).data)

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        invoice = self.get_object()
        serializer = InvoiceMarkPaidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            mark_invoice_paid(
                invoice,
                actor=request.user,
                payment_reference=serializer.validated_data.get("payment_reference", ""),
            )
        except InvoiceError as exc:
            raise ValidationError(str(exc)) from exc
        self._log(AuditAction.UPDATE, invoice, metadata={"action": "marked_paid"})
        return Response(InvoiceDetailSerializer(invoice).data)


class MedicaidExportView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]

    def get(self, request):
        # NOTE: the query param is `export_format`, not `format` -- DRF
        # reserves `format` for its own content-negotiation override
        # (URL_FORMAT_OVERRIDE) and 404s the request before dispatch ever
        # reaches this method if no renderer is registered for that value.
        date_from = parse_date(request.query_params.get("date_from", ""))
        date_to = parse_date(request.query_params.get("date_to", ""))
        fmt = request.query_params.get("export_format", "csv").lower()

        if date_from is None or date_to is None:
            raise ValidationError("date_from and date_to (YYYY-MM-DD) query params are required.")
        if fmt not in ("csv", "pdf"):
            raise ValidationError("export_format must be 'csv' or 'pdf'.")

        if fmt == "csv":
            response = export_services.render_medicaid_csv(date_from, date_to)
        else:
            response = export_services.render_medicaid_pdf(date_from, date_to)

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.EXPORT,
            model_name="MedicaidExport",
            object_id=f"{date_from}:{date_to}",
            ip_address=_client_ip(request),
            metadata={"format": fmt},
        )
        return response
