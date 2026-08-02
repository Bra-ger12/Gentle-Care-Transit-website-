from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import InvoiceViewSet, MedicaidExportView, RateScheduleViewSet

router = DefaultRouter()
router.register("rate-schedules", RateScheduleViewSet, basename="rate-schedule")
router.register("invoices", InvoiceViewSet, basename="invoice")

urlpatterns = router.urls + [
    path("medicaid-export/", MedicaidExportView.as_view(), name="medicaid-export"),
]
