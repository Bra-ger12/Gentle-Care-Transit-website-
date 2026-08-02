from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import DriverProfile, RiderProfile, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["-date_joined"]
    list_display = [
        "email",
        "phone_number",
        "role",
        "is_active",
        "is_verified",
        "is_staff",
    ]
    list_filter = ["role", "is_active", "is_verified", "is_staff"]
    search_fields = ["email", "phone_number", "first_name", "last_name"]
    readonly_fields = ["date_joined", "last_login"]
    fieldsets = (
        (None, {"fields": ("email", "phone_number", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "role")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "is_verified",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "phone_number",
                    "role",
                    "password1",
                    "password2",
                ),
            },
        ),
    )


@admin.register(RiderProfile)
class RiderProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "city", "state", "medicaid_id"]
    search_fields = ["user__email", "medicaid_id"]


@admin.register(DriverProfile)
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "vehicle_type",
        "background_check_status",
        "is_approved",
        "license_expiry_date",
        "rejection_reason",
    ]
    list_filter = ["vehicle_type", "background_check_status", "is_approved"]
    search_fields = ["user__email", "license_number", "vehicle_plate"]
