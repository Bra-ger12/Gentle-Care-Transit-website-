from rest_framework.routers import DefaultRouter

from .views import RecurringTripSeriesViewSet, TripViewSet

router = DefaultRouter()
router.register("recurring-series", RecurringTripSeriesViewSet, basename="recurring-series")
router.register("", TripViewSet, basename="trip")

urlpatterns = router.urls
