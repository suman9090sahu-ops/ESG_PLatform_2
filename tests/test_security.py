"""
Tests for MEIL ESG CONTROL TOWER Security & Middleware.
"""

from django.test import Client, SimpleTestCase


class SecurityConfigurationTests(SimpleTestCase):
    """Validate security headers, CSRF enforcement, and cookie policies."""

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def test_x_frame_options_header_present(self):
        """X-Frame-Options header must prevent clickjacking."""
        response = self.client.get("/")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")

    def test_csrf_cookie_or_token_enforced_on_post(self):
        """POST without CSRF token must be rejected with 403 Forbidden."""
        response = self.client.post("/", {"data": "test"})
        # Should be rejected because no CSRF token was provided
        self.assertEqual(response.status_code, 403)
