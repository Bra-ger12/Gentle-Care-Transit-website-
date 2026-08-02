from django.contrib import admin

from .models import RecurringTripSeries, Trip


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
        "assigned_driver",
    ]
    list_filter = ["status"]
    search_fields = ["rider__user__email", "pickup_address", "dropoff_address"]


@admin.register(RecurringTripSeries)
class RecurringTripSeriesAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "rider",
        "pickup_time",
        "start_date",
        "end_date",
        "is_active",
    ]
    list_filter = ["is_active"]
    search_fields = ["rider__user__email", "pickup_address", "dropoff_address"]
