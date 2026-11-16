from rest_framework.routers import DefaultRouter

from .views import RecurringTripSeriesViewSet, ServiceViewSet, TripViewSet

router = DefaultRouter()
router.register("services", ServiceViewSet, basename="service")
router.register("recurring-series", RecurringTripSeriesViewSet, basename="recurring-series")
router.register("", TripViewSet, basename="trip")

urlpatterns = router.urls
