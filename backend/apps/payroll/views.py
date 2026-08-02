from django.utils.dateparse import parse_date
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import DriverProfile, Role
from apps.accounts.permissions import IsAdminRole
from apps.audit.mixins import AuditedViewSetMixin
from apps.audit.models import AuditAction

from .models import DriverPayRate, TripEarning
from .serializers import (
    DriverPayRateSerializer,
    EarningMarkPaidSerializer,
    EarningsSummarySerializer,
    TripEarningSerializer,
)
from .services.earnings import (
    EarningError,
    earnings_summary,
    generate_pending_earnings,
    mark_earning_paid,
)


def _range(request):
    """Optional ?date_from=&date_to= (YYYY-MM-DD), rejected rather than ignored
    when malformed -- a silently dropped filter would overstate a payout."""
    parsed = []
    for key in ("date_from", "date_to"):
        raw = request.query_params.get(key)
        if not raw:
            parsed.append(None)
            continue
        try:
            value = parse_date(raw)
        except ValueError:
            value = None
        if value is None:
            raise ValidationError({key: "Expected a date as YYYY-MM-DD."})
        parsed.append(value)
    return tuple(parsed)


class DriverPayRateViewSet(AuditedViewSetMixin, viewsets.ModelViewSet):
    """Admin-managed. A rate with no driver is the house default; one with a
    driver overrides it for that driver only."""

    queryset = DriverPayRate.objects.select_related("driver__user")
    serializer_class = DriverPayRateSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]
    audit_model_name = "DriverPayRate"

    def perform_create(self, serializer):
        rate = serializer.save()
        self._log(AuditAction.CREATE, rate)

    def perform_update(self, serializer):
        rate = serializer.save()
        self._log(AuditAction.UPDATE, rate)


class TripEarningViewSet(
    AuditedViewSetMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Earnings are never created or edited directly -- only generated from
    completed trips and marked paid, both through services.earnings, so the
    snapshot stays the record of what was owed."""

    queryset = TripEarning.objects.select_related("trip", "driver__user", "pay_rate")
    serializer_class = TripEarningSerializer
    audit_model_name = "TripEarning"

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if user.role == Role.ADMIN or user.is_staff:
            queryset = queryset
        elif user.role == Role.DRIVER:
            queryset = queryset.filter(driver__user=user)
        else:
            return queryset.none()

        date_from, date_to = _range(self.request)
        if date_from:
            queryset = queryset.filter(earned_on__gte=date_from)
        if date_to:
            queryset = queryset.filter(earned_on__lte=date_to)
        unpaid = self.request.query_params.get("unpaid")
        if unpaid and unpaid.lower() == "true":
            queryset = queryset.filter(paid_at__isnull=True)
        return queryset

    def get_permissions(self):
        if self.action in ("generate", "mark_paid"):
            return [permissions.IsAuthenticated(), IsAdminRole()]
        return [permissions.IsAuthenticated()]

    @action(detail=False, methods=["post"])
    def generate(self, request):
        """Create earnings for every completed trip that doesn't have one."""
        try:
            earnings = generate_pending_earnings(actor=request.user)
        except EarningError as exc:
            raise ValidationError(str(exc)) from exc
        for earning in earnings:
            self._log(AuditAction.CREATE, earning)
        return Response(
            {"generated": len(earnings), "results": TripEarningSerializer(earnings, many=True).data}
        )

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        earning = self.get_object()
        serializer = EarningMarkPaidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            mark_earning_paid(
                earning,
                actor=request.user,
                payment_reference=serializer.validated_data["payment_reference"],
            )
        except EarningError as exc:
            raise ValidationError(str(exc)) from exc
        self._log(AuditAction.UPDATE, earning, metadata={"action": "paid"})
        return Response(TripEarningSerializer(earning).data)


class MyEarningsSummaryView(APIView):
    """Totals for the signed-in driver: what the board's Earn tile and the
    driver's report show. Admins pass ?driver=<id> to see anyone's."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        date_from, date_to = _range(request)
        driver_id = request.query_params.get("driver")

        if driver_id:
            if request.user.role != Role.ADMIN and not request.user.is_staff:
                self.permission_denied(request)
            driver = DriverProfile.objects.filter(pk=driver_id).first()
            if driver is None:
                raise ValidationError({"driver": "No such driver."})
        else:
            if request.user.role != Role.DRIVER:
                self.permission_denied(request)
            driver = request.user.driverprofile

        summary = earnings_summary(driver, date_from=date_from, date_to=date_to)
        return Response(EarningsSummarySerializer(summary).data)
