from rest_framework import permissions, viewsets

from apps.accounts.permissions import IsAdminRole

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only, admin-only view over the audit trail. Not itself audited
    (that would just recursively log views of the audit log)."""

    queryset = AuditLog.objects.select_related("actor")
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        actor_id = params.get("actor")
        if actor_id:
            queryset = queryset.filter(actor_id=actor_id)

        action_param = params.get("action")
        if action_param:
            actions = [a.strip() for a in action_param.split(",") if a.strip()]
            queryset = queryset.filter(action__in=actions)

        model_name = params.get("model_name")
        if model_name:
            queryset = queryset.filter(model_name=model_name)

        date_from = params.get("date_from")
        if date_from:
            queryset = queryset.filter(timestamp__date__gte=date_from)

        date_to = params.get("date_to")
        if date_to:
            queryset = queryset.filter(timestamp__date__lte=date_to)

        return queryset
