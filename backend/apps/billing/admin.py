from django.contrib import admin

from .models import Invoice, RateSchedule


@admin.register(RateSchedule)
class RateScheduleAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "mobility_need",
        "base_fare",
        "per_mile_rate",
        "effective_from",
        "effective_to",
        "is_active",
    ]
    list_filter = ["mobility_need", "is_active"]


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        "invoice_number",
        "rider_name_snapshot",
        "status",
        "total_amount",
        "created_at",
    ]
    list_filter = ["status"]
    search_fields = ["invoice_number", "rider_name_snapshot", "medicaid_id_snapshot"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
