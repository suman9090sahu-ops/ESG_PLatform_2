"""
Unit and Integration Test Suite for Site Manager Assigned Site Workspace.

Validates the complete specification in MASTER PROMPT:
1. Login and Navigation:
   - Site Manager is redirected to /site-manager/dashboard/ after login (including with next=/dashboard/).
   - Accessing /dashboard/ directly redirects Site Manager to /site-manager/dashboard/.
   - Other roles (ESG_MANAGER, SUBSIDIARY_MANAGER) retain their appropriate dashboards.
   - Navigation and breadcrumbs point to "My Assigned Site" without Control Tower shortcuts.
   - No redirect loops occur.
2. Site Authorization & Scoping:
   - Single site assignment directly opens that site workspace.
   - Multi-site assignment displays a scoped site selector.
   - IDOR protection: requesting unassigned site ID in query param does not leak foreign site data.
   - Site Manager with no assignment sees "No site has been assigned to your account. Please contact your administrator."
   - Workflow displays 4 guided steps (Data Entry -> Evidence -> Validation -> Submit & Track).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.auth_services import get_role_sidebar_menu
from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    CollectionFrequency,
    Company,
    OrganizationStatus,
    PeriodStatus,
    Project,
    ReportingPeriod,
    Role,
    ScopeClassification,
    Site,
    SiteAssignment,
    Subsidiary,
    SubsidiaryAssignment,
    UnitDimension,
    UnitOfMeasure,
    UserRole,
)

User = get_user_model()


class AssignedSiteWorkspaceTests(TestCase):
    """Integration tests verifying the Site Manager My Assigned Site workspace."""

    @classmethod
    def setUpTestData(cls):
        # 1. Roles
        cls.site_mgr_role, _ = Role.objects.get_or_create(
            code=Role.Code.SITE_MANAGER,
            defaults={"name": "Site Manager", "is_active": True},
        )
        cls.sub_mgr_role, _ = Role.objects.get_or_create(
            code=Role.Code.SUBSIDIARY_MANAGER,
            defaults={"name": "Subsidiary Manager", "is_active": True},
        )
        cls.esg_mgr_role, _ = Role.objects.get_or_create(
            code=Role.Code.ESG_MANAGER,
            defaults={"name": "ESG Governance Manager", "is_active": True},
        )

        # 2. Organization structure
        cls.company = Company.objects.create(
            name="MEIL Global Infrastructure",
            code="MEIL-CORP",
            is_active=True,
        )
        cls.subsidiary = Subsidiary.objects.create(
            company=cls.company,
            name="MEIL Hydro Division",
            short_name="MEIL-HYDRO",
            code="SUB-HYDRO-01",
            status=OrganizationStatus.ACTIVE,
        )
        cls.project = Project.objects.create(
            subsidiary=cls.subsidiary,
            name="Polavaram National Project",
            code="PRJ-POL-01",
            status=OrganizationStatus.ACTIVE,
        )
        cls.site_1 = Site.objects.create(
            project=cls.project,
            name="Polavaram Dam Headworks Site",
            code="SITE-POL-101",
            status=OrganizationStatus.ACTIVE,
        )
        cls.site_2 = Site.objects.create(
            project=cls.project,
            name="Spillway Auxiliary Site",
            code="SITE-POL-102",
            status=OrganizationStatus.ACTIVE,
        )
        cls.unassigned_site = Site.objects.create(
            project=cls.project,
            name="Remote Solar Station",
            code="SITE-SOL-999",
            status=OrganizationStatus.ACTIVE,
        )

        # 3. Reporting Period
        cls.period = ReportingPeriod.objects.create(
            company=cls.company,
            code="FY2026-Q3",
            name="Financial Year 2026 Q3",
            start_date="2026-10-01",
            end_date="2026-12-31",
            status=PeriodStatus.OPEN,
        )

        # 4. Users
        cls.password = "StrongPassword@123"

        # User 1: Single assigned site
        cls.sm_single = User.objects.create_user(
            username="sm_single",
            email="sm_single@meil.in",
            password=cls.password,
            department="Hydro Operations",
        )
        UserRole.objects.create(user=cls.sm_single, role=cls.site_mgr_role, is_primary=True)
        SiteAssignment.objects.create(user=cls.sm_single, site=cls.site_1)

        # User 2: Multiple assigned sites
        cls.sm_multi = User.objects.create_user(
            username="sm_multi",
            email="sm_multi@meil.in",
            password=cls.password,
            department="Hydro Operations",
        )
        UserRole.objects.create(user=cls.sm_multi, role=cls.site_mgr_role, is_primary=True)
        SiteAssignment.objects.create(user=cls.sm_multi, site=cls.site_1)
        SiteAssignment.objects.create(user=cls.sm_multi, site=cls.site_2)

        # User 3: Zero assigned sites
        cls.sm_zero = User.objects.create_user(
            username="sm_zero",
            email="sm_zero@meil.in",
            password=cls.password,
            department="Operations",
        )
        UserRole.objects.create(user=cls.sm_zero, role=cls.site_mgr_role, is_primary=True)

        # User 4: ESG Manager (for comparison)
        cls.esg_user = User.objects.create_user(
            username="esg_governor",
            email="governor@meil.in",
            password=cls.password,
            department="Sustainability",
        )
        UserRole.objects.create(user=cls.esg_user, role=cls.esg_mgr_role, is_primary=True)

    def test_site_manager_post_login_redirect(self):
        """Site Manager logging in without 'next' is redirected to /site-manager/dashboard/."""
        response = self.client.post(
            reverse("core:login"),
            {"username": "sm_single", "password": self.password},
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:site_manager_dashboard"))

    def test_site_manager_login_with_generic_dashboard_next_param(self):
        """Site Manager with next=/dashboard/ is redirected to /site-manager/dashboard/, not generic dashboard."""
        response = self.client.post(
            reverse("core:login") + "?next=/dashboard/",
            {"username": "sm_single", "password": self.password},
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:site_manager_dashboard"))

    def test_site_manager_login_with_control_tower_next_param(self):
        """Site Manager with next=/dashboard/control-tower/ is redirected to /site-manager/dashboard/."""
        response = self.client.post(
            reverse("core:login") + "?next=/dashboard/control-tower/",
            {"username": "sm_single", "password": self.password},
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:site_manager_dashboard"))

    def test_direct_access_to_dashboard_redirects_site_manager(self):
        """Accessing /dashboard/ directly redirects Site Manager to /site-manager/dashboard/."""
        self.client.login(username="sm_single", password=self.password)
        response = self.client.get(reverse("core:control_tower_dashboard"), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:site_manager_dashboard"))

    def test_direct_access_to_dashboard_allowed_for_esg_manager(self):
        """ESG Manager accessing /dashboard/ is NOT redirected to site-manager dashboard."""
        self.client.login(username="esg_governor", password=self.password)
        response = self.client.get(reverse("core:control_tower_dashboard"), follow=False)
        self.assertEqual(response.status_code, 200)

    def test_site_manager_sidebar_navigation_items(self):
        """Site Manager sidebar menu contains only assigned site operational items."""
        menu = get_role_sidebar_menu(self.sm_single)
        self.assertIsNotNone(menu)
        items = menu[0]["items"]
        labels = [item["label"] for item in items]
        urls = [item["url"] for item in items]

        # Must contain 'My Assigned Site'
        self.assertIn("My Assigned Site", labels)
        self.assertIn(reverse("core:site_manager_dashboard"), urls)

        # Must contain operational workflow items
        self.assertIn("ESG Data Entry", labels)
        self.assertIn("My Activity Data", labels)
        self.assertIn("Evidence", labels)
        self.assertIn("Validation Issues", labels)
        self.assertIn("Submissions", labels)
        self.assertIn("Corrections", labels)

        # Must NOT contain generic Control Tower or UI preview items
        self.assertNotIn("Control Tower", labels)
        self.assertNotIn("Executive ESG Dashboard", labels)
        self.assertNotIn("Executive Dashboard", labels)
        self.assertNotIn("UI Component Library", labels)

    def test_single_site_workspace_renders_site_details(self):
        """Single site manager lands on workspace with exact assigned site details."""
        self.client.login(username="sm_single", password=self.password)
        response = self.client.get(reverse("core:site_manager_dashboard"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        # Header requirements
        self.assertIn("My Assigned Site", content)
        self.assertIn("Polavaram Dam Headworks Site", content)
        self.assertIn("SITE-POL-101", content)
        self.assertIn("Polavaram National Project", content)
        self.assertIn("FY2026-Q3", content)

        # Guided workflow
        self.assertIn("1. Data Entry", content)
        self.assertIn("2. Evidence", content)
        self.assertIn("3. Validation", content)
        self.assertIn("4. Submit &amp; Track", content)

        # Compact summary cards
        self.assertIn("Assigned Site", content)
        self.assertIn("Data Entry Tasks", content)
        self.assertIn("Missing Evidence", content)
        self.assertIn("Validation Issues", content)

        # Multi-site selector should NOT be rendered when only 1 site is assigned
        self.assertNotIn("id=\"site-selector\"", content)

        # Unassigned site must not appear
        self.assertNotIn("SITE-SOL-999", content)

    def test_multi_site_manager_renders_site_selector(self):
        """Multi-site manager sees the site selector with only authorized sites."""
        self.client.login(username="sm_multi", password=self.password)
        response = self.client.get(reverse("core:site_manager_dashboard"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("id=\"site-selector\"", content)
        self.assertIn("SITE-POL-101", content)
        self.assertIn("SITE-POL-102", content)
        # Unassigned site must not be in the selector
        self.assertNotIn("SITE-SOL-999", content)

    def test_site_switcher_switches_active_site_and_persists_session(self):
        """Selecting site 2 switches the active site scope and persists in session."""
        self.client.login(username="sm_multi", password=self.password)
        response = self.client.get(
            reverse("core:site_manager_dashboard") + f"?site_id={self.site_2.id}"
        )
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("SITE-POL-102", content)
        self.assertIn("Spillway Auxiliary Site", content)

        # Verify session persistence on subsequent request
        response_next = self.client.get(reverse("core:site_manager_dashboard"))
        content_next = response_next.content.decode("utf-8")
        self.assertIn("SITE-POL-102", content_next)

    def test_idor_protection_ignores_unassigned_site_id(self):
        """Tampering ?site_id with an unassigned site ID falls back to authorized site without leaking data."""
        self.client.login(username="sm_single", password=self.password)
        response = self.client.get(
            reverse("core:site_manager_dashboard") + f"?site_id={self.unassigned_site.id}"
        )
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        # Must show the authorized site
        self.assertIn("SITE-POL-101", content)
        # Must NEVER leak the unauthorized site
        self.assertNotIn("SITE-SOL-999", content)
        self.assertNotIn("Remote Solar Station", content)

    def test_zero_assigned_sites_empty_state(self):
        """Site Manager with zero assignments sees the explicit guidance message without foreign data."""
        self.client.login(username="sm_zero", password=self.password)
        response = self.client.get(reverse("core:site_manager_dashboard"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("No site has been assigned to your account. Please contact your administrator.", content)
        self.assertNotIn("SITE-POL-101", content)
        self.assertNotIn("SITE-POL-102", content)
        self.assertNotIn("SITE-SOL-999", content)

    def test_navbar_and_breadcrumbs_reflect_assigned_site(self):
        """Top navbar brand and breadcrumbs point to My Assigned Site for Site Manager."""
        self.client.login(username="sm_single", password=self.password)
        response = self.client.get(reverse("core:site_manager_dashboard"))
        content = response.content.decode("utf-8")

        # Navbar brand logo links to site manager dashboard
        self.assertIn("href=\"/site-manager/dashboard/\"", content)
        # Breadcrumb text
        self.assertIn("My Assigned Site", content)
        # Generic Control Tower heading must not be present
        self.assertNotIn("Executive ESG Control Tower", content)
