from django.urls import path

from .views import (
    DriverPerformanceView,
    DriverReportView,
    KpiSummaryView,
    ReportExportView,
    RevenueByMonthView,
)

urlpatterns = [
    path("kpis/summary/", KpiSummaryView.as_view(), name="kpi-summary"),
    path("kpis/revenue-by-month/", RevenueByMonthView.as_view(), name="kpi-revenue-by-month"),
    path("driver-performance/", DriverPerformanceView.as_view(), name="driver-performance"),
    path("export/", ReportExportView.as_view(), name="report-export"),
    path("driver/summary/", DriverReportView.as_view(), name="driver-report"),
]
