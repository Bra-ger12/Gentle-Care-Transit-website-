from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.audit.mixins import AuditedRetrieveUpdateMixin, AuditedViewSetMixin
from apps.audit.models import AuditAction

from .emails import send_verification_email
from .models import (
    BackgroundCheckStatus,
    DriverAvailability,
    DriverLocation,
    DriverProfile,
    DriverTimeOff,
    RiderProfile,
    Role,
)
from .permissions import IsAdminRole, IsDriver, IsOwnerOrAdmin
from .serializers import (
    DriverAvailabilitySerializer,
    DriverLocationSerializer,
    DriverProfileAdminSerializer,
    DriverProfileSerializer,
    DriverTimeOffSerializer,
    EmailVerificationConfirmSerializer,
    IdentifierTokenObtainPairSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    RiderProfileSerializer,
    UserAdminSerializer,
    UserSerializer,
    VehicleUpdateSerializer,
    make_password_reset_link,
)

User = get_user_model()


def _set_refresh_cookie(response, refresh_token: str):
    response.set_cookie(
        key=settings.JWT_REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.JWT_REFRESH_COOKIE_SECURE,
        samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        path="/api/auth/",
    )


def _set_csrf_cookie(response, request):
    # FIX #6: explicitly issue the readable CSRF cookie that refresh must echo.
    token = get_token(request)
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=token,
        secure=settings.CSRF_COOKIE_SECURE,
        httponly=getattr(settings, "CSRF_COOKIE_HTTPONLY", False),
        samesite=settings.CSRF_COOKIE_SAMESITE,
        max_age=getattr(settings, "CSRF_COOKIE_AGE", None),
        path=getattr(settings, "CSRF_COOKIE_PATH", "/"),
    )
    return token


def _clear_refresh_cookie(response):
    response.delete_cookie(key=settings.JWT_REFRESH_COOKIE_NAME, path="/api/auth/")


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        user = serializer.save()
        send_verification_email(user)


class EmailVerifyConfirmView(APIView):
    """Confirms an address from the emailed link. Deliberately unauthenticated:
    the link is opened from a mail client, often on a different device."""

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = EmailVerificationConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        if serializer.validated_data["already_verified"]:
            return Response({"detail": "This email is already confirmed.", "verified": True})

        user.is_verified = True
        user.save(update_fields=["is_verified"])
        return Response({"detail": "Email confirmed. Thank you.", "verified": True})


class EmailVerifyResendView(APIView):
    """Sends a fresh verification link to the signed-in user's own address."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if request.user.is_verified:
            return Response({"detail": "Your email is already confirmed.", "verified": True})

        sent = send_verification_email(request.user)
        if not sent:
            return Response(
                {"detail": "We couldn't send that email just now. Please try again shortly."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": f"Verification link sent to {request.user.email}."})


class LoginView(TokenObtainPairView):
    serializer_class = IdentifierTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def post(self, request, *args, **kwargs):
        # FIX #6: login issues the CSRF cookie used by the refresh-cookie flow.
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        csrf_token = get_token(request)
        response = Response(
            {"access": data["access"], "csrf": csrf_token},
            status=status.HTTP_200_OK,
        )
        _set_refresh_cookie(response, data["refresh"])
        _set_csrf_cookie(response, request)
        return response


class CsrfTokenView(APIView):
    """Issue a CSRF token for the static frontend before cookie-backed refresh."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @method_decorator(ensure_csrf_cookie)
    def get(self, request, *args, **kwargs):
        # FIX #6: SPA can fetch a token before POSTing to the refresh endpoint.
        csrf_token = get_token(request)
        response = Response({"csrf": csrf_token})
        _set_csrf_cookie(response, request)
        return response


class RefreshView(APIView):
    permission_classes = [permissions.AllowAny]

    @method_decorator(csrf_protect)
    def post(self, request, *args, **kwargs):
        # FIX #6: refresh uses an httpOnly cookie, so require Django's CSRF check.
        raw_refresh = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if not raw_refresh:
            return Response(
                {"detail": "No refresh token cookie present."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            old_refresh = RefreshToken(raw_refresh)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc

        try:
            user = User.objects.get(pk=old_refresh["user_id"], is_active=True)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_401_UNAUTHORIZED)

        new_refresh = IdentifierTokenObtainPairSerializer.get_token(user)
        access = str(new_refresh.access_token)

        if settings.SIMPLE_JWT.get("BLACKLIST_AFTER_ROTATION"):
            try:
                old_refresh.blacklist()
            except AttributeError:
                pass

        csrf_token = get_token(request)
        response = Response({"access": access, "csrf": csrf_token}, status=status.HTTP_200_OK)
        _set_refresh_cookie(response, str(new_refresh))
        _set_csrf_cookie(response, request)
        return response


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        raw_refresh = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)
        if raw_refresh:
            try:
                RefreshToken(raw_refresh).blacklist()
            except TokenError:
                pass

        response = Response(status=status.HTTP_205_RESET_CONTENT)
        _clear_refresh_cookie(response)
        return response


class MeView(AuditedRetrieveUpdateMixin, generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    audit_model_name = "User"

    def get_object(self):
        obj = self.request.user
        self.check_object_permissions(self.request, obj)
        return obj


class RiderProfileView(AuditedRetrieveUpdateMixin, generics.RetrieveUpdateAPIView):
    serializer_class = RiderProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    audit_model_name = "RiderProfile"

    def get_object(self):
        if self.request.user.role != Role.RIDER:
            self.permission_denied(self.request)
        obj, _ = RiderProfile.objects.get_or_create(user=self.request.user)
        return obj


class DriverProfileView(AuditedRetrieveUpdateMixin, generics.RetrieveUpdateAPIView):
    serializer_class = DriverProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    audit_model_name = "DriverProfile"

    def get_object(self):
        if self.request.user.role != Role.DRIVER:
            self.permission_denied(self.request)
        obj, _ = DriverProfile.objects.get_or_create(user=self.request.user)
        return obj


class DriverProfileAdminViewSet(
    AuditedViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Admin-only driver approval queue. Read-only aside from `approve`/`reject`."""

    queryset = DriverProfile.objects.select_related("user", "approved_by").order_by("-created_at")
    serializer_class = DriverProfileAdminSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]
    audit_model_name = "DriverProfile"

    def get_queryset(self):
        queryset = super().get_queryset()
        is_approved_param = self.request.query_params.get("is_approved")
        if is_approved_param is not None:
            queryset = queryset.filter(is_approved=is_approved_param.lower() == "true")
        return queryset

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        driver = self.get_object()
        driver.is_approved = True
        driver.background_check_status = BackgroundCheckStatus.APPROVED
        driver.approved_at = timezone.now()
        driver.approved_by = request.user
        driver.rejection_reason = ""
        driver.save()
        self._log(AuditAction.UPDATE, driver, metadata={"action": "approve"})
        self._notify_driver_approved(driver)
        return Response(DriverProfileAdminSerializer(driver).data)

    @staticmethod
    def _notify_driver_approved(driver):
        # Best-effort: an approval must not fail because a notification did.
        try:
            from apps.notifications.models import NotificationCategory
            from apps.notifications.services import notify

            notify(
                driver.user,
                category=NotificationCategory.DRIVER_APPROVED,
                title="You're approved to drive",
                body="Your driver application has been approved. You can now be "
                "assigned trips. Welcome aboard!",
            )
        except Exception:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).exception("driver-approved notification failed")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        driver = self.get_object()
        driver.is_approved = False
        driver.background_check_status = BackgroundCheckStatus.REJECTED
        driver.approved_at = timezone.now()
        driver.approved_by = request.user
        driver.rejection_reason = request.data.get("reason", "")
        driver.save()
        self._log(AuditAction.UPDATE, driver, metadata={"action": "reject"})
        return Response(DriverProfileAdminSerializer(driver).data)

    @action(detail=False, methods=["get"], url_path="on-duty")
    def on_duty(self, request):
        """The crew dispatch can actually send right now, with where they are.

        The dispatch map is otherwise built from trips, so a driver who is on
        duty but between jobs -- exactly the person you want to give the next
        trip to -- was invisible on it. Position comes from the last report the
        driver's app made; `position_is_stale` marks a fix too old to steer by
        rather than quietly presenting it as current.
        """
        from django.db.models import Count, Q

        from apps.trips.models import Trip
        from apps.trips.services.assignment import ACTIVE_STATUSES, LOCATION_FRESHNESS

        now = timezone.now()
        drivers = (
            DriverProfile.objects.filter(is_approved=True, is_available=True)
            .select_related("user", "location")
            .annotate(
                active_trip_count=Count(
                    "assigned_trips",
                    filter=Q(assigned_trips__status__in=ACTIVE_STATUSES),
                    distinct=True,
                )
            )
            .order_by("active_trip_count", "user__last_name")
        )

        payload = []
        for driver in drivers:
            location = getattr(driver, "location", None)
            age = (now - location.reported_at).total_seconds() / 60 if location else None
            current = (
                Trip.objects.filter(assigned_driver=driver, status__in=ACTIVE_STATUSES)
                .order_by("scheduled_pickup_time")
                .first()
            )
            payload.append(
                {
                    "id": driver.id,
                    "name": driver.user.get_full_name(),
                    "vehicle_type": driver.vehicle_type,
                    "vehicle_plate": driver.vehicle_plate,
                    "active_trip_count": driver.active_trip_count,
                    "lat": location.lat if location else None,
                    "lng": location.lng if location else None,
                    "reported_at": location.reported_at if location else None,
                    "position_age_minutes": round(age) if age is not None else None,
                    "position_is_stale": (
                        age is not None and age > LOCATION_FRESHNESS.total_seconds() / 60
                    ),
                    "current_trip_id": str(current.id) if current else None,
                    "current_trip_status": current.status if current else None,
                    "current_trip_dropoff": current.dropoff_address if current else None,
                }
            )
        return Response(payload)

    @action(detail=True, methods=["patch"], url_path="vehicle")
    def update_vehicle(self, request, pk=None):
        """Admin fleet management: edit a driver's vehicle record."""
        driver = self.get_object()
        serializer = VehicleUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(driver, field, value)
        driver.save()
        self._log(
            AuditAction.UPDATE,
            driver,
            metadata={"action": "vehicle_update", **serializer.validated_data},
        )
        return Response(DriverProfileAdminSerializer(driver).data)


class AdminUserViewSet(
    AuditedViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Admin account management for patient & driver accounts. Suspending sets
    `is_active=False`, which blocks login and refresh (so the user is signed
    out). Admin accounts cannot be suspended, and admins cannot suspend
    themselves, to avoid locking the system out."""

    # select_related keeps the rider-profile lookup on the list serializer from
    # firing one query per row.
    queryset = User.objects.select_related("riderprofile").order_by("-date_joined")
    serializer_class = UserAdminSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminRole]
    audit_model_name = "User"

    def get_queryset(self):
        queryset = super().get_queryset()
        role = self.request.query_params.get("role")
        if role:
            queryset = queryset.filter(role=role.upper())
        search = self.request.query_params.get("q")
        if search:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        return queryset

    def _guard_target(self, target, request):
        if target == request.user:
            raise ValidationError("You cannot change your own account status.")
        if target.role == Role.ADMIN or target.is_staff:
            raise ValidationError("Admin accounts cannot be suspended here.")

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None):
        target = self.get_object()
        self._guard_target(target, request)
        target.is_active = False
        target.save(update_fields=["is_active"])
        self._log(AuditAction.UPDATE, target, metadata={"action": "suspend"})
        return Response(UserAdminSerializer(target).data)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        target = self.get_object()
        target.is_active = True
        target.save(update_fields=["is_active"])
        self._log(AuditAction.UPDATE, target, metadata={"action": "activate"})
        return Response(UserAdminSerializer(target).data)


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.get_user()

        if user is not None:
            link = make_password_reset_link(user, settings.FRONTEND_URL)
            send_mail(
                subject="Reset your Gentle Care Transit password",
                message=f"Use this link to reset your password: {link}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
            )

        # Always return 200 regardless of whether the email exists, to avoid
        # leaking account existence.
        return Response({"detail": "If that email exists, a reset link was sent."})


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Password has been reset."})


class _DriverOwnedViewSet(viewsets.ModelViewSet):
    """Base for the calendar collections a driver owns outright.

    Scoped to the signed-in driver's own rows in `get_queryset`, so there is no
    object-level check to forget: another driver's shift simply isn't in the
    queryset and 404s.
    """

    permission_classes = [permissions.IsAuthenticated, IsDriver]

    def _profile(self):
        profile, _ = DriverProfile.objects.get_or_create(user=self.request.user)
        return profile

    def get_queryset(self):
        return self.queryset.filter(driver=self._profile())

    def perform_create(self, serializer):
        serializer.save(driver=self._profile())


class DriverAvailabilityViewSet(_DriverOwnedViewSet):
    """The driver's recurring weekly shifts."""

    queryset = DriverAvailability.objects.all()
    serializer_class = DriverAvailabilitySerializer


class DriverTimeOffViewSet(_DriverOwnedViewSet):
    """Date ranges the driver is unavailable regardless of their usual shifts."""

    queryset = DriverTimeOff.objects.all()
    serializer_class = DriverTimeOffSerializer


class DriverLocationView(APIView):
    """Where the driver's app says they are.

    POSTed periodically while on duty. Stored as a single row per driver
    (overwritten, never appended) so dispatch can place everyone on the board
    without the system keeping a movement history of a person's day.
    """

    permission_classes = [permissions.IsAuthenticated, IsDriver]

    def post(self, request, *args, **kwargs):
        serializer = DriverLocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile, _ = DriverProfile.objects.get_or_create(user=request.user)

        DriverLocation.objects.update_or_create(
            driver=profile,
            defaults={
                "lat": serializer.validated_data["lat"],
                "lng": serializer.validated_data["lng"],
                "reported_at": timezone.now(),
            },
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
