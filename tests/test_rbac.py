"""
Role-Based Access Control (RBAC) Test Suite for MEIL ESG CONTROL TOWER.

Validates:
- Role recognition for all 5 enterprise personas:
  SITE_MANAGER, SUBSIDIARY_MANAGER, ESG_MANAGER, AUDITOR, MEIL_OPERATOR
- Server-side route authorization enforcement
- Cross-role route denial (403 Forbidden)
- Unauthenticated access redirection to login
- Dynamic sidebar navigation structure generated per role
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.auth_services import get_role_sidebar_menu
from apps.core.models import Role, UserRole

User = get_user_model()


class RBACTests(TestCase):
    """Test suite for server-side RBAC enforcement and navigation isolation."""

    def setUp(self):
        self.client = Client()
        self.password = "EnterpriseSecurePass123!@"

        # Create Roles
        self.site_role = Role.objects.create(code=Role.Code.SITE_MANAGER, name="Site Manager")
        self.sub_role = Role.objects.create(code=Role.Code.SUBSIDIARY_MANAGER, name="Subsidiary Manager")
        self.esg_role = Role.objects.create(code=Role.Code.ESG_MANAGER, name="ESG Governance Manager")
        self.auditor_role = Role.objects.create(code=Role.Code.AUDITOR, name="Assurance Auditor")
        self.operator_role = Role.objects.create(code=Role.Code.MEIL_OPERATOR, name="MEIL Operator")

        # Create Users for each persona
        self.site_user = User.objects.create_user(username="site_user", password=self.password)
        UserRole.objects.create(user=self.site_user, role=self.site_role, is_primary=True)

        self.sub_user = User.objects.create_user(username="sub_user", password=self.password)
        UserRole.objects.create(user=self.sub_user, role=self.sub_role, is_primary=True)

        self.esg_user = User.objects.create_user(username="esg_user", password=self.password)
        UserRole.objects.create(user=self.esg_user, role=self.esg_role, is_primary=True)

        self.auditor_user = User.objects.create_user(username="auditor_user", password=self.password)
        UserRole.objects.create(user=self.auditor_user, role=self.auditor_role, is_primary=True)

        self.operator_user = User.objects.create_user(username="operator_user", password=self.password)
        UserRole.objects.create(user=self.operator_user, role=self.operator_role, is_primary=True)

        self.unassigned_user = User.objects.create_user(username="no_role_user", password=self.password)

    def test_unauthenticated_requests_redirected_to_login(self):
        """Unauthenticated requests to any role dashboard are redirected to login with next param."""
        dashboard_urls = [
            reverse("core:site_manager_dashboard"),
            reverse("core:subsidiary_manager_dashboard"),
            reverse("core:esg_manager_dashboard"),
            reverse("core:auditor_dashboard"),
            reverse("core:meil_operator_dashboard"),
        ]
        for url in dashboard_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("core:login"), response.url)
            self.assertIn(f"next={url}", response.url)

    def test_site_manager_authorized_for_site_dashboard(self):
        """SITE_MANAGER can access their operational dashboard."""
        self.client.login(username="site_user", password=self.password)
        response = self.client.get(reverse("core:site_manager_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Site Manager Operational Dashboard")

    def test_site_manager_denied_from_other_role_dashboards(self):
        """SITE_MANAGER receives 403 Forbidden when attempting cross-role access."""
        self.client.login(username="site_user", password=self.password)
        unauthorized_urls = [
            reverse("core:subsidiary_manager_dashboard"),
            reverse("core:esg_manager_dashboard"),
            reverse("core:auditor_dashboard"),
            reverse("core:meil_operator_dashboard"),
        ]
        for url in unauthorized_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)

    def test_subsidiary_manager_authorized_for_sub_dashboard(self):
        """SUBSIDIARY_MANAGER can access their governance review dashboard."""
        self.client.login(username="sub_user", password=self.password)
        response = self.client.get(reverse("core:subsidiary_manager_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Subsidiary Manager Governance Dashboard")

    def test_subsidiary_manager_denied_from_other_dashboards(self):
        """SUBSIDIARY_MANAGER receives 403 Forbidden for corporate ESG & operational dashboards."""
        self.client.login(username="sub_user", password=self.password)
        unauthorized_urls = [
            reverse("core:site_manager_dashboard"),
            reverse("core:esg_manager_dashboard"),
            reverse("core:auditor_dashboard"),
            reverse("core:meil_operator_dashboard"),
        ]
        for url in unauthorized_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)

    def test_esg_manager_authorized_for_esg_dashboard(self):
        """ESG_MANAGER can access corporate governance dashboard."""
        self.client.login(username="esg_user", password=self.password)
        response = self.client.get(reverse("core:esg_manager_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ESG Manager Corporate Governance Dashboard")

    def test_esg_manager_denied_from_site_and_operator_dashboards(self):
        """ESG_MANAGER cannot access site operational or operator command hubs."""
        self.client.login(username="esg_user", password=self.password)
        for url in [reverse("core:site_manager_dashboard"), reverse("core:meil_operator_dashboard")]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)

    def test_auditor_authorized_for_auditor_dashboard(self):
        """AUDITOR can access independent assurance dashboard."""
        self.client.login(username="auditor_user", password=self.password)
        response = self.client.get(reverse("core:auditor_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Auditor Independent Assurance Dashboard")

    def test_auditor_denied_from_site_and_operator_dashboards(self):
        """AUDITOR cannot access site manager or operator command dashboards."""
        self.client.login(username="auditor_user", password=self.password)
        for url in [reverse("core:site_manager_dashboard"), reverse("core:meil_operator_dashboard")]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)

    def test_meil_operator_authorized_for_operator_hub(self):
        """MEIL_OPERATOR can access the operator control hub."""
        self.client.login(username="operator_user", password=self.password)
        response = self.client.get(reverse("core:meil_operator_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MEIL Operator Control Hub")

    def test_user_without_roles_denied_from_all_dashboards(self):
        """Authenticated user without assigned roles is denied from all role dashboards."""
        self.client.login(username="no_role_user", password=self.password)
        dashboard_urls = [
            reverse("core:site_manager_dashboard"),
            reverse("core:subsidiary_manager_dashboard"),
            reverse("core:esg_manager_dashboard"),
            reverse("core:auditor_dashboard"),
            reverse("core:meil_operator_dashboard"),
        ]
        for url in dashboard_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)

    def test_role_aware_sidebar_navigation_menus(self):
        """Sidebar navigation menu reflects each role's functional domain."""
        site_nav = get_role_sidebar_menu(self.site_user)
        self.assertEqual(site_nav[0]["title"], "Site Operations")
        site_labels = [item["label"] for item in site_nav[0]["items"]]
        self.assertIn("Site Dashboard", site_labels)
        self.assertIn("My Assigned Sites", site_labels)
        self.assertIn("ESG Data Entry", site_labels)

        sub_nav = get_role_sidebar_menu(self.sub_user)
        self.assertEqual(sub_nav[0]["title"], "Subsidiary Review")
        sub_labels = [item["label"] for item in sub_nav[0]["items"]]
        self.assertIn("Subsidiary Dashboard", sub_labels)
        self.assertIn("Assigned Subsidiaries", sub_labels)

        esg_nav = get_role_sidebar_menu(self.esg_user)
        self.assertEqual(esg_nav[0]["title"], "Corporate ESG")
        esg_labels = [item["label"] for item in esg_nav[0]["items"]]
        self.assertIn("Scope 1, 2, 3 GHG", esg_labels)
        self.assertIn("BRSR Finalization", esg_labels)

        auditor_nav = get_role_sidebar_menu(self.auditor_user)
        self.assertEqual(auditor_nav[0]["title"], "Assurance & Audit")
        auditor_labels = [item["label"] for item in auditor_nav[0]["items"]]
        self.assertIn("Calculation Lineage", auditor_labels)
        self.assertIn("Audit Findings", auditor_labels)

        op_nav = get_role_sidebar_menu(self.operator_user)
        self.assertEqual(op_nav[0]["title"], "Operations Command")
        op_labels = [item["label"] for item in op_nav[0]["items"]]
        self.assertIn("Security Audit Log", op_labels)
