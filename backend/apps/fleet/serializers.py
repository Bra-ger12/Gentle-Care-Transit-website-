from django.utils import timezone
from rest_framework import serializers

from .models import DefectItem, VehicleInspection


class VehicleInspectionSerializer(serializers.ModelSerializer):
    driver_name = serializers.SerializerMethodField()
    has_defects = serializers.BooleanField(read_only=True)
    needs_attention = serializers.BooleanField(read_only=True)

    class Meta:
        model = VehicleInspection
        fields = [
            "id",
            "driver",
            "driver_name",
            "inspection_type",
            "performed_at",
            "inspected_on",
            "vehicle_plate_snapshot",
            "vehicle_type_snapshot",
            "odometer",
            "defects",
            "defect_notes",
            "safe_to_operate",
            "signature",
            "has_defects",
            "needs_attention",
            "reviewed_at",
            "reviewed_by",
            "resolution_notes",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "driver",
            "driver_name",
            "performed_at",
            "inspected_on",
            "vehicle_plate_snapshot",
            "vehicle_type_snapshot",
            "has_defects",
            "needs_attention",
            "reviewed_at",
            "reviewed_by",
            "resolution_notes",
            "created_at",
        ]

    def get_driver_name(self, obj):
        return obj.driver.user.get_full_name() or obj.driver.user.email

    def validate_defects(self, value):
        valid = set(DefectItem.values)
        invalid = set(value) - valid
        if invalid:
            raise serializers.ValidationError(f"Unknown checklist items: {sorted(invalid)}")
        return value

    def validate(self, attrs):
        defects = attrs.get("defects", [])
        notes = (attrs.get("defect_notes") or "").strip()
        # A flagged defect without a description is useless to whoever fixes it.
        if defects and not notes:
            raise serializers.ValidationError({"defect_notes": "Describe the defect you found."})
        if not (attrs.get("signature") or "").strip():
            raise serializers.ValidationError(
                {"signature": "Type your name to certify this report."}
            )
        return attrs

    def create(self, validated_data):
        driver = self.context["driver"]
        now = timezone.now()
        # One report per driver per day per type: re-submitting corrects the day's
        # report rather than stacking duplicates (matches the DB constraint).
        inspection, _ = VehicleInspection.objects.update_or_create(
            driver=driver,
            inspected_on=timezone.localtime(now).date(),
            inspection_type=validated_data["inspection_type"],
            defaults={
                **validated_data,
                "performed_at": now,
                "vehicle_plate_snapshot": driver.vehicle_plate,
                "vehicle_type_snapshot": driver.vehicle_type,
                "reviewed_at": None,
                "reviewed_by": None,
                "resolution_notes": "",
            },
        )
        return inspection


class InspectionReviewSerializer(serializers.Serializer):
    resolution_notes = serializers.CharField(
        max_length=2000, required=False, allow_blank=True, default=""
    )


class DefectItemSerializer(serializers.Serializer):
    """The checklist itself, so the frontend never hard-codes the item list."""

    value = serializers.CharField()
    label = serializers.CharField()
