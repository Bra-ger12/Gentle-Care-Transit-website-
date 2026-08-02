from .base import *  # noqa: F401,F403

DEBUG = False

DATABASES["default"]["NAME"] = env("TEST_DATABASE_NAME", default="gentlecare_test")  # noqa: F405

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Run Celery tasks synchronously (no broker needed) so `.delay()` calls in tests
# execute in-process and raise real exceptions instead of silently queuing.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# No test may reach the network. With the key blank, the maps service goes
# straight to the offline gazetteer instead of spending a 5s timeout per call
# discovering that Google is unreachable from CI.
GOOGLE_MAPS_API_KEY = ""
GOOGLE_MAPS_BROWSER_KEY = ""
MAPS_OFFLINE_FALLBACK = True
