from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    PlaceOptionsView,
    ServiceAreaSummaryView,
    ServiceAreaViewSet,
    SystemSettingView,
)

router = DefaultRouter()
router.register("service-areas", ServiceAreaViewSet, basename="service-area")

urlpatterns = router.urls + [
    path("settings/", SystemSettingView.as_view(), name="system-settings"),
    path("service-area-summary/", ServiceAreaSummaryView.as_view(), name="service-area-summary"),
    path("places/", PlaceOptionsView.as_view(), name="place-options"),
]
