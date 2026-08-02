from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import IsAdminRole, IsDriver
from apps.audit.mixins import AuditedViewSetMixin
from apps.audit.models import AuditAction

from .models import DefectItem, InspectionType, VehicleInspection
from .serializers import (
    DefectItemSerializer,
    InspectionReviewSerializer,
    VehicleInspectionSerializer,
)


class ChecklistView(APIView):
    """The DVIR checklist, served so the form and the admin view stay in step
    with the model's choices instead of duplicating them in JS."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        items = [{"value": value, "label": label} for value, label in DefectItem.choices]
        types = [{"value": value, "label": label} for value, label in InspectionType.choices]
        return Response(
            {"items": DefectItemSerializer(items, many=True).data, "inspection_types": types}
        )


class VehicleInspectionViewSet(
    AuditedViewSetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Drivers file their own reports and see their own history; admins see every
    report and clear the ones that flagged a defect. Reports are never edited
    after review -- a correction is a fresh submission for that day."""

    queryset = VehicleInspection.objects.select_related("driver__user")
    serializer_class = VehicleInspectionSerializer
    audit_model_name = "VehicleInspection"

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if user.role == Role.ADMIN or user.is_staff:
            pass
        elif user.role == Role.DRIVER:
            queryset = queryset.filter(driver__user=user)
        else:
            return queryset.none()

        date_param = self.request.query_params.get("date")
        if date_param:
            try:
                inspected_on = parse_date(date_param)
            except ValueError:
                inspected_on = None
            if inspected_on is None:
                raise ValidationError({"date": "Expected a date as YYYY-MM-DD."})
            queryset = queryset.filter(inspected_on=inspected_on)

        if (self.request.query_params.get("needs_attention") or "").lower() == "true":
            queryset = queryset.filter(reviewed_at__isnull=True).exclude(
                defects=[], safe_to_operate=True
            )
        return queryset

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated(), IsDriver()]
        if self.action == "review":
            return [permissions.IsAuthenticated(), IsAdminRole()]
        return [permissions.IsAuthenticated()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.request.user.is_authenticated and self.request.user.role == Role.DRIVER:
            context["driver"] = self.request.user.driverprofile
        return context

    def perform_create(self, serializer):
        inspection = serializer.save()
        self._log(AuditAction.CREATE, inspection)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        """An admin signs off a report, closing out whatever it flagged."""
        inspection = self.get_object()
        serializer = InspectionReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inspection.reviewed_at = timezone.now()
        inspection.reviewed_by = request.user
        inspection.resolution_notes = serializer.validated_data["resolution_notes"]
        inspection.save(
            update_fields=["reviewed_at", "reviewed_by", "resolution_notes", "updated_at"]
        )
        self._log(AuditAction.UPDATE, inspection, metadata={"action": "reviewed"})
        return Response(VehicleInspectionSerializer(inspection).data)

    @action(detail=False, methods=["get"], url_path="today")
    def today(self, request):
        """What the signed-in driver has filed today -- the board's DVIR status."""
        if request.user.role != Role.DRIVER:
            self.permission_denied(request)
        filed = VehicleInspection.objects.filter(
            driver__user=request.user, inspected_on=timezone.localdate()
        )
        return Response(VehicleInspectionSerializer(filed, many=True).data)
