from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import mixins, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.models import RiderProfile, Role
from apps.accounts.permissions import IsAdminRole, IsRider
from apps.audit.mixins import AuditedViewSetMixin
from apps.audit.models import AuditAction
from apps.operations.models import SystemSetting

from . import notifications as trip_hooks
from .models import STATUS_TRANSITIONS, RecurringTripSeries, Trip, TripStatus, TripType
from .permissions import IsAssignedDriver, IsTripParticipant
from .serializers import (
    RecurringTripSeriesCreateSerializer,
    RecurringTripSeriesDetailSerializer,
    TripCompletionSerializer,
    TripCreateSerializer,
    TripDetailSerializer,
    TripListSerializer,
    TripRatingSerializer,
    TripRescheduleSerializer,
)
from .services.assignment import eligible_drivers, find_available_driver, rank_drivers
from .services.booking import create_return_leg
from .tasks import generate_recurring_trips


class TripViewSet(
    AuditedViewSetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Trip is never exposed via generic update/destroy -- status changes only
    happen through the named actions below, and trip records are never deleted."""

    queryset = Trip.objects.select_related(
        "rider__user", "recurring_series", "assigned_driver__user"
    )
    audit_model_name = "Trip"

    def get_serializer_class(self):
        if self.action == "create":
            return TripCreateSerializer
        if self.action == "list":
            return TripListSerializer
        return TripDetailSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == Role.ADMIN or user.is_staff:
            queryset = super().get_queryset()
        elif user.role == Role.RIDER:
            queryset = super().get_queryset().filter(rider__user=user)
        elif user.role == Role.DRIVER:
            queryset = super().get_queryset().filter(assigned_driver__user=user)
        else:
            queryset = super().get_queryset().none()

        status_param = self.request.query_params.get("status")
        if status_param:
            statuses = [s.strip() for s in status_param.split(",") if s.strip()]
            queryset = queryset.filter(status__in=statuses)

        # `?date=YYYY-MM-DD` narrows to one day of the schedule (the driver's daily
        # manifest, the dispatch board's "trips today" count). The day boundary is
        # the project TIME_ZONE, not UTC.
        date_param = self.request.query_params.get("date")
        if date_param:
            try:
                scheduled_date = parse_date(date_param)
            except ValueError:
                scheduled_date = None
            if scheduled_date is None:
                raise ValidationError({"date": "Expected a date as YYYY-MM-DD."})
            queryset = queryset.filter(scheduled_pickup_time__date=scheduled_date)
        return queryset

    def get_permissions(self):
        if self.action == "create":
            # Admins book on behalf of riders who phone dispatch.
            return [permissions.IsAuthenticated(), (IsRider | IsAdminRole)()]
        if self.action == "confirm":
            return [permissions.IsAuthenticated(), IsAdminRole()]
        if self.action in ("assign", "auto_assign", "reassign", "driver_suggestions"):
            return [permissions.IsAuthenticated(), IsAdminRole()]
        if self.action in ("accept", "decline"):
            return [permissions.IsAuthenticated(), IsAssignedDriver()]
        if self.action in ("en_route", "arrive", "picked_up", "complete", "no_show"):
            return [permissions.IsAuthenticated(), (IsAdminRole | IsAssignedDriver)()]
        if self.action in ("cancel", "reschedule", "request_return"):
            return [permissions.IsAuthenticated(), IsTripParticipant()]
        if self.action == "rate":
            return [permissions.IsAuthenticated(), IsRider(), IsTripParticipant()]
        return [permissions.IsAuthenticated(), (IsTripParticipant | IsAssignedDriver)()]

    def _require_verified_email(self):
        """A rider has to be reachable before we accept a booking.

        Trip confirmations, driver-assigned notices and appointment reminders all
        go to this address; an unconfirmed one means a rider standing outside
        with no idea whether anyone is coming.
        """
        user = self.request.user
        if user.is_verified or user.role != Role.RIDER:
            return
        if not SystemSetting.load().require_verified_email_to_book:
            return
        raise ValidationError(
            {
                "email": "Confirm your email address before booking. Check your "
                "inbox for the link, or request a new one from your account page."
            }
        )

    def _booking_rider(self, serializer):
        """Whose trip this is.

        A rider books for themselves. An admin taking a call books for whoever
        rang, which is how most NEMT trips are actually created -- riders are
        often elderly, and a phone call to dispatch is the whole booking channel.
        """
        rider_id = serializer.validated_data.pop("rider_id", None)
        is_admin = self.request.user.role == Role.ADMIN or self.request.user.is_staff

        if not is_admin:
            if rider_id is not None:
                raise ValidationError({"rider_id": "You can only book trips for yourself."})
            return self.request.user.riderprofile

        if rider_id is None:
            raise ValidationError({"rider_id": "Choose which rider this booking is for."})
        rider = RiderProfile.objects.filter(id=rider_id).first()
        if rider is None:
            raise ValidationError({"rider_id": "No rider with that id."})
        if not rider.user.is_active:
            raise ValidationError({"rider_id": "That rider's account is suspended."})
        return rider

    def perform_create(self, serializer):
        self._require_verified_email()
        rider = self._booking_rider(serializer)
        return_time = serializer.validated_data.pop("return_pickup_time", None)
        will_call = serializer.validated_data.pop("return_is_will_call", False)

        trip = serializer.save(rider=rider, created_by=self.request.user)
        self._log(AuditAction.CREATE, trip)
        trip_hooks.trip_created(trip)

        if trip.trip_type == TripType.ROUND_TRIP:
            leg = create_return_leg(trip, return_time=return_time, is_will_call=will_call)
            self._log(AuditAction.CREATE, leg, metadata={"leg": "return"})
            trip_hooks.trip_created(leg)

    def _apply_transition(self, trip, new_status, request, extra_fields=None):
        if new_status not in STATUS_TRANSITIONS.get(trip.status, set()):
            raise ValidationError(f"Cannot move a {trip.status} trip to {new_status}.")

        is_admin = request.user.role == Role.ADMIN or request.user.is_staff
        if new_status == TripStatus.CANCELLED and not is_admin:
            hours = SystemSetting.load().cancellation_cutoff_hours
            cutoff = trip.scheduled_pickup_time - timedelta(hours=hours)
            if timezone.now() > cutoff:
                raise ValidationError(
                    f"Trips can only be cancelled at least {hours} hours before pickup."
                )

        old_status = trip.status
        trip.status = new_status
        for field, value in (extra_fields or {}).items():
            setattr(trip, field, value)
        trip.save()

        self._log(AuditAction.UPDATE, trip, metadata={"from": old_status, "to": new_status})
        trip_hooks.status_changed(trip, request.user)
        return Response(TripDetailSerializer(trip).data)

    def _assign_driver(self, trip, driver, request):
        return self._apply_transition(
            trip,
            TripStatus.ASSIGNED,
            request,
            extra_fields={
                "assigned_driver": driver,
                "assigned_at": timezone.now(),
                "assigned_by": request.user,
                "accepted_at": None,
                "decline_reason": "",
            },
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._apply_transition(
            self.get_object(),
            TripStatus.CANCELLED,
            request,
            extra_fields={
                "cancelled_at": timezone.now(),
                "cancelled_by": request.user,
                "cancellation_reason": request.data.get("reason", ""),
            },
        )

    @action(detail=True, methods=["post"])
    def reschedule(self, request, pk=None):
        """Move a trip to a new time, subject to the same cutoff as cancelling.

        Only trips that haven't started can move. Anything already assigned goes
        back to CONFIRMED and releases its driver -- the person who accepted a
        09:00 pickup did not agree to a 15:00 one, and silently keeping them on
        it is how a rider ends up stranded.
        """
        trip = self.get_object()
        serializer = TripRescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_time = serializer.validated_data["scheduled_pickup_time"]

        movable = (TripStatus.REQUESTED, TripStatus.CONFIRMED, TripStatus.ASSIGNED)
        if trip.status not in movable:
            raise ValidationError(f"A {trip.get_status_display().lower()} trip can't be moved.")

        setting = SystemSetting.load()
        is_admin = request.user.role == Role.ADMIN or request.user.is_staff
        now = timezone.now()

        if not is_admin:
            cutoff = trip.scheduled_pickup_time - timedelta(hours=setting.cancellation_cutoff_hours)
            if now > cutoff:
                raise ValidationError(
                    f"Trips can only be rescheduled at least "
                    f"{setting.cancellation_cutoff_hours} hours before pickup."
                )

        earliest = now + timedelta(minutes=setting.booking_lead_time_minutes)
        if new_time <= earliest:
            raise ValidationError(
                {
                    "scheduled_pickup_time": "The new time needs at least "
                    f"{setting.booking_lead_time_minutes} minutes' notice."
                }
            )

        previous = trip.scheduled_pickup_time
        released = None
        if trip.status == TripStatus.ASSIGNED:
            released = trip.assigned_driver
            trip.status = TripStatus.CONFIRMED
            trip.assigned_driver = None
            trip.assigned_at = None
            trip.assigned_by = None
            trip.accepted_at = None

        trip.scheduled_pickup_time = new_time
        trip.save()

        self._log(
            AuditAction.UPDATE,
            trip,
            metadata={
                "action": "rescheduled",
                "from": previous.isoformat(),
                "to": new_time.isoformat(),
                "reason": serializer.validated_data.get("reason", ""),
            },
        )
        trip_hooks.trip_rescheduled(trip, previous, released)
        return Response(TripDetailSerializer(trip).data)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        return self._apply_transition(self.get_object(), TripStatus.CONFIRMED, request)

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        trip = self.get_object()
        driver_id = request.data.get("driver_id")
        if not driver_id:
            raise ValidationError("driver_id is required.")
        driver = eligible_drivers(trip).filter(id=driver_id).first()
        if driver is None:
            raise ValidationError(
                "No eligible driver with that id (unapproved, vehicle-incompatible, "
                "or already booked around that time)."
            )
        return self._assign_driver(trip, driver, request)

    @action(detail=True, methods=["get"], url_path="driver-suggestions")
    def driver_suggestions(self, request, pk=None):
        """Who dispatch should send, best first.

        Nearest on-duty driver wins. A driver whose position is stale or missing
        is ranked after those we can locate rather than treated as far away --
        an unknown position is not evidence of distance.
        """
        trip = self.get_object()
        return Response(
            [
                {
                    "driver_id": row["driver"].id,
                    "name": row["driver"].user.get_full_name(),
                    "vehicle_type": row["driver"].vehicle_type,
                    "vehicle_plate": row["driver"].vehicle_plate,
                    "is_available": row["is_available"],
                    "active_trip_count": row["active_trip_count"],
                    "miles_away": (
                        float(round(row["miles_away"], 1))
                        if row["miles_away"] is not None
                        else None
                    ),
                }
                for row in rank_drivers(trip)
            ]
        )

    @action(detail=True, methods=["post"], url_path="auto-assign")
    def auto_assign(self, request, pk=None):
        trip = self.get_object()
        driver = find_available_driver(trip)
        if driver is None:
            raise ValidationError("No available driver found.")
        return self._assign_driver(trip, driver, request)

    @action(detail=True, methods=["post"])
    def reassign(self, request, pk=None):
        trip = self.get_object()
        if trip.status != TripStatus.ASSIGNED or trip.accepted_at is not None:
            raise ValidationError("Trip is not awaiting acceptance.")

        driver_id = request.data.get("driver_id")
        if driver_id:
            driver = eligible_drivers(trip).filter(id=driver_id).first()
            if driver is None:
                raise ValidationError("No eligible driver with that id.")
        else:
            driver = find_available_driver(trip)
            if driver is None:
                raise ValidationError("No available driver found.")

        trip.assigned_driver = driver
        trip.assigned_at = timezone.now()
        trip.assigned_by = request.user
        trip.accepted_at = None
        trip.decline_reason = ""
        trip.save()
        self._log(
            AuditAction.UPDATE, trip, metadata={"action": "reassigned", "driver": str(driver.id)}
        )
        trip_hooks.trip_reassigned(trip)
        return Response(TripDetailSerializer(trip).data)

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        trip = self.get_object()
        if trip.status != TripStatus.ASSIGNED or trip.accepted_at is not None:
            raise ValidationError("Trip is not awaiting acceptance.")
        trip.accepted_at = timezone.now()
        trip.save(update_fields=["accepted_at"])
        self._log(AuditAction.UPDATE, trip, metadata={"action": "accepted"})
        trip_hooks.trip_accepted(trip)
        return Response(TripDetailSerializer(trip).data)

    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        trip = self.get_object()
        if trip.status != TripStatus.ASSIGNED or trip.accepted_at is not None:
            raise ValidationError("Trip is not awaiting acceptance.")
        trip.status = TripStatus.CONFIRMED
        trip.assigned_driver = None
        trip.assigned_at = None
        trip.assigned_by = None
        trip.decline_reason = request.data.get("reason", "")
        trip.save()
        self._log(AuditAction.UPDATE, trip, metadata={"action": "declined"})
        trip_hooks.trip_declined(trip)
        return Response(TripDetailSerializer(trip).data)

    @action(detail=True, methods=["post"], url_path="en-route")
    def en_route(self, request, pk=None):
        trip = self.get_object()
        is_admin = request.user.role == Role.ADMIN or request.user.is_staff
        if not is_admin and trip.accepted_at is None:
            raise ValidationError("Accept the trip before marking en route.")
        return self._apply_transition(
            trip, TripStatus.EN_ROUTE, request, extra_fields={"en_route_at": timezone.now()}
        )

    @action(detail=True, methods=["post"])
    def arrive(self, request, pk=None):
        """Driver is at the pickup point. Starts the no-show wait clock."""
        return self._apply_transition(
            self.get_object(),
            TripStatus.ARRIVED,
            request,
            extra_fields={"arrived_at": timezone.now()},
        )

    @action(detail=True, methods=["post"], url_path="picked-up")
    def picked_up(self, request, pk=None):
        return self._apply_transition(
            self.get_object(),
            TripStatus.PICKED_UP,
            request,
            extra_fields={"picked_up_at": timezone.now()},
        )

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        trip = self.get_object()
        completion = TripCompletionSerializer(data=request.data)
        completion.is_valid(raise_exception=True)
        extra_fields = {"completed_at": timezone.now(), **completion.validated_data}
        return self._apply_transition(
            trip, TripStatus.COMPLETED, request, extra_fields=extra_fields
        )

    @action(detail=True, methods=["post"], url_path="no-show")
    def no_show(self, request, pk=None):
        """A no-show may only be filed after waiting the configured minimum.

        The wait is the whole substance of the claim -- ND Medicaid will not
        reimburse one that wasn't served, and a rider shouldn't be marked absent
        because a driver knocked once and left. The clock runs from `arrived_at`,
        which is why NO_SHOW is only reachable from ARRIVED.
        """
        trip = self.get_object()
        required = SystemSetting.load().no_show_wait_minutes
        now = timezone.now()

        if trip.arrived_at is None:
            raise ValidationError("Mark yourself arrived before filing a no-show.")

        waited = (now - trip.arrived_at).total_seconds() / 60
        if waited < required:
            remaining = int(required - waited) + 1
            raise ValidationError(
                f"You must wait {required} minutes at the pickup point before "
                f"filing a no-show. About {remaining} minute(s) left."
            )

        reason = request.data.get("reason", "").strip()
        if not reason:
            raise ValidationError({"reason": "Say what happened — this goes on the claim."})

        return self._apply_transition(
            trip,
            TripStatus.NO_SHOW,
            request,
            extra_fields={
                "no_show_at": now,
                "no_show_reason": reason,
                "no_show_waited_minutes": int(waited),
            },
        )

    @action(detail=True, methods=["post"], url_path="request-return")
    def request_return(self, request, pk=None):
        """Rider is ready to be collected — turns a will-call leg into a real booking."""
        trip = self.get_object()
        if not trip.is_will_call:
            raise ValidationError("This trip isn't a will-call return.")
        if trip.will_call_requested_at is not None:
            raise ValidationError("You've already asked for this ride.")
        if trip.status not in (TripStatus.REQUESTED, TripStatus.CONFIRMED):
            raise ValidationError("This ride is already underway.")

        now = timezone.now()
        trip.will_call_requested_at = now
        # Dispatch needs a real target time to schedule against; the placeholder
        # the booking created is replaced with "as soon as someone is free".
        trip.scheduled_pickup_time = now + timedelta(
            minutes=SystemSetting.load().booking_lead_time_minutes or 30
        )
        trip.save(update_fields=["will_call_requested_at", "scheduled_pickup_time", "updated_at"])
        self._log(AuditAction.UPDATE, trip, metadata={"action": "will_call_requested"})
        trip_hooks.will_call_requested(trip)
        return Response(TripDetailSerializer(trip).data)

    @action(detail=True, methods=["post"])
    def rate(self, request, pk=None):
        """Rider rates the driver once, after the trip is completed."""
        trip = self.get_object()
        if trip.status != TripStatus.COMPLETED:
            raise ValidationError("You can only rate a completed trip.")
        if trip.rated_at is not None:
            raise ValidationError("This trip has already been rated.")

        serializer = TripRatingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trip.rating = serializer.validated_data["rating"]
        trip.review = serializer.validated_data.get("review", "")
        trip.rated_at = timezone.now()
        trip.save(update_fields=["rating", "review", "rated_at", "updated_at"])

        self._log(AuditAction.UPDATE, trip, metadata={"action": "rated", "rating": trip.rating})
        return Response(TripDetailSerializer(trip).data)


class RecurringTripSeriesViewSet(
    AuditedViewSetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    queryset = RecurringTripSeries.objects.select_related("rider__user")
    audit_model_name = "RecurringTripSeries"

    def get_serializer_class(self):
        if self.action == "create":
            return RecurringTripSeriesCreateSerializer
        return RecurringTripSeriesDetailSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == Role.ADMIN or user.is_staff:
            return super().get_queryset()
        if user.role == Role.RIDER:
            return super().get_queryset().filter(rider__user=user)
        return super().get_queryset().none()

    def get_permissions(self):
        if self.action == "create":
            # Admins book on behalf of riders who phone dispatch.
            return [permissions.IsAuthenticated(), (IsRider | IsAdminRole)()]
        return [permissions.IsAuthenticated(), IsTripParticipant()]

    def perform_create(self, serializer):
        series = serializer.save(rider=self.request.user.riderprofile)
        self._log(AuditAction.CREATE, series)
        generate_recurring_trips.delay(series_id=str(series.id))

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        series = self.get_object()
        series.is_active = False
        series.save(update_fields=["is_active"])
        self._log(AuditAction.UPDATE, series, metadata={"is_active": False})
        return Response(RecurringTripSeriesDetailSerializer(series).data)
