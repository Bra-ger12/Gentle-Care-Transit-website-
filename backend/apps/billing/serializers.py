from rest_framework import serializers

from .models import Invoice, RateSchedule


class RateScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RateSchedule
        fields = [
            "id",
            "mobility_need",
            "base_fare",
            "per_mile_rate",
            "wheelchair_surcharge",
            "stretcher_surcharge",
            "free_wait_minutes",
            "wait_time_rate_per_minute",
            "effective_from",
            "effective_to",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class InvoiceListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = [
            "id",
            "invoice_number",
            "trip",
            "rider",
            "status",
            "rider_name_snapshot",
            "total_amount",
            "created_at",
            "finalized_at",
            "paid_at",
        ]
        read_only_fields = fields


class InvoiceDetailSerializer(serializers.ModelSerializer):
    payer_type = serializers.CharField(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "invoice_number",
            "trip",
            "rider",
            "rate_schedule",
            "status",
            "rider_name_snapshot",
            "medicaid_id_snapshot",
            "prior_auth_snapshot",
            "mobility_need_snapshot",
            "mileage_snapshot",
            "base_fare",
            "per_mile_rate",
            "mileage_amount",
            "surcharge_amount",
            "billable_wait_minutes",
            "wait_time_amount",
            "total_amount",
            "payer_type",
            "generated_by",
            "finalized_at",
            "finalized_by",
            "paid_at",
            "paid_by",
            "payment_reference",
            "voided_at",
            "voided_by",
            "void_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class InvoiceGenerateSerializer(serializers.Serializer):
    trip_id = serializers.UUIDField(required=False)


class InvoiceVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, allow_blank=False)


class InvoiceMarkPaidSerializer(serializers.Serializer):
    payment_reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
