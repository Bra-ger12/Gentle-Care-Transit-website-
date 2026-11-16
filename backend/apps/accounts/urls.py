from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("drivers", views.DriverProfileAdminViewSet, basename="admin-driver")
router.register("users", views.AdminUserViewSet, basename="admin-user")
router.register("availability", views.DriverAvailabilityViewSet, basename="availability")
router.register("time-off", views.DriverTimeOffViewSet, basename="time-off")

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="auth-register"),
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("csrf/", views.CsrfTokenView.as_view(), name="auth-csrf"),
    path("refresh/", views.RefreshView.as_view(), name="auth-refresh"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("me/", views.MeView.as_view(), name="auth-me"),
    path(
        "me/rider-profile/",
        views.RiderProfileView.as_view(),
        name="auth-rider-profile",
    ),
    path(
        "me/driver-profile/",
        views.DriverProfileView.as_view(),
        name="auth-driver-profile",
    ),
    path("me/location/", views.DriverLocationView.as_view(), name="driver-location"),
    path(
        "verify-email/confirm/",
        views.EmailVerifyConfirmView.as_view(),
        name="auth-verify-email-confirm",
    ),
    path(
        "verify-email/resend/",
        views.EmailVerifyResendView.as_view(),
        name="auth-verify-email-resend",
    ),
    path(
        "password-reset/request/",
        views.PasswordResetRequestView.as_view(),
        name="auth-password-reset-request",
    ),
    path(
        "password-reset/confirm/",
        views.PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
] + router.urls
