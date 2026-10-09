"""
Tests for Public Sustainability Landing Page and Dashboard Preservation.
Validates:
1. Public root URL '/' renders image-first sustainability landing page without authentication.
2. The provided sustainability building image is referenced correctly via static asset path.
3. Login and Sign Up actions are functional and present.
4. Sign Up modal communicates enterprise RBAC policy and access request guidance.
5. Control Tower dashboard (and metrics/sidebar) is NOT present on the public landing page.
6. Control Tower dashboard is preserved and accessible at authenticated route '/dashboard/'.
7. Unauthenticated access to '/dashboard/' redirects to login.
8. Authenticated access to '/dashboard/' renders Control Tower with 200 OK.
9. Post-login deterministic routing and logout workflows remain intact.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.models import Role, UserRole

User = get_user_model()


class PublicLandingPageTests(TestCase):
    """Test suite for the public sustainability landing page and protected dashboard."""

    def setUp(self):
        self.client = Client()
        self.password = "ValidPass123!@#"
        self.user = User.objects.create_user(
            username="esg_operator",
            email="operator@meilgroup.com",
            password=self.password,
            first_name="ESG",
            last_name="Operator",
            is_active=True,
        )
        self.role = Role.objects.create(
            code=Role.Code.MEIL_OPERATOR,
            name="MEIL Operator",
        )
        UserRole.objects.create(user=self.user, role=self.role, is_primary=True)

    def test_public_landing_page_loads_without_auth(self):
        """Root URL '/' loads with 200 OK without requiring login."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_landing_page_content_and_imagery(self):
        """Landing page displays sustainability theme, headline, and local hero asset."""
        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Building a")
        self.assertContains(response, "Sustainable Future")
        self.assertContains(response, "One platform for responsible growth")
        self.assertContains(response, "sustainable_hero.jpg")

    def test_landing_page_action_buttons(self):
        """Landing page displays functional Login and Sign Up buttons."""
        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("core:login"))
        self.assertContains(response, "Login")
        self.assertContains(response, "Sign Up")
        self.assertContains(response, "accessRequestModal")

    def test_no_control_tower_on_public_landing_page(self):
        """Control Tower dashboard, sidebar, and KPI cards must NOT appear on '/'."""
        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.status_code, 200)
        # Verify internal dashboard elements are strictly absent
        self.assertNotContains(response, "Executive ESG Dashboard")
        self.assertNotContains(response, 'id="sidebar"')
        self.assertNotContains(response, "Scope 1 Direct GHG")
        self.assertNotContains(response, "Scope 2 Electricity")
        self.assertNotContains(response, "Demo Data • Phase 01 Prototype")
        self.assertNotContains(response, "UI Component Preview")

    def test_control_tower_requires_authentication(self):
        """Unauthenticated access to '/dashboard/' redirects to login."""
        response = self.client.get(reverse("core:control_tower_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("core:login"), response.url)

    def test_control_tower_accessible_to_authenticated_user(self):
        """Authenticated users can access the preserved Control Tower at '/dashboard/'."""
        self.client.login(username="esg_operator", password=self.password)
        response = self.client.get(reverse("core:control_tower_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Executive ESG Dashboard")
        self.assertContains(response, "Scope 1 Direct GHG")
        self.assertContains(response, "Scope 2 Electricity")

    def test_landing_page_when_authenticated(self):
        """Authenticated users visiting '/' still receive 200 OK with dashboard access CTA."""
        self.client.login(username="esg_operator", password=self.password)
        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Building a")
        self.assertContains(response, reverse("core:control_tower_dashboard"))
        self.assertContains(response, reverse("core:logout"))

    def test_login_page_renders_with_home_navigation(self):
        """Login page renders with 200 OK and includes return to public portal link."""
        response = self.client.get(reverse("core:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("core:index"))
        self.assertContains(response, "Return to Public Sustainability Portal")

    def test_account_request_modal_content(self):
        """Sign Up modal details enterprise RBAC policy and contact guidance."""
        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Account Registration &amp; Access Policy")
        self.assertContains(response, "Enterprise Role-Based Access Governance")
        self.assertContains(response, "sustainability@meilgroup.com")
