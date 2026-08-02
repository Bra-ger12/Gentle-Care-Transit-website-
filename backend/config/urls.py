from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

from .views import PublicConfigView, frontend_file

urlpatterns = [
    # Django's own admin lives under /django-admin/ so it can't shadow the operator
    # portal the frontend serves at /admin/*.html (both share one origin in dev).
    path("django-admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/trips/", include("apps.trips.urls")),
    path("api/billing/", include("apps.billing.urls")),
    path("api/payroll/", include("apps.payroll.urls")),
    path("api/fleet/", include("apps.fleet.urls")),
    path("api/reports/", include("apps.reports.urls")),
    path("api/audit/", include("apps.audit.urls")),
    path("api/operations/", include("apps.operations.urls")),
    path("api/notifications/", include("apps.notifications.urls")),
    path("api/public-config/", PublicConfigView.as_view(), name="public-config"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # Serve the plain HTML/JS frontend from this app so `runserver` alone puts the
    # whole system on http://localhost:8000/ — one origin, so no CORS preflights and
    # no cross-port refresh cookie in dev. Registered last: every /api/,
    # /django-admin/ and /media/ route above still wins. Production serves
    # `frontend/` separately.
    urlpatterns += [re_path(r"^(?P<path>.*)$", frontend_file, name="frontend")]
