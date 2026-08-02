from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.db.models import Avg
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .emails import email_verification_token
from .models import (
    DriverAvailability,
    DriverProfile,
    DriverTimeOff,
    MobilityNeed,
    RiderProfile,
    Role,
    VehicleType,
)
from .validators import validate_document

LICENSE_EXPIRY_WARNING_DAYS = 30

User = get_user_model()


class IdentifierTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Accepts `identifier` (email or phone) instead of a fixed USERNAME_FIELD."""

    username_field = "identifier"

    def validate(self, attrs):
        identifier = attrs.get("identifier")
        password = attrs.get("password")

        user = authenticate(
            request=self.context.get("request"),
            username=identifier,
            password=password,
        )
        if user is None:
            raise AuthenticationFailed("No active account found with the given credentials.")

        data = {}
        refresh = self.get_token(user)
        data["refresh"] = str(refresh)
        data["access"] = str(refresh.access_token)
        self.user = user
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["is_verified"] = user.is_verified
        token["email"] = user.email
        return token


class RiderProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiderProfile
        fields = [
            "date_of_birth",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "zip_code",
            "emergency_contact_name",
            "emergency_contact_phone",
            "mobility_needs",
            "medicaid_id",
            "prior_auth_number",
        ]

    def validate_mobility_needs(self, value):
        valid = set(MobilityNeed.values)
        invalid = set(value) - valid
        if invalid:
            raise serializers.ValidationError(f"Invalid mobility needs: {invalid}")
        return value


class DriverRatingMixin(serializers.Serializer):
    """Adds each driver's average performance rating, computed from the ratings
    riders left on that driver's completed trips."""

    average_rating = serializers.SerializerMethodField()
    ratings_count = serializers.SerializerMethodField()

    def get_average_rating(self, obj):
        avg = obj.assigned_trips.filter(rating__isnull=False).aggregate(v=Avg("rating"))["v"]
        return round(avg, 2) if avg is not None else None

    def get_ratings_count(self, obj):
        return obj.assigned_trips.filter(rating__isnull=False).count()


class DriverProfileSerializer(DriverRatingMixin, serializers.ModelSerializer):
    # The upload is checked on content, not on what the browser claims. See
    # accounts.validators -- this arrives from an account nobody has vetted yet.
    insurance_document = serializers.FileField(
        required=False, allow_null=True, validators=[validate_document]
    )

    class Meta:
        model = DriverProfile
        fields = [
            "license_number",
            "license_expiry_date",
            "vehicle_type",
            "vehicle_plate",
            "vehicle_capacity",
            "insurance_document",
            "background_check_status",
            "is_approved",
            "is_available",
            "average_rating",
            "ratings_count",
        ]
        read_only_fields = ["background_check_status", "is_approved"]

    def validate_license_expiry_date(self, value):
        if value and value < timezone.localdate():
            raise serializers.ValidationError(
                "That licence has already expired. Renew it before driving."
            )
        return value


class DriverProfileAdminSerializer(DriverRatingMixin, serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)
    license_expiring_soon = serializers.SerializerMethodField()
    license_expired = serializers.SerializerMethodField()

    class Meta:
        model = DriverProfile
        fields = [
            "id",
            "user",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "license_number",
            "license_expiry_date",
            "license_expiring_soon",
            "license_expired",
            "vehicle_type",
            "vehicle_plate",
            "vehicle_capacity",
            "insurance_document",
            "background_check_status",
            "is_approved",
            "is_available",
            "average_rating",
            "ratings_count",
            "approved_at",
            "approved_by",
            "rejection_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_license_expiring_soon(self, obj):
        if not obj.license_expiry_date:
            return False
        days_until_expiry = (obj.license_expiry_date - timezone.localdate()).days
        return 0 <= days_until_expiry <= LICENSE_EXPIRY_WARNING_DAYS

    def get_license_expired(self, obj):
        if not obj.license_expiry_date:
            return False
        return obj.license_expiry_date < timezone.localdate()


class UserAdminSerializer(serializers.ModelSerializer):
    """Admin-facing account listing (patients & drivers). Read-only; the
    active/suspended state is changed through dedicated actions, not PATCH."""

    full_name = serializers.SerializerMethodField()
    # A trip belongs to a RiderProfile, not to a User, so phone booking needs the
    # profile id to book against. Null for anyone who isn't a rider.
    riderprofile_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "phone_number",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "riderprofile_id",
            "is_active",
            "is_verified",
            "date_joined",
        ]
        read_only_fields = fields

    def get_full_name(self, obj):
        return obj.get_full_name()

    def get_riderprofile_id(self, obj):
        profile = getattr(obj, "riderprofile", None)
        return profile.id if profile else None


class VehicleUpdateSerializer(serializers.Serializer):
    vehicle_type = serializers.ChoiceField(
        choices=VehicleType.choices, required=False, allow_blank=True
    )
    vehicle_plate = serializers.CharField(max_length=20, required=False, allow_blank=True)
    vehicle_capacity = serializers.IntegerField(min_value=1, required=False, allow_null=True)


class UserSerializer(serializers.ModelSerializer):
    riderprofile = RiderProfileSerializer(read_only=True)
    driverprofile = DriverProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "phone_number",
            "first_name",
            "last_name",
            "role",
            "is_verified",
            "date_joined",
            "riderprofile",
            "driverprofile",
        ]
        read_only_fields = ["id", "role", "is_verified", "date_joined"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    role = serializers.ChoiceField(choices=[Role.RIDER, Role.DRIVER])

    class Meta:
        model = User
        fields = [
            "email",
            "phone_number",
            "password",
            "first_name",
            "last_name",
            "role",
        ]

    def create(self, validated_data):
        role = validated_data.pop("role")
        password = validated_data.pop("password")
        user = User(role=role, **validated_data)
        user.set_password(password)
        user.save()

        if role == Role.RIDER:
            RiderProfile.objects.create(user=user)
        elif role == Role.DRIVER:
            DriverProfile.objects.create(user=user)

        return user


class EmailVerificationConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()

    def validate(self, attrs):
        try:
            uid = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            raise serializers.ValidationError("Invalid verification link.")

        if user.is_verified:
            # Already done. Say so plainly rather than failing -- a second click
            # on the same link is the commonest way to reach here.
            attrs["user"] = user
            attrs["already_verified"] = True
            return attrs

        if not email_verification_token.check_token(user, attrs["token"]):
            raise serializers.ValidationError(
                "This link has expired or has already been used. Sign in and ask for a new one."
            )

        attrs["user"] = user
        attrs["already_verified"] = False
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def get_user(self):
        try:
            return User.objects.get(email__iexact=self.validated_data["email"])
        except User.DoesNotExist:
            return None


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(validators=[validate_password])

    def validate(self, attrs):
        try:
            uid = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            raise serializers.ValidationError("Invalid reset link.")

        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError("Invalid or expired reset token.")

        attrs["user"] = user
        return attrs


def make_password_reset_link(user, frontend_url):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{frontend_url}/reset-password?uid={uid}&token={token}"


class DriverAvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverAvailability
        fields = ["id", "weekday", "start_time", "end_time"]

    def validate(self, attrs):
        if attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError(
                {"end_time": "A shift has to end after it starts."}
            )
        return attrs


class DriverTimeOffSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverTimeOff
        fields = ["id", "start_date", "end_date", "reason"]

    def validate(self, attrs):
        if attrs["end_date"] < attrs["start_date"]:
            raise serializers.ValidationError(
                {"end_date": "Time off has to end on or after it starts."}
            )
        return attrs


class DriverLocationSerializer(serializers.Serializer):
    """A position report from the driver's app."""

    lat = serializers.DecimalField(max_digits=9, decimal_places=6)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6)

    def validate_lat(self, value):
        if not -90 <= value <= 90:
            raise serializers.ValidationError("Latitude is out of range.")
        return value

    def validate_lng(self, value):
        if not -180 <= value <= 180:
            raise serializers.ValidationError("Longitude is out of range.")
        return value
