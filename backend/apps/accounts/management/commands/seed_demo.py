"""Populate a working demo dataset: `python manage.py seed_demo`.

Every account it creates lives on the `@demo.gentlecaretransit.org` domain, and
nothing outside that domain is ever touched. That is what makes `--flush` safe
to run against a database that also holds real accounts, and what makes the
command re-runnable: flush, then rebuild.

Mileage is resolved through the normal booking service, so with no Google key
the trips carry honest haversine estimates flagged `distance_estimated=True`
rather than invented numbers.
"""

import random
from datetime import date, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import (
    BackgroundCheckStatus,
    DriverProfile,
    MobilityNeed,
    RiderProfile,
    Role,
    User,
    VehicleType,
)
from apps.billing.models import Invoice, RateSchedule
from apps.billing.services.pricing import generate_invoice_for_trip
from apps.fleet.models import DefectItem, InspectionType, VehicleInspection
from apps.payroll.models import DriverPayRate, TripEarning
from apps.payroll.services.earnings import generate_earning_for_trip
from apps.trips.models import RecurringTripSeries, Trip, TripStatus, TripType
from apps.trips.services.maps import resolve_route

DEMO_DOMAIN = "demo.gentlecaretransit.org"
DEMO_PASSWORD = "GentleCare!2026"

ADMIN = ("dispatch", "Renee", "Halvorsen")

RIDERS = [
    ("m.thorson", "Margaret", "Thorson", "Bismarck", [MobilityNeed.WHEELCHAIR], "ND441002881"),
    ("h.iverson", "Harold", "Iverson", "Mandan", [MobilityNeed.WALKER], "ND441007345"),
    ("d.littlebear", "Dolores", "Littlebear", "Bismarck", [MobilityNeed.AMBULATORY], "ND441009120"),
    ("f.schmitt", "Frank", "Schmitt", "Lincoln", [MobilityNeed.OXYGEN], None),
    ("e.rodriguez", "Elena", "Rodriguez", "Bismarck", [MobilityNeed.STRETCHER], "ND441003467"),
]

DRIVERS = [
    ("t.nguyen", "Tom", "Nguyen", VehicleType.WHEELCHAIR_VAN, "ND 4821-K", 6),
    ("s.okafor", "Sadie", "Okafor", VehicleType.STRETCHER_VAN, "ND 7734-B", 4),
    ("j.beaulieu", "Jesse", "Beaulieu", VehicleType.SEDAN, "ND 2296-R", 4),
]

# Real Bismarck-area origins and medical destinations, so the map and the
# mileage estimates land where an operator would expect them to.
HOMES = {
    "Bismarck": [
        "1420 Boulevard Ave, Bismarck, ND",
        "722 N 26th St, Bismarck, ND",
        "3115 Rosser Ave, Bismarck, ND",
        "509 E Broadway Ave, Bismarck, ND",
    ],
    "Mandan": ["405 3rd Ave NW, Mandan, ND", "1900 Sunset Dr, Mandan, ND"],
    "Lincoln": ["215 Ash St, Lincoln, ND"],
}

CLINICS = [
    "Sanford Health, 300 N 7th St, Bismarck, ND",
    "CHI St Alexius Health, 900 E Broadway Ave, Bismarck, ND",
    "Bismarck Cancer Center, 500 N 8th St, Bismarck, ND",
    "Mid Dakota Clinic, 401 N 9th St, Bismarck, ND",
    "Dialysis Center, 1000 E Rosser Ave, Bismarck, ND",
]

NOTES = [
    "Rider uses a folding wheelchair; needs help at the front step.",
    "Dialysis — please be prompt, appointment cannot be moved.",
    "Daughter will meet the van at the clinic entrance.",
    "Oxygen concentrator travels with the rider.",
    "",
    "Building has a rear accessible entrance off the alley.",
]

REVIEWS = [
    "Tom was early and very patient. Thank you.",
    "Smooth ride, driver helped with the door.",
    "On time and friendly.",
    "",
]


class Command(BaseCommand):
    help = "Create a demo dataset: 1 admin, 5 riders, 3 drivers, 20 trips, invoices and earnings."

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete previously seeded demo data before rebuilding.",
        )
        parser.add_argument(
            "--seed", type=int, default=20260726, help="RNG seed, for reproducible data."
        )

    def handle(self, *args, **options):
        self.random = random.Random(options["seed"])

        if options["flush"]:
            self._flush()

        if User.objects.filter(email__endswith=f"@{DEMO_DOMAIN}").exists():
            self.stdout.write(
                self.style.WARNING("Demo data already present. Re-run with --flush to rebuild it.")
            )
            return

        with transaction.atomic():
            admin = self._create_admin()
            riders = self._create_riders()
            drivers = self._create_drivers()
            self._create_rates()
            trips = self._create_trips(riders, drivers, admin)
            self._create_series(riders[0])
            self._create_inspections(drivers)
            invoices, earnings = self._create_financials(trips, admin)

        self.stdout.write(self.style.SUCCESS("\nDemo data created.\n"))
        self.stdout.write(
            f"  1 admin, {len(riders)} riders, {len(drivers)} drivers, "
            f"{len(trips)} trips, {invoices} invoices, {earnings} driver earnings\n"
        )
        self.stdout.write(
            "  Sign in with any of these — password " + self.style.NOTICE(DEMO_PASSWORD)
        )
        self.stdout.write(f"    admin   {ADMIN[0]}@{DEMO_DOMAIN}")
        self.stdout.write(f"    rider   {RIDERS[0][0]}@{DEMO_DOMAIN}")
        self.stdout.write(f"    driver  {DRIVERS[0][0]}@{DEMO_DOMAIN}\n")

    # --- teardown -------------------------------------------------------

    def _flush(self):
        """Delete demo rows child-first: Trip.rider, Invoice.trip, TripEarning.trip
        and VehicleInspection.driver are all PROTECT, so order matters."""
        users = User.objects.filter(email__endswith=f"@{DEMO_DOMAIN}")
        trips = Trip.objects.filter(rider__user__in=users)

        counts = {
            "earnings": TripEarning.objects.filter(trip__in=trips).delete()[0],
            "invoices": Invoice.objects.filter(trip__in=trips).delete()[0],
            "inspections": VehicleInspection.objects.filter(driver__user__in=users).delete()[0],
            "trips": trips.delete()[0],
            "series": RecurringTripSeries.objects.filter(rider__user__in=users).delete()[0],
            "pay rates": DriverPayRate.objects.filter(driver__user__in=users).delete()[0],
            "users": users.delete()[0],
        }
        self.stdout.write(
            "Flushed demo data: " + ", ".join(f"{value} {label}" for label, value in counts.items())
        )

    # --- accounts -------------------------------------------------------

    def _user(self, handle, first, last, role, phone):
        user = User.objects.create_user(
            email=f"{handle}@{DEMO_DOMAIN}",
            password=DEMO_PASSWORD,
            first_name=first,
            last_name=last,
            role=role,
            phone_number=phone,
            is_verified=True,
        )
        return user

    def _create_admin(self):
        handle, first, last = ADMIN
        user = self._user(handle, first, last, Role.ADMIN, "+17015550100")
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        return user

    def _create_riders(self):
        riders = []
        for index, (handle, first, last, city, needs, medicaid) in enumerate(RIDERS):
            user = self._user(handle, first, last, Role.RIDER, f"+1701555{2100 + index}")
            riders.append(
                RiderProfile.objects.create(
                    user=user,
                    date_of_birth=date(1940 + index * 5, 3 + index, 12),
                    address_line1=self.random.choice(HOMES[city]),
                    city=city,
                    state="ND",
                    zip_code="58501",
                    emergency_contact_name=f"{first[0]}. {last} (family)",
                    emergency_contact_phone=f"+1701555{3100 + index}",
                    mobility_needs=list(needs),
                    medicaid_id=medicaid,
                )
            )
        return riders

    def _create_drivers(self):
        today = timezone.localdate()
        admin_now = timezone.now()
        drivers = []
        for index, (handle, first, last, vehicle, plate, capacity) in enumerate(DRIVERS):
            user = self._user(handle, first, last, Role.DRIVER, f"+1701555{4100 + index}")
            drivers.append(
                DriverProfile.objects.create(
                    user=user,
                    license_number=f"ND-CDL-{620045 + index * 137}",
                    # One licence deliberately expires soon, so the document-expiry
                    # alert has something real to fire on.
                    license_expiry_date=today + timedelta(days=[21, 400, 620][index]),
                    vehicle_type=vehicle,
                    vehicle_plate=plate,
                    vehicle_capacity=capacity,
                    background_check_status=BackgroundCheckStatus.APPROVED,
                    is_approved=True,
                    approved_at=admin_now,
                    is_available=index < 2,
                )
            )
        return drivers

    def _create_rates(self):
        start = timezone.localdate() - timedelta(days=365)
        # One schedule priced for every tier: surcharges on top of the base fare,
        # rather than a separate rate card per mobility need. Both mechanisms
        # work; this one puts the breakdown on the invoice where an auditor
        # can see it.
        RateSchedule.objects.get_or_create(
            mobility_need="",
            effective_from=start,
            defaults={
                "base_fare": Decimal("18.00"),
                "per_mile_rate": Decimal("2.35"),
                "wheelchair_surcharge": Decimal("10.00"),
                "stretcher_surcharge": Decimal("37.00"),
                "free_wait_minutes": 15,
                "wait_time_rate_per_minute": Decimal("0.75"),
                "is_active": True,
            },
        )
        DriverPayRate.objects.get_or_create(
            driver=None,
            effective_from=start,
            defaults={
                "per_trip_base": Decimal("12.00"),
                "per_mile_rate": Decimal("0.72"),
                "is_active": True,
            },
        )

    # --- trips ----------------------------------------------------------

    def _addresses(self, rider):
        return rider.address_line1, self.random.choice(CLINICS)

    def _create_trips(self, riders, drivers, admin):
        """20 trips: a settled past, a live today, and a booked future.

        The shape matters more than the count -- every screen in the system has
        to have something to render, including the empty-ish states like a
        declined trip sitting back in the dispatch queue.
        """
        now = timezone.now()
        today = timezone.localdate()
        plan = [
            # (days_offset, hour, status, driver_index)
            (-21, 9, TripStatus.COMPLETED, 0),
            (-18, 13, TripStatus.COMPLETED, 1),
            (-16, 8, TripStatus.COMPLETED, 0),
            (-14, 10, TripStatus.COMPLETED, 2),
            (-11, 14, TripStatus.NO_SHOW, 1),
            (-9, 9, TripStatus.COMPLETED, 0),
            (-7, 11, TripStatus.COMPLETED, 1),
            (-6, 15, TripStatus.CANCELLED, None),
            (-4, 8, TripStatus.COMPLETED, 2),
            (-2, 13, TripStatus.COMPLETED, 0),
            (-1, 10, TripStatus.COMPLETED, 1),
            (0, 8, TripStatus.COMPLETED, 0),
            (0, 10, TripStatus.PICKED_UP, 0),
            (0, 11, TripStatus.ARRIVED, 1),
            (0, 12, TripStatus.EN_ROUTE, 1),
            (0, 14, TripStatus.ASSIGNED, 0),
            (0, 15, TripStatus.ASSIGNED, 2),
            (0, 16, TripStatus.CONFIRMED, None),
            (1, 9, TripStatus.REQUESTED, None),
            (2, 13, TripStatus.CONFIRMED, None),
            (4, 9, TripStatus.REQUESTED, None),
        ]

        trips = []
        for index, (offset, hour, status, driver_index) in enumerate(plan):
            rider = riders[index % len(riders)]
            pickup, dropoff = self._addresses(rider)
            route = resolve_route(pickup, dropoff)
            scheduled = timezone.make_aware(
                timezone.datetime.combine(today + timedelta(days=offset), time(hour, 0))
            )
            need = rider.mobility_needs[0] if rider.mobility_needs else ""

            trip = Trip(
                rider=rider,
                created_by=rider.user,
                status=status,
                scheduled_pickup_time=scheduled,
                pickup_address=pickup,
                pickup_lat=route.pickup_lat,
                pickup_lng=route.pickup_lng,
                dropoff_address=dropoff,
                dropoff_lat=route.dropoff_lat,
                dropoff_lng=route.dropoff_lng,
                mileage=route.miles,
                distance_estimated=route.estimated,
                estimated_duration_minutes=route.duration_minutes,
                mobility_need=need,
                escort_count=self.random.choice([0, 0, 0, 1, 1, 2]),
                notes=self.random.choice(NOTES),
            )
            self._apply_history(trip, status, drivers, driver_index, scheduled, admin, now)
            trip.save()
            trips.append(trip)

        trips.extend(self._create_round_trip(riders[2], drivers[0], admin))
        return trips

    def _create_round_trip(self, rider, driver, admin):
        """One booked round trip: an outbound leg and a will-call return.

        Every other trip in the demo is one-way, so without this the round-trip
        and will-call screens would render nothing.
        """
        from apps.trips.services.booking import create_return_leg

        pickup, dropoff = self._addresses(rider)
        route = resolve_route(pickup, dropoff)
        scheduled = timezone.make_aware(
            timezone.datetime.combine(timezone.localdate() + timedelta(days=3), time(10, 30))
        )
        outbound = Trip.objects.create(
            rider=rider,
            created_by=rider.user,
            status=TripStatus.CONFIRMED,
            trip_type=TripType.ROUND_TRIP,
            scheduled_pickup_time=scheduled,
            pickup_address=pickup,
            pickup_lat=route.pickup_lat,
            pickup_lng=route.pickup_lng,
            dropoff_address=dropoff,
            dropoff_lat=route.dropoff_lat,
            dropoff_lng=route.dropoff_lng,
            mileage=route.miles,
            distance_estimated=route.estimated,
            estimated_duration_minutes=route.duration_minutes,
            mobility_need=rider.mobility_needs[0] if rider.mobility_needs else "",
            escort_count=1,
            notes="Round trip — daughter travelling with her.",
        )
        return [outbound, create_return_leg(outbound, is_will_call=True)]

    def _apply_history(self, trip, status, drivers, driver_index, scheduled, admin, now):
        """Backfill the timestamps a trip in this state would really carry."""
        if driver_index is not None:
            driver = drivers[driver_index]
            trip.assigned_driver = driver
            trip.assigned_at = scheduled - timedelta(hours=20)
            trip.assigned_by = admin

        if status in (TripStatus.ASSIGNED,):
            # One of the two assigned trips is still awaiting acceptance, which is
            # the state the dispatcher's reassign control exists for.
            trip.accepted_at = None if trip.mileage % 2 == 0 else scheduled - timedelta(hours=18)
        elif driver_index is not None:
            trip.accepted_at = scheduled - timedelta(hours=18)

        underway = (
            TripStatus.EN_ROUTE,
            TripStatus.ARRIVED,
            TripStatus.PICKED_UP,
            TripStatus.COMPLETED,
        )
        if status in underway:
            trip.en_route_at = scheduled - timedelta(minutes=18)
        if status in underway[1:]:
            trip.arrived_at = scheduled - timedelta(minutes=self.random.randint(1, 6))
        if status in (TripStatus.PICKED_UP, TripStatus.COMPLETED):
            # Most boardings are prompt; occasionally a rider takes a while to
            # get to the door, which is what the billable-wait rule is for.
            delay = self.random.choice([0, 1, 2, 3, 4, 6, 28])
            trip.picked_up_at = trip.arrived_at + timedelta(minutes=delay)

        if status == TripStatus.COMPLETED:
            duration = trip.estimated_duration_minutes or 20
            trip.completed_at = trip.picked_up_at + timedelta(
                minutes=duration + self.random.randint(0, 8)
            )
            odometer_start = self.random.randrange(41000, 88000)
            trip.odometer_start = odometer_start
            trip.odometer_end = odometer_start + int(trip.mileage)
            trip.completion_attestation = trip.assigned_driver.user.get_full_name()
            # Most completed trips get rated; some never do, which is realistic
            # and gives the "not yet rated" state something to render.
            if self.random.random() < 0.7:
                trip.rating = self.random.choice([5, 5, 5, 4, 4, 3])
                trip.review = self.random.choice(REVIEWS)
                trip.rated_at = trip.completed_at + timedelta(hours=self.random.randint(1, 30))

        if status == TripStatus.NO_SHOW:
            trip.en_route_at = scheduled - timedelta(minutes=15)
            trip.arrived_at = scheduled - timedelta(minutes=2)
            trip.no_show_at = scheduled + timedelta(minutes=12)
            trip.no_show_waited_minutes = 14
            trip.no_show_reason = "Waited at the door, no answer by phone."

        if status == TripStatus.CANCELLED:
            trip.cancelled_at = scheduled - timedelta(days=2)
            trip.cancelled_by = trip.rider.user
            trip.cancellation_reason = "Appointment rescheduled by the clinic."

        if status == TripStatus.CONFIRMED and now < scheduled:
            trip.decline_reason = ""

    def _create_series(self, rider):
        pickup = rider.address_line1
        dropoff = "Dialysis Center, 1000 E Rosser Ave, Bismarck, ND"
        route = resolve_route(pickup, dropoff)
        today = timezone.localdate()
        RecurringTripSeries.objects.create(
            rider=rider,
            pickup_address=pickup,
            pickup_lat=route.pickup_lat,
            pickup_lng=route.pickup_lng,
            dropoff_address=dropoff,
            dropoff_lat=route.dropoff_lat,
            dropoff_lng=route.dropoff_lng,
            mileage=route.miles,
            distance_estimated=route.estimated,
            pickup_time=time(7, 30),
            weekdays=[0, 2, 4],
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=90),
            mobility_need=rider.mobility_needs[0] if rider.mobility_needs else "",
            notes="Standing dialysis schedule — Mon/Wed/Fri.",
        )

    def _create_inspections(self, drivers):
        today = timezone.localdate()
        now = timezone.now()
        for index, driver in enumerate(drivers):
            VehicleInspection.objects.create(
                driver=driver,
                inspection_type=InspectionType.PRE_TRIP,
                performed_at=now - timedelta(hours=6 + index),
                inspected_on=today,
                vehicle_plate_snapshot=driver.vehicle_plate,
                vehicle_type_snapshot=driver.vehicle_type,
                odometer=self.random.randrange(41000, 88000),
                defects=[DefectItem.WIPERS] if index == 1 else [],
                defect_notes="Passenger-side wiper streaking." if index == 1 else "",
                safe_to_operate=True,
                signature=driver.user.get_full_name(),
            )

    def _create_financials(self, trips, admin):
        invoices = earnings = 0
        for trip in trips:
            if trip.status != TripStatus.COMPLETED:
                continue
            invoice = generate_invoice_for_trip(trip, actor=admin)
            invoices += 1
            # Age the books: older trips are settled, recent ones still open.
            age_days = (timezone.localdate() - timezone.localtime(trip.completed_at).date()).days
            if age_days > 10:
                invoice.status = "PAID"
                invoice.finalized_at = trip.completed_at + timedelta(days=1)
                invoice.finalized_by = admin
                invoice.paid_at = trip.completed_at + timedelta(days=6)
                invoice.paid_by = admin
                invoice.payment_reference = f"ND-MMIS-{self.random.randrange(100000, 999999)}"
                invoice.save()
            elif age_days > 3:
                invoice.status = "FINALIZED"
                invoice.finalized_at = trip.completed_at + timedelta(days=1)
                invoice.finalized_by = admin
                invoice.save()

            if generate_earning_for_trip(trip, actor=admin) is not None:
                earnings += 1
        return invoices, earnings
