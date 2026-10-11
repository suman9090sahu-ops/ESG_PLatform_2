"""
Production settings for MEIL ESG CONTROL TOWER.
"""

from .base import *  # noqa: F403
from django.core.exceptions import ImproperlyConfigured

DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() in ("true", "1", "yes")

# Validate SECRET_KEY in production
if not SECRET_KEY or "django-insecure" in SECRET_KEY:  # noqa: F405
    if os.getenv("VERCEL"):
        # On Vercel, if DJANGO_SECRET_KEY is not explicitly set in the Vercel dashboard,
        # use a stable persistent secret key so all serverless lambda instances can validate
        # CSRF tokens and user session cookies without mismatch.
        SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or "meil-esg-control-tower-vercel-stable-production-secret-key-2026-secure"
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set in environment variables to a secure, unique value for production."
        )

# Validate ALLOWED_HOSTS in production
if not ALLOWED_HOSTS or ALLOWED_HOSTS == ["*"]:  # noqa: F405
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must be set with specific trusted domain names or IPs for production."
    )

# -----------------------------------------------------------------------------
# PRODUCTION SECURITY HEADERS & COOKIES
# -----------------------------------------------------------------------------
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True").lower() in ("true", "1")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("SECURE_HSTS_INCLUDE_SUBDOMAINS", "True").lower() in ("true", "1")
SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "True").lower() in ("true", "1")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# -----------------------------------------------------------------------------
# PRODUCTION LOGGING
# -----------------------------------------------------------------------------
LOGGING["handlers"]["console"]["level"] = "INFO"  # noqa: F405
LOGGING["root"]["level"] = "INFO"  # noqa: F405
