from rest_framework.permissions import BasePermission

from .models import Role


class IsRider(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and request.user.role == Role.RIDER
        )


class IsDriver(BasePermission):
    """Requires role=DRIVER and an approved DriverProfile."""

    def has_permission(self, request, view):
        if not (
            request.user and request.user.is_authenticated and request.user.role == Role.DRIVER
        ):
            return False
        return getattr(request.user, "driverprofile", None) is not None and (
            request.user.driverprofile.is_approved
        )


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.role == Role.ADMIN or request.user.is_staff)
        )


class IsOwnerOrAdmin(BasePermission):
    """Object-level: the object's `user` FK matches the requester, or requester is admin."""

    def has_object_permission(self, request, view, obj):
        if request.user.role == Role.ADMIN or request.user.is_staff:
            return True
        owner = getattr(obj, "user", obj)
        return owner == request.user
