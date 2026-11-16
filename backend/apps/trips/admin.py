from django.contrib import admin

from .models import RecurringTripSeries, Service, Trip


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    # NEW: Django admins can maintain per-kilometer prices for each service tier.
    list_display = [
        "name",
        "cost_per_km",
        "base_fee",
        "minimum_fare",
        "is_active",
        "updated_at",
    ]
    list_filter = ["is_active"]
    search_fields = ["name"]
    ordering = ["name"]


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "rider",
        "status",
        "scheduled_pickup_time",
        "pickup_address",
        "dropoff_address",
        "mileage",
        "service_name_snapshot",
        "distance_km",
        "total_cost",
        "assigned_driver",
    ]
    list_filter = ["status", "service", "distance_estimated"]
    search_fields = ["rider__user__email", "pickup_address", "dropoff_address"]


@admin.register(RecurringTripSeries)
class RecurringTripSeriesAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "rider",
        "pickup_time",
        "start_date",
        "end_date",
        "service_name_snapshot",
        "distance_km",
        "total_cost",
        "is_active",
    ]
    list_filter = ["is_active", "service", "distance_estimated"]
    search_fields = ["rider__user__email", "pickup_address", "dropoff_address"]
