from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

DEBUG = env("DEBUG")
# FIX #5: production must never boot with a known fallback SECRET_KEY.
SECRET_KEY = env("SECRET_KEY", default="")
if not SECRET_KEY:
    settings_module = env("DJANGO_SETTINGS_MODULE", default="")
    if settings_module.endswith(".prod"):
        raise ImproperlyConfigured("Set SECRET_KEY in the environment before running production.")
    SECRET_KEY = "django-insecure-dev-only-change-me"
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    "apps.accounts",
    "apps.audit",
    "apps.operations",
    "apps.trips",
    "apps.billing",
    "apps.payroll",
    "apps.fleet",
    "apps.reports",
    "apps.notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL"),
}

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.EmailOrPhoneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# North Dakota spans Central time, with the westernmost counties in Mountain time.
# All datetimes are stored in UTC (USE_TZ=True) and converted to this default display
# zone; per-user/service-area zone overrides can be layered on in a later phase.
TIME_ZONE = env("TIME_ZONE", default="America/Chicago")
USE_TZ = True
LANGUAGE_CODE = "en-us"
USE_I18N = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
# FIX #7: uploaded patient/driver files should not be world-readable on disk.
FILE_UPLOAD_PERMISSIONS = 0o640
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o750

# The plain HTML/JS frontend, served by this app at the site root while DEBUG is on
# so `runserver` alone serves the whole system on one origin (see config/urls.py).
# In production a real web server or CDN serves this directory instead.
FRONTEND_DIR = Path(env("FRONTEND_DIR", default=str(BASE_DIR.parent / "frontend")))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Gentle Care Transit API",
    "DESCRIPTION": "NEMT web system API (North Dakota)",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env.int("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=15)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_OBTAIN_SERIALIZER": "apps.accounts.serializers.IdentifierTokenObtainPairSerializer",
}

# Refresh token is delivered as an httpOnly cookie rather than in the JSON body
# (XSS-resistant token storage) -- the access token stays in the response body
# and is held only in memory on the frontend.
JWT_REFRESH_COOKIE_NAME = env("JWT_REFRESH_COOKIE_NAME", default="refresh_token")
JWT_REFRESH_COOKIE_SECURE = env.bool("JWT_REFRESH_COOKIE_SECURE", default=not DEBUG)
JWT_REFRESH_COOKIE_SAMESITE = env("JWT_REFRESH_COOKIE_SAMESITE", default="Lax")

FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:5173")
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[FRONTEND_URL])
CORS_ALLOW_CREDENTIALS = True

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@gentlecaretransit.org")

# --- Geocoding/routing ---
GOOGLE_MAPS_API_KEY = env("GOOGLE_MAPS_API_KEY", default="")
# With no key -- or when Google refuses (billing off, quota, outage) -- addresses
# resolve against the built-in North Dakota gazetteer and mileage is estimated by
# haversine, so the system stays fully usable. Trips priced that way are stored
# with distance_estimated=True. Set false to make an unavailable Maps API a hard
# booking error instead.
MAPS_OFFLINE_FALLBACK = env.bool("MAPS_OFFLINE_FALLBACK", default=True)

# --- Celery (Phase 2 recurring-trip generation; Phase 5 reminders/alerts) ---
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_TIMEZONE = TIME_ZONE
# Static beat schedule (no django-celery-beat DB scheduler needed). Only runs when a
# `celery beat` process is started (prod). In Redis-free dev the same sweeps are run
# on demand via `manage.py send_trip_reminders` / `check_document_expiry`.
CELERY_BEAT_SCHEDULE = {
    "send-trip-reminders": {
        "task": "apps.notifications.tasks.send_trip_reminders",
        "schedule": 15 * 60,  # every 15 minutes
    },
    "check-document-expiry": {
        "task": "apps.notifications.tasks.check_document_expiry",
        "schedule": 24 * 60 * 60,  # daily
    },
}

# --- Channels (Phase 5 realtime) ---
# Dev default is the in-memory layer: a single Daphne process serves both HTTP and
# WebSocket, so in-process group_send reaches consumers with no Redis dependency.
# Set CHANNELS_BACKEND=redis (prod, or multi-process dev) to use channels_redis.
CHANNELS_REDIS_URL = env("CHANNELS_REDIS_URL", default="redis://localhost:6379/1")
if env("CHANNELS_BACKEND", default="memory") == "redis":
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [CHANNELS_REDIS_URL]},
        }
    }
else:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# --- Needed starting Phase 5 (SMS) ---
TWILIO_ACCOUNT_SID = env("TWILIO_ACCOUNT_SID", default="")
TWILIO_AUTH_TOKEN = env("TWILIO_AUTH_TOKEN", default="")
TWILIO_FROM_NUMBER = env("TWILIO_FROM_NUMBER", default="")

# Browser-side Google Maps key served to the static frontend via /api/public-config/.
# Defaults to the server-side geocoding key; in prod use a separate referrer-restricted
# key so the browser key can't be reused for server-side quota.
GOOGLE_MAPS_BROWSER_KEY = env("GOOGLE_MAPS_BROWSER_KEY", default=GOOGLE_MAPS_API_KEY)

# FIX #5: production-ready logging baseline without putting secrets in code.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(levelname)s %(asctime)s %(name)s %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        }
    },
    "root": {
        "handlers": ["console"],
        "level": env("DJANGO_LOG_LEVEL", default="INFO"),
    },
    "loggers": {
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        }
    },
}
