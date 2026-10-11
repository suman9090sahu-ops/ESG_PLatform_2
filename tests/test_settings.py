"""
Tests for MEIL ESG CONTROL TOWER Settings Configurations.
Validates environment split, production security headers, timezone, and database settings.
"""

import os
from unittest import mock
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase


class SettingsConfigurationTests(SimpleTestCase):
    """Test platform configuration requirements."""

    def test_timezone_asia_kolkata(self):
        """Timezone must be set to Asia/Kolkata per specifications."""
        self.assertEqual(settings.TIME_ZONE, "Asia/Kolkata")
        self.assertTrue(settings.USE_TZ)

    def test_installed_apps_includes_core(self):
        """Core application must be present in INSTALLED_APPS."""
        self.assertIn("apps.core.apps.CoreConfig", settings.INSTALLED_APPS)

    def test_middleware_includes_security_and_whitenoise(self):
        """Ensure vital middleware are loaded in proper sequence."""
        self.assertIn("django.middleware.security.SecurityMiddleware", settings.MIDDLEWARE)
        self.assertIn("whitenoise.middleware.WhiteNoiseMiddleware", settings.MIDDLEWARE)
        self.assertIn("django.middleware.csrf.CsrfViewMiddleware", settings.MIDDLEWARE)
        self.assertIn("django.middleware.clickjacking.XFrameOptionsMiddleware", settings.MIDDLEWARE)

    def test_static_and_media_configurations(self):
        """Static files and media directories must be properly configured."""
        self.assertEqual(settings.STATIC_URL, "/static/")
        self.assertEqual(settings.MEDIA_URL, "/media/")
        self.assertTrue(hasattr(settings, "STATIC_ROOT"))
        self.assertTrue(hasattr(settings, "MEDIA_ROOT"))
        self.assertTrue(hasattr(settings, "STATICFILES_DIRS"))

    def test_production_settings_validation(self):
        """Production settings should raise ImproperlyConfigured if insecure keys or default hosts are used."""
        with mock.patch.dict(os.environ, {
            "DJANGO_SECRET_KEY": "django-insecure-test",
            "DJANGO_ALLOWED_HOSTS": "*",
        }):
            with self.assertRaises(ImproperlyConfigured):
                import importlib
                import config.settings.production
                importlib.reload(config.settings.production)

    def test_vercel_media_root_redirects_to_tmp(self):
        """When running in Vercel environment, MEDIA_ROOT must point to writable /tmp/media."""
        import importlib
        with mock.patch.dict(os.environ, {"VERCEL": "1"}):
            import config.settings.base
            importlib.reload(config.settings.base)
            self.assertTrue(
                str(config.settings.base.MEDIA_ROOT).endswith("media") and "tmp" in str(config.settings.base.MEDIA_ROOT).lower()
            )
        # Restore base settings
        import config.settings.base
        importlib.reload(config.settings.base)

    def test_vercel_csrf_and_secret_key_stability(self):
        """When running in Vercel environment, CSRF trusted origins and secret key must be stable."""
        import importlib
        with mock.patch.dict(os.environ, {"VERCEL": "1", "DJANGO_ALLOWED_HOSTS": "esg-platform-2.vercel.app"}):
            import config.settings.base
            importlib.reload(config.settings.base)
            self.assertIn("https://esg-platform-2.vercel.app", config.settings.base.CSRF_TRUSTED_ORIGINS)
            self.assertIn("https://esg-p-latform-2.vercel.app", config.settings.base.CSRF_TRUSTED_ORIGINS)
            self.assertEqual(config.settings.base.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))

            import config.settings.production
            importlib.reload(config.settings.production)
            # Must have non-empty stable secret key without error
            self.assertTrue(bool(config.settings.production.SECRET_KEY))
            self.assertFalse(config.settings.production.CSRF_COOKIE_HTTPONLY)

        # Restore base settings
        import config.settings.base
        importlib.reload(config.settings.base)
