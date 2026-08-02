from rest_framework import serializers

from .models import DriverPayRate, TripEarning


class DriverPayRateSerializer(serializers.ModelSerializer):
    driver_name = serializers.SerializerMethodField()

    class Meta:
        model = DriverPayRate
        fields = [
            "id",
            "driver",
            "driver_name",
            "per_trip_base",
            "per_mile_rate",
            "effective_from",
            "effective_to",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "driver_name", "created_at", "updated_at"]

    def get_driver_name(self, obj):
        if obj.driver is None:
            return None
        return obj.driver.user.get_full_name() or obj.driver.user.email

    def validate(self, attrs):
        start = attrs.get("effective_from", getattr(self.instance, "effective_from", None))
        end = attrs.get("effective_to", getattr(self.instance, "effective_to", None))
        if start and end and end < start:
            raise serializers.ValidationError(
                {"effective_to": "effective_to must be on or after effective_from."}
            )
        return attrs


class TripEarningSerializer(serializers.ModelSerializer):
    driver_name = serializers.SerializerMethodField()
    is_paid = serializers.BooleanField(read_only=True)
    trip_route = serializers.SerializerMethodField()

    class Meta:
        model = TripEarning
        fields = [
            "id",
            "trip",
            "trip_route",
            "driver",
            "driver_name",
            "earned_on",
            "mileage_snapshot",
            "per_trip_base",
            "per_mile_rate",
            "mileage_amount",
            "total_amount",
            "is_paid",
            "paid_at",
            "payment_reference",
            "created_at",
        ]
        read_only_fields = fields

    def get_driver_name(self, obj):
        return obj.driver.user.get_full_name() or obj.driver.user.email

    def get_trip_route(self, obj):
        return f"{obj.trip.pickup_address} → {obj.trip.dropoff_address}"


class EarningMarkPaidSerializer(serializers.Serializer):
    payment_reference = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )


class EarningsSummarySerializer(serializers.Serializer):
    """Read-only shape returned by the summary endpoint."""

    trips = serializers.IntegerField()
    total_earned = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_miles = serializers.DecimalField(max_digits=8, decimal_places=2)
    unpaid_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
