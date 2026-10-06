"""
Testing settings for MEIL ESG CONTROL TOWER.
"""

from .base import *  # noqa: F403

DEBUG = False

SECRET_KEY = "test-secret-key-for-meil-esg-control-tower-testing-suite"

ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

# Fast in-memory SQLite database for test suite isolation and speed
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Fast password hasher for tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# In-memory email backend for testing
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Standard static files storage during tests
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Disable noisy logging during test execution
LOGGING["handlers"]["console"]["level"] = "CRITICAL"  # noqa: F405
LOGGING["root"]["level"] = "CRITICAL"  # noqa: F405
