"""
Tests for MEIL ESG CONTROL TOWER Health Check Endpoint.
"""

from django.test import Client, TestCase
from django.urls import reverse


class HealthEndpointTests(TestCase):
    """Validate /health/ probe responses and payloads."""

    def setUp(self):
        self.client = Client()

    def test_health_check_returns_200_json(self):
        """Health check returns HTTP 200 with JSON payload."""
        response = self.client.get(reverse("core:health_check"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

        data = response.json()
        self.assertEqual(data.get("status"), "healthy")
        self.assertEqual(data.get("service"), "MEIL ESG CONTROL TOWER")
        self.assertEqual(data.get("database"), "connected")
        self.assertEqual(data.get("timezone"), "Asia/Kolkata")
        self.assertIn("timestamp", data)
        self.assertIn("environment", data)
        self.assertIn("version", data)
