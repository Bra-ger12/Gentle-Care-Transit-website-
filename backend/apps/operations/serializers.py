from rest_framework import serializers

from apps.trips.services import geo

from .models import ServiceArea, ServiceAreaKind, SystemSetting


class ServiceAreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceArea
        fields = [
            "id",
            "name",
            "kind",
            "place",
            "center_lat",
            "center_lng",
            "radius_miles",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        merged = {**getattr(self.instance, "__dict__", {}), **attrs}
        kind = merged.get("kind")

        if kind == ServiceAreaKind.PLACE:
            place = (merged.get("place") or "").strip()
            if not place:
                raise serializers.ValidationError({"place": "Name the town this rule covers."})
            # Must be a town the geocoder knows, or the rule can never match.
            if geo.normalize(place) not in geo.ND_PLACES:
                raise serializers.ValidationError(
                    {
                        "place": f"{place!r} isn't a town this system knows. "
                        "Use a radius rule to cover somewhere unlisted."
                    }
                )
            attrs["place"] = geo.normalize(place)

        elif kind == ServiceAreaKind.RADIUS:
            missing = [
                field
                for field in ("center_lat", "center_lng", "radius_miles")
                if merged.get(field) in (None, "")
            ]
            if missing:
                raise serializers.ValidationError(
                    {field: "Required for a radius rule." for field in missing}
                )
            if merged["radius_miles"] <= 0:
                raise serializers.ValidationError(
                    {"radius_miles": "Radius must be greater than zero."}
                )

        return attrs


class SystemSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSetting
        fields = [
            "enforce_service_area",
            "require_verified_email_to_book",
            "cancellation_cutoff_hours",
            "booking_lead_time_minutes",
            "no_show_wait_minutes",
            "template_trip_confirmed",
            "template_driver_assigned",
            "template_driver_en_route",
            "template_trip_reminder",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate_cancellation_cutoff_hours(self, value):
        if value > 168:
            raise serializers.ValidationError(
                "A cutoff beyond a week is almost certainly a mistake."
            )
        return value

    def validate_no_show_wait_minutes(self, value):
        if value > 120:
            raise serializers.ValidationError(
                "Drivers cannot be asked to wait more than two hours."
            )
        return value


class PlaceOptionSerializer(serializers.Serializer):
    """The towns a PLACE rule may name, for the settings screen's picker."""

    name = serializers.CharField()
    lat = serializers.FloatField()
    lng = serializers.FloatField()
