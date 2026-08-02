from rest_framework.permissions import BasePermission

from apps.accounts.models import Role


class IsTripParticipant(BasePermission):
    """Object-level: admin/staff, or the trip's own rider."""

    def has_object_permission(self, request, view, obj):
        if request.user.role == Role.ADMIN or request.user.is_staff:
            return True
        return obj.rider.user_id == request.user.id


class IsAssignedDriver(BasePermission):
    """Object-level: the trip's currently assigned driver."""

    def has_object_permission(self, request, view, obj):
        return obj.assigned_driver is not None and obj.assigned_driver.user_id == request.user.id
