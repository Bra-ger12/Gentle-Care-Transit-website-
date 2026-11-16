from datetime import timedelta

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import RiderProfileFactory
from apps.trips.models import RecurringTripSeries, Service, Trip, TripStatus, Weekday


class ServiceFactory(DjangoModelFactory):
    class Meta:
        model = Service

    name = factory.Sequence(lambda n: f"Standard car {n}")
    cost_per_km = "2.50"
    base_fee = "5.00"
    minimum_fare = "10.00"
    is_active = True


class RecurringTripSeriesFactory(DjangoModelFactory):
    class Meta:
        model = RecurringTripSeries

    rider = factory.SubFactory(RiderProfileFactory)
    pickup_address = "123 Main St, Fargo, ND"
    pickup_lat = "46.877186"
    pickup_lng = "-96.789803"
    dropoff_address = "456 Broadway, Fargo, ND"
    dropoff_lat = "46.880000"
    dropoff_lng = "-96.790000"
    mileage = "3.20"
    service = factory.SubFactory(ServiceFactory)
    service_name_snapshot = factory.SelfAttribute("service.name")
    distance_km = "5.15"
    cost_per_km_used = factory.SelfAttribute("service.cost_per_km")
    base_fee_used = factory.SelfAttribute("service.base_fee")
    minimum_fare_used = factory.SelfAttribute("service.minimum_fare")
    total_cost = "17.88"
    pickup_time = "09:00:00"
    weekdays = [Weekday.MONDAY, Weekday.WEDNESDAY, Weekday.FRIDAY]
    start_date = factory.LazyFunction(timezone.localdate)
    end_date = None


class TripFactory(DjangoModelFactory):
    class Meta:
        model = Trip

    rider = factory.SubFactory(RiderProfileFactory)
    status = TripStatus.REQUESTED
    scheduled_pickup_time = factory.LazyFunction(lambda: timezone.now() + timedelta(days=3))
    pickup_address = "123 Main St, Fargo, ND"
    pickup_lat = "46.877186"
    pickup_lng = "-96.789803"
    dropoff_address = "456 Broadway, Fargo, ND"
    dropoff_lat = "46.880000"
    dropoff_lng = "-96.790000"
    mileage = "3.20"
    service = factory.SubFactory(ServiceFactory)
    service_name_snapshot = factory.SelfAttribute("service.name")
    distance_km = "5.15"
    cost_per_km_used = factory.SelfAttribute("service.cost_per_km")
    base_fee_used = factory.SelfAttribute("service.base_fee")
    minimum_fare_used = factory.SelfAttribute("service.minimum_fare")
    total_cost = "17.88"
