from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import DriverPayRateViewSet, MyEarningsSummaryView, TripEarningViewSet

router = DefaultRouter()
router.register("pay-rates", DriverPayRateViewSet, basename="pay-rate")
router.register("earnings", TripEarningViewSet, basename="earning")

urlpatterns = router.urls + [
    path("earnings-summary/", MyEarningsSummaryView.as_view(), name="earnings-summary"),
]
