from datetime import timedelta

from django.db.models import Avg
from django.utils import timezone
from rest_framework import serializers

from .models import RecurringTripSeries, Trip, TripType, Weekday
from .services import geo
from .services.maps import GeocodingError, resolve_route
from .services.signature import SignatureError, decode_signature


def resolve_addresses(pickup_address: str, dropoff_address: str) -> dict:
    """Geocode both ends of a booking and measure the drive between them.

    Shared by one-off trips and recurring series so both store the same fields
    and reject the same bad input. Raises DRF ValidationError, so it can be
    called straight out of a serializer's `validate`.
    """
    if geo.normalize(pickup_address) == geo.normalize(dropoff_address):
        raise serializers.ValidationError(
            {"dropoff_address": "Pickup and drop-off cannot be the same address."}
        )

    try:
        route = resolve_route(pickup_address, dropoff_address)
    except GeocodingError as exc:
        raise serializers.ValidationError(str(exc)) from exc

    # Imported here rather than at module scope: apps.operations depends on
    # apps.trips.services.geo, so a top-level import would close the loop.
    from apps.operations.services import ServiceAreaError, check_service_area

    try:
        check_service_area(
            pickup_address,
            (route.pickup_lat, route.pickup_lng),
            dropoff_address,
            (route.dropoff_lat, route.dropoff_lng),
        )
    except ServiceAreaError as exc:
        raise serializers.ValidationError(exc.args[0]) from exc

    return {
        "pickup_lat": route.pickup_lat,
        "pickup_lng": route.pickup_lng,
        "dropoff_lat": route.dropoff_lat,
        "dropoff_lng": route.dropoff_lng,
        "mileage": route.miles,
        "distance_estimated": route.estimated,
        "duration_minutes": route.duration_minutes,
    }


class AssignedDriverNameMixin(serializers.Serializer):
    assigned_driver_name = serializers.SerializerMethodField()

    def get_assigned_driver_name(self, obj):
        if obj.assigned_driver is None:
            return None
        return obj.assigned_driver.user.get_full_name()


class TripListSerializer(AssignedDriverNameMixin, serializers.ModelSerializer):
    class Meta:
        model = Trip
        fields = [
            "id",
            "status",
            "scheduled_pickup_time",
            "pickup_address",
            # Coordinates travel with the list so a map of many trips (the dispatch
            # board's fleet view) doesn't need one detail request per marker.
            "pickup_lat",
            "pickup_lng",
            "dropoff_address",
            "dropoff_lat",
            "dropoff_lng",
            "mileage",
            "distance_estimated",
            "mobility_need",
            "escort_count",
            "trip_type",
            "is_will_call",
            "will_call_requested_at",
            "assigned_driver",
            "assigned_driver_name",
            # Dispatch distinguishes "assigned, waiting on the driver" from
            # "accepted" â€” an unaccepted trip is the one worth reassigning.
            "accepted_at",
            # Why a trip bounced back into the queue, for the dispatcher deciding
            # who to send instead.
            "decline_reason",
            "rating",
        ]
        read_only_fields = [f for f in fields if f != "assigned_driver_name"]


class TripDetailSerializer(AssignedDriverNameMixin, serializers.ModelSerializer):
    # Passenger details for the driver's / admin's active-trip panel. The trip is
    # already permissioned to its participants (rider, assigned driver, admin), so
    # exposing the rider's name/phone/needs here doesn't widen access.
    rider_name = serializers.SerializerMethodField()
    rider_phone = serializers.SerializerMethodField()
    rider_mobility_needs = serializers.SerializerMethodField()
    # Assigned-driver details for the rider's "Your Next Ride" card.
    assigned_driver_rating = serializers.SerializerMethodField()
    assigned_driver_vehicle_plate = serializers.SerializerMethodField()
    assigned_driver_vehicle_type = serializers.SerializerMethodField()

    class Meta:
        model = Trip
        fields = [
            "id",
            "rider",
            "rider_name",
            "rider_phone",
            "rider_mobility_needs",
            "created_by",
            "recurring_series",
            "status",
            "scheduled_pickup_time",
            "pickup_address",
            "pickup_lat",
            "pickup_lng",
            "dropoff_address",
            "dropoff_lat",
            "dropoff_lng",
            "mileage",
            "distance_estimated",
            "estimated_duration_minutes",
            "mobility_need",
            "notes",
            "cancelled_at",
            "cancelled_by",
            "cancellation_reason",
            "assigned_driver",
            "assigned_driver_name",
            "assigned_driver_rating",
            "assigned_driver_vehicle_plate",
            "assigned_driver_vehicle_type",
            "assigned_at",
            "assigned_by",
            "accepted_at",
            "decline_reason",
            "en_route_at",
            "arrived_at",
            "picked_up_at",
            "completed_at",
            "no_show_at",
            "no_show_reason",
            "no_show_waited_minutes",
            "odometer_start",
            "odometer_end",
            "completion_attestation",
            "signature_image",
            "escort_count",
            "trip_type",
            "outbound_trip",
            "is_will_call",
            "will_call_requested_at",
            "rating",
            "review",
            "rated_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            f
            for f in fields
            if f
            not in {
                "assigned_driver_name",
                "rider_name",
                "rider_phone",
                "rider_mobility_needs",
                "assigned_driver_rating",
                "assigned_driver_vehicle_plate",
                "assigned_driver_vehicle_type",
            }
        ]

    def get_rider_name(self, obj):
        return obj.rider.user.get_full_name()

    def get_rider_phone(self, obj):
        return obj.rider.user.phone_number or obj.rider.emergency_contact_phone or None

    def get_rider_mobility_needs(self, obj):
        # Prefer the trip's specific need; fall back to the rider's profile needs.
        if obj.mobility_need:
            return [obj.mobility_need]
        return list(obj.rider.mobility_needs or [])

    def get_assigned_driver_rating(self, obj):
        if obj.assigned_driver is None:
            return None
        avg = obj.assigned_driver.assigned_trips.filter(rating__isnull=False).aggregate(
            v=Avg("rating")
        )["v"]
        return round(avg, 2) if avg is not None else None

    def get_assigned_driver_vehicle_plate(self, obj):
        return obj.assigned_driver.vehicle_plate if obj.assigned_driver else None

    def get_assigned_driver_vehicle_type(self, obj):
        return obj.assigned_driver.vehicle_type if obj.assigned_driver else None


class TripRescheduleSerializer(serializers.Serializer):
    """Move an existing trip. The route doesn't change, so nothing is re-geocoded."""

    scheduled_pickup_time = serializers.DateTimeField()
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class TripRatingSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)

    review = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class TripCompletionSerializer(serializers.Serializer):
    """Drop-off record: the odometer pair, the typed name, and the drawn mark.



    `signature_image` arrives as a data URL from the driver's canvas rather than

    a multipart file, because the whole completion is one JSON POST from a phone

    that may be on a thin connection -- splitting it into two requests would let

    a trip be completed with the signature lost.

    """

    odometer_start = serializers.IntegerField(min_value=0)

    odometer_end = serializers.IntegerField(min_value=0)

    completion_attestation = serializers.CharField(max_length=255, allow_blank=False)

    signature_image = serializers.CharField(write_only=True, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["odometer_end"] < attrs["odometer_start"]:
            raise serializers.ValidationError("odometer_end must be >= odometer_start.")

        driven = attrs["odometer_end"] - attrs["odometer_start"]

        if driven > 2000:
            raise serializers.ValidationError(
                {"odometer_end": f"{driven} miles on one trip is almost certainly a typo."}
            )

        raw = attrs.pop("signature_image", "")

        if raw:
            try:
                attrs["signature_image"] = decode_signature(raw)

            except SignatureError as exc:
                raise serializers.ValidationError({"signature_image": str(exc)}) from exc

        return attrs


class TripCreateSerializer(serializers.ModelSerializer):
    """One-off booking.

    A ROUND_TRIP creates a second Trip for the way home (see
    `services.booking.create_return_leg`), so the return details here are
    write-only inputs rather than fields on this row.

    `rider_id` is only honoured for an admin taking a booking over the phone; a
    rider booking for themselves never supplies it. The role check lives in the
    view's `perform_create`, which is where the actor is known.
    """

    return_pickup_time = serializers.DateTimeField(write_only=True, required=False, allow_null=True)
    return_is_will_call = serializers.BooleanField(write_only=True, required=False, default=False)
    # RiderProfile has an integer primary key, unlike Trip's UUID.
    rider_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = Trip

        fields = [
            "id",
            "status",
            "scheduled_pickup_time",
            "pickup_address",
            "pickup_lat",
            "pickup_lng",
            "dropoff_address",
            "dropoff_lat",
            "dropoff_lng",
            "mileage",
            "distance_estimated",
            "estimated_duration_minutes",
            "mobility_need",
            "escort_count",
            "notes",
            "trip_type",
            "is_will_call",
            "return_pickup_time",
            "return_is_will_call",
            "rider_id",
        ]

        read_only_fields = [
            "id",
            "status",
            "is_will_call",
            "pickup_lat",
            "pickup_lng",
            "dropoff_lat",
            "dropoff_lng",
            "mileage",
            "distance_estimated",
            "estimated_duration_minutes",
        ]

    def validate_scheduled_pickup_time(self, value):
        from apps.operations.models import SystemSetting

        lead_minutes = SystemSetting.load().booking_lead_time_minutes

        earliest = timezone.now() + timedelta(minutes=lead_minutes)

        if value <= earliest:
            if lead_minutes:
                raise serializers.ValidationError(
                    f"Bookings need at least {lead_minutes} minutes' notice."
                )

            raise serializers.ValidationError("Pickup time must be in the future.")

        return value

    def validate_escort_count(self, value):
        if value > 4:
            raise serializers.ValidationError(
                "More than four escorts needs a call to dispatch — no van seats that many."
            )

        return value

    def validate(self, attrs):
        self._validate_return(attrs)

        attrs.update(resolve_addresses(attrs["pickup_address"], attrs["dropoff_address"]))

        attrs["estimated_duration_minutes"] = attrs.pop("duration_minutes")

        return attrs

    def _validate_return(self, attrs):
        is_round = attrs.get("trip_type") == TripType.ROUND_TRIP

        will_call = attrs.get("return_is_will_call", False)

        return_time = attrs.get("return_pickup_time")

        if not is_round:
            if will_call or return_time:
                raise serializers.ValidationError(
                    {"trip_type": "Return details only apply to a round trip."}
                )

            return

        if will_call and return_time:
            raise serializers.ValidationError(
                {"return_pickup_time": "Choose either a return time or will-call, not both."}
            )

        if not will_call and not return_time:
            raise serializers.ValidationError(
                {
                    "return_pickup_time": "Give a return time, or tick will-call if the "
                    "appointment has no set finish."
                }
            )

        if return_time and return_time <= attrs["scheduled_pickup_time"]:
            raise serializers.ValidationError(
                {"return_pickup_time": "The return has to be after the outbound pickup."}
            )


class RecurringTripSeriesDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecurringTripSeries

        fields = [
            "id",
            "rider",
            "pickup_address",
            "pickup_lat",
            "pickup_lng",
            "dropoff_address",
            "dropoff_lat",
            "dropoff_lng",
            "mileage",
            "distance_estimated",
            "pickup_time",
            "weekdays",
            "start_date",
            "end_date",
            "mobility_need",
            "notes",
            "is_active",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields


class RecurringTripSeriesCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecurringTripSeries

        fields = [
            "id",
            "pickup_address",
            "pickup_lat",
            "pickup_lng",
            "dropoff_address",
            "dropoff_lat",
            "dropoff_lng",
            "mileage",
            "distance_estimated",
            "pickup_time",
            "weekdays",
            "start_date",
            "end_date",
            "mobility_need",
            "notes",
            "is_active",
        ]

        read_only_fields = [
            "id",
            "pickup_lat",
            "pickup_lng",
            "dropoff_lat",
            "dropoff_lng",
            "mileage",
            "distance_estimated",
            "is_active",
        ]

    def validate_weekdays(self, value):
        if not value:
            raise serializers.ValidationError("Select at least one weekday.")

        valid_values = {choice for choice, _ in Weekday.choices}

        if not set(value).issubset(valid_values):
            raise serializers.ValidationError("Invalid weekday value.")

        return value

    def validate(self, attrs):
        start_date = attrs.get("start_date")

        end_date = attrs.get("end_date")

        if end_date and start_date and end_date < start_date:
            raise serializers.ValidationError("end_date must be on or after start_date.")

        attrs.update(resolve_addresses(attrs["pickup_address"], attrs["dropoff_address"]))

        # A series has no single duration to store -- each generated trip carries

        # its own. Everything else from the lookup is kept.

        attrs.pop("duration_minutes")

        return attrs
