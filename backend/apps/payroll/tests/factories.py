import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.payroll.models import DriverPayRate


class DriverPayRateFactory(DjangoModelFactory):
    class Meta:
        model = DriverPayRate

    driver = None  # the house default rate
    per_trip_base = "12.00"
    per_mile_rate = "1.35"
    effective_from = factory.LazyFunction(lambda: timezone.localdate().replace(day=1))
    effective_to = None
    is_active = True
