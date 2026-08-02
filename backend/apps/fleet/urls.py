from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ChecklistView, VehicleInspectionViewSet

router = DefaultRouter()
router.register("inspections", VehicleInspectionViewSet, basename="inspection")

urlpatterns = router.urls + [
    path("inspection-checklist/", ChecklistView.as_view(), name="inspection-checklist"),
]
