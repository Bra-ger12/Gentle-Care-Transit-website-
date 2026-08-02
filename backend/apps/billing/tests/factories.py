import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.billing.models import Invoice, InvoiceStatus, RateSchedule
from apps.trips.tests.factories import TripFactory


class RateScheduleFactory(DjangoModelFactory):
    class Meta:
        model = RateSchedule

    mobility_need = ""
    base_fare = "5.00"
    per_mile_rate = "2.00"
    effective_from = factory.LazyFunction(lambda: timezone.localdate().replace(day=1))
    effective_to = None
    is_active = True


class InvoiceFactory(DjangoModelFactory):
    class Meta:
        model = Invoice

    trip = factory.SubFactory(TripFactory)
    rider = factory.SelfAttribute("trip.rider")
    rate_schedule = factory.SubFactory(RateScheduleFactory)
    invoice_number = factory.Sequence(lambda n: f"INV-TEST-{n:06d}")
    status = InvoiceStatus.DRAFT
    rider_name_snapshot = factory.LazyAttribute(lambda o: o.rider.user.get_full_name())
    medicaid_id_snapshot = None
    mobility_need_snapshot = ""
    mileage_snapshot = "3.20"
    base_fare = "5.00"
    per_mile_rate = "2.00"
    mileage_amount = "6.40"
    total_amount = "11.40"
