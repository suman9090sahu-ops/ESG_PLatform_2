"""
Tests for MEIL ESG CONTROL TOWER Custom Error Handlers (400, 403, 404, 500).
"""

from django.test import RequestFactory, SimpleTestCase
from apps.core.views import handler400, handler403, handler404, handler500


class ErrorPagesTests(SimpleTestCase):
    """Validate that custom error handlers render custom styled templates and correct HTTP status codes."""

    def setUp(self):
        self.factory = RequestFactory()

    def test_handler400_renders_custom_template(self):
        """Handler 400 returns 400 and renders errors/400.html."""
        request = self.factory.get("/bad-request-test/")
        response = handler400(request)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "400", status_code=400)
        self.assertContains(response, "BAD REQUEST", status_code=400)

    def test_handler403_renders_custom_template(self):
        """Handler 403 returns 403 and renders errors/403.html."""
        request = self.factory.get("/forbidden-test/")
        response = handler403(request)
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "403", status_code=403)
        self.assertContains(response, "ACCESS FORBIDDEN", status_code=403)

    def test_handler404_renders_custom_template(self):
        """Handler 404 returns 404 and renders errors/404.html."""
        request = self.factory.get("/non-existent-page-path/")
        response = handler404(request)
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "404", status_code=404)
        self.assertContains(response, "PAGE NOT FOUND", status_code=404)

    def test_handler500_renders_custom_template(self):
        """Handler 500 returns 500 and renders errors/500.html."""
        request = self.factory.get("/server-error-test/")
        response = handler500(request)
        self.assertEqual(response.status_code, 500)
        self.assertContains(response, "500", status_code=500)
        self.assertContains(response, "INTERNAL SERVER ERROR", status_code=500)
