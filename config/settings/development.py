"""
Development settings for MEIL ESG CONTROL TOWER.
"""

from .base import *  # noqa: F403

DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = ["*"]

# Allow insecure cookies for local HTTP development
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

# Console email backend for development inspection
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Verbose logging in development
LOGGING["handlers"]["console"]["level"] = "DEBUG"  # noqa: F405
LOGGING["loggers"]["apps.core"]["level"] = "DEBUG"  # noqa: F405
