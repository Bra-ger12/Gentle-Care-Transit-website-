from rest_framework.permissions import BasePermission

from apps.accounts.models import Role


class IsInvoiceOwnerOrAdmin(BasePermission):
    """Object-level: admin/staff, or the invoice's own rider."""

    def has_object_permission(self, request, view, obj):
        if request.user.role == Role.ADMIN or request.user.is_staff:
            return True
        return obj.rider.user_id == request.user.id
