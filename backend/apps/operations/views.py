from rest_framework import permissions, viewsets
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminRole
from apps.audit.mixins import AuditedRetrieveUpdateMixin, AuditedViewSetMixin
from apps.audit.models import AuditAction
from apps.trips.services import geo

from .models import ServiceArea, SystemSetting
from .serializers import (
    PlaceOptionSerializer,
    ServiceAreaSerializer,
    SystemSettingSerializer,
)


class ServiceAreaViewSet(AuditedViewSetMixin, viewsets.ModelViewSet):
    """Where the service runs. Admin-only to change; every change is audited,
    because narrowing the service area is what stops riders being able to book."""

    queryset = ServiceArea.objects.all()
    serializer_class = ServiceAreaSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]
    audit_model_name = "ServiceArea"

    def perform_create(self, serializer):
        self._log(AuditAction.CREATE, serializer.save())

    def perform_update(self, serializer):
        self._log(AuditAction.UPDATE, serializer.save())

    def perform_destroy(self, instance):
        self._log(AuditAction.DELETE, instance)
        instance.delete()


class SystemSettingView(AuditedRetrieveUpdateMixin, RetrieveUpdateAPIView):
    serializer_class = SystemSettingSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]
    audit_model_name = "SystemSetting"

    def get_object(self):
        return SystemSetting.load()

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class PlaceOptionsView(APIView):
    """Towns a PLACE service-area rule may name.

    Public to any signed-in user: the booking form uses it to tell a rider which
    towns are recognised before they submit an address we'd have to reject.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        places = [
            {"name": name.title(), "lat": lat, "lng": lng}
            for name, (lat, lng) in sorted(geo.ND_PLACES.items())
        ]
        return Response(PlaceOptionSerializer(places, many=True).data)


class ServiceAreaSummaryView(APIView):
    """What the current service area is, in words -- for the booking form and
    the landing page. Readable by any signed-in user."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        setting = SystemSetting.load()
        areas = ServiceArea.objects.filter(is_active=True)
        return Response(
            {
                "enforced": setting.enforce_service_area and areas.exists(),
                "areas": ServiceAreaSerializer(areas, many=True).data,
                "cancellation_cutoff_hours": setting.cancellation_cutoff_hours,
                "booking_lead_time_minutes": setting.booking_lead_time_minutes,
                "no_show_wait_minutes": setting.no_show_wait_minutes,
            }
        )
