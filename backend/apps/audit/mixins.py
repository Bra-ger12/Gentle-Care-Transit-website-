from .models import AuditAction, AuditLog


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class AuditedRetrieveUpdateMixin:
    """Logs who viewed/edited a record -- required for PHI-adjacent data (RiderProfile, etc.)."""

    audit_model_name: str = ""

    def _log(self, action, obj):
        AuditLog.objects.create(
            actor=self.request.user if self.request.user.is_authenticated else None,
            action=action,
            model_name=self.audit_model_name or obj.__class__.__name__,
            object_id=str(obj.pk),
            ip_address=_client_ip(self.request),
        )

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        self._log(AuditAction.VIEW, self.get_object())
        return response

    def update(self, request, *args, **kwargs):
        obj = self.get_object()
        response = super().update(request, *args, **kwargs)
        self._log(AuditAction.UPDATE, obj)
        return response


class AuditedViewSetMixin:
    """Same VIEW-logging behavior as AuditedRetrieveUpdateMixin, for GenericViewSet-based views."""

    audit_model_name: str = ""

    def _log(self, action, obj, metadata=None):
        AuditLog.objects.create(
            actor=self.request.user if self.request.user.is_authenticated else None,
            action=action,
            model_name=self.audit_model_name or obj.__class__.__name__,
            object_id=str(obj.pk),
            ip_address=_client_ip(self.request),
            metadata=metadata or {},
        )

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        self._log(AuditAction.VIEW, self.get_object())
        return response
