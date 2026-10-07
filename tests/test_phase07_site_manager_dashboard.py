"""
Comprehensive Test Suite for Phase 07 — Site Manager Dashboard & Operational Aggregation Layer.

Validates:
1. Authentication & Role-Based Access Control (RBAC):
   - Unauthenticated requests to /site-manager/dashboard/ and /dashboard/site-manager/ redirect to login
   - SITE_MANAGER persona accesses dashboard with 200 OK
   - MEIL_OPERATOR supervisor persona accesses dashboard with 200 OK
   - SUBSIDIARY_MANAGER receives 403 Forbidden
   - ESG_MANAGER receives 403 Forbidden
   - AUDITOR receives 403 Forbidden
   - Canonical alias /dashboard/site-manager/ redirects to /site-manager/dashboard/

2. Object Scoping & Strict Tenant Isolation (Anti-IDOR / No Data Leakage):
   - Site Manager sees ONLY their assigned sites
   - Unassigned sites belonging to other managers are never displayed
   - Query string manipulation (?site_id=...) does not alter authorized scope
   - Direct object inspection of unassigned site (/site-manager/sites/<id>/) returns 403 Forbidden

3. Accurate Metrics Aggregation & Multiple Site Handling:
   - Site counts reflect authorized sites accurately
   - Duplicate project counting prevented (Multiple sites under 1 project = 1 project count)
   - Sites under distinct projects correctly increment unique project count
   - Active vs Inactive site metrics computed accurately

4. Temporal Governance & Reporting Period Scoping:
   - Current OPEN period correctly identified and displayed in KPI cards and side panel
   - Closed or locked periods are handled cleanly with proper inactive badges
   - No active period scenario displays appropriate empty state and alert

5. Activity Master & Workflow Readiness (Phase 06 Integration & Phase 08 Hooks):
   - Approved ESG activity schemas count dynamically populated from Phase 06 catalog
   - Real zero counts for pending drafts/submissions/corrections (no fabricated data)
   - Data entry readiness badge reflects site assignment and open period status

6. Empty States Handling:
   - Zero assigned sites shows clear empty state and alert
   - Zero open reporting period shows clear empty state and alert
   - Zero pending actions displays "You're All Caught Up"
   - Zero audit logs displays "No Recent Activity"

7. Audit Trail Lineage & Query Optimization:
   - Scoped audit logs display only user-relevant and site-relevant events
   - N+1 query prevention verified via select_related
"""

from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.dashboard_services import get_site_manager_dashboard_context
from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    AuthAuditLog,
    CollectionFrequency,
    Company,
    MasterStatus,
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


class BaseSiteManagerDashboardTestCase(TestCase):
    """Base setup for Phase 07 Site Manager Dashboard tests."""

    @classmethod
    def setUpTestData(cls):
        # 1. Create Roles
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
        cls.auditor_role, _ = Role.objects.get_or_create(
            code=Role.Code.AUDITOR,
            defaults={"name": "Auditor", "is_active": True},
        )
        cls.operator_role, _ = Role.objects.get_or_create(
            code=Role.Code.MEIL_OPERATOR,
            defaults={"name": "MEIL Operations Lead", "is_active": True},
        )

        # 2. Create Organizational Hierarchy
        cls.company_1 = Company.objects.create(
            code="CO-ALPHA",
            name="Alpha Enterprise",
            status=OrganizationStatus.ACTIVE,
        )
        cls.company_2 = Company.objects.create(
            code="CO-BETA",
            name="Beta Enterprise",
            status=OrganizationStatus.ACTIVE,
        )

        cls.sub_1 = Subsidiary.objects.create(
            code="SUB-HYDRO",
            name="Hydro Power Division",
            company=cls.company_1,
            status=OrganizationStatus.ACTIVE,
        )
        cls.sub_2 = Subsidiary.objects.create(
            code="SUB-SOLAR",
            name="Solar Energy Division",
            company=cls.company_2,
            status=OrganizationStatus.ACTIVE,
        )

        cls.proj_1 = Project.objects.create(
            code="PRJ-DAM-01",
            name="Polavaram Dam Project",
            subsidiary=cls.sub_1,
            status=OrganizationStatus.ACTIVE,
        )
        cls.proj_2 = Project.objects.create(
            code="PRJ-POWER-02",
            name="Powerhouse Hydel Project",
            subsidiary=cls.sub_1,
            status=OrganizationStatus.ACTIVE,
        )
        cls.proj_solar = Project.objects.create(
            code="PRJ-SOL-01",
            name="Kurnool Solar Project",
            subsidiary=cls.sub_2,
            status=OrganizationStatus.ACTIVE,
        )

        cls.site_1a = Site.objects.create(
            code="SITE-DAM-101",
            name="Dam Barrier Section",
            project=cls.proj_1,
            location="Eluru, AP",
            facility_type="Hydro Dam",
            status=OrganizationStatus.ACTIVE,
        )
        cls.site_1b = Site.objects.create(
            code="SITE-DAM-102",
            name="Dam Spillway Gates",
            project=cls.proj_1,
            location="Eluru, AP",
            facility_type="Spillway",
            status=OrganizationStatus.ACTIVE,
        )
        cls.site_2a = Site.objects.create(
            code="SITE-PWR-201",
            name="Turbine Gallery 1",
            project=cls.proj_2,
            location="Polavaram, AP",
            facility_type="Hydel Powerhouse",
            status=OrganizationStatus.ACTIVE,
        )
        cls.site_solar = Site.objects.create(
            code="SITE-SOL-301",
            name="Solar Inverter Station",
            project=cls.proj_solar,
            location="Kurnool, AP",
            facility_type="Solar Array",
            status=OrganizationStatus.ACTIVE,
        )

        # 3. Create Reporting Periods
        today = timezone.now().date()
        cls.open_period = ReportingPeriod.objects.create(
            company=cls.company_1,
            code="FY2025-26",
            name="FY 2025-26 Operational Cycle",
            fiscal_year="FY 2025-26",
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=60),
            status=PeriodStatus.OPEN,
        )
        cls.locked_period = ReportingPeriod.objects.create(
            company=cls.company_1,
            code="FY2024-25",
            name="FY 2024-25 Audited Cycle",
            fiscal_year="FY 2024-25",
            start_date=today - timedelta(days=395),
            end_date=today - timedelta(days=31),
            status=PeriodStatus.LOCKED,
        )

        # 4. Create Activity Master Entries
        cls.category_fuel = ActivityCategory.objects.create(
            code="FUEL",
            name="Fuel & Combustion",
            display_order=1,
            status=MasterStatus.ACTIVE,
        )
        cls.category_energy = ActivityCategory.objects.create(
            code="ENERGY",
            name="Electricity & Energy",
            display_order=2,
            status=MasterStatus.ACTIVE,
        )
        cls.unit_litre = UnitOfMeasure.objects.create(
            code="LITRE",
            name="Litre",
            symbol="L",
            dimension=UnitDimension.VOLUME,
            status=MasterStatus.ACTIVE,
        )
        cls.act_diesel = ActivityMaster.objects.create(
            code="FUEL-DIESEL-GEN",
            name="Diesel Generator Fuel",
            category=cls.category_fuel,
            activity_type="Stationary Combustion",
            base_unit=cls.unit_litre,
            scope_classification=ScopeClassification.SCOPE_1,
            collection_frequency=CollectionFrequency.MONTHLY,
            status=MasterStatus.ACTIVE,
        )

        # 5. Create Test Users
        # User 1: Site Manager A (Assigned to Site 1a & Site 1b under Project 1)
        cls.user_sm_a = User.objects.create_user(
            username="site_manager_a",
            password="SecurePass123!",
            first_name="Ramesh",
            last_name="Kumar",
            designation="Site In-Charge",
        )
        UserRole.objects.create(user=cls.user_sm_a, role=cls.site_mgr_role, is_primary=True)
        SiteAssignment.objects.create(user=cls.user_sm_a, site=cls.site_1a)
        SiteAssignment.objects.create(user=cls.user_sm_a, site=cls.site_1b)

        # User 2: Site Manager B (Assigned to Site 2a under Project 2)
        cls.user_sm_b = User.objects.create_user(
            username="site_manager_b",
            password="SecurePass123!",
            first_name="Suresh",
            last_name="Reddy",
            designation="Powerhouse Lead",
        )
        UserRole.objects.create(user=cls.user_sm_b, role=cls.site_mgr_role, is_primary=True)
        SiteAssignment.objects.create(user=cls.user_sm_b, site=cls.site_2a)

        # User 3: Unassigned Site Manager
        cls.user_sm_unassigned = User.objects.create_user(
            username="site_manager_none",
            password="SecurePass123!",
            first_name="Unassigned",
            last_name="Engineer",
        )
        UserRole.objects.create(user=cls.user_sm_unassigned, role=cls.site_mgr_role, is_primary=True)

        # User 4: Subsidiary Manager
        cls.user_sub_mgr = User.objects.create_user(
            username="sub_manager",
            password="SecurePass123!",
            first_name="Priya",
            last_name="Sharma",
        )
        UserRole.objects.create(user=cls.user_sub_mgr, role=cls.sub_mgr_role, is_primary=True)
        SubsidiaryAssignment.objects.create(user=cls.user_sub_mgr, subsidiary=cls.sub_1)

        # User 5: ESG Manager
        cls.user_esg_mgr = User.objects.create_user(
            username="esg_governance_mgr",
            password="SecurePass123!",
            first_name="Ananya",
            last_name="Iyer",
        )
        UserRole.objects.create(user=cls.user_esg_mgr, role=cls.esg_mgr_role, is_primary=True)

        # User 6: Auditor
        cls.user_auditor = User.objects.create_user(
            username="external_auditor",
            password="SecurePass123!",
            first_name="Vikram",
            last_name="Mehta",
        )
        UserRole.objects.create(user=cls.user_auditor, role=cls.auditor_role, is_primary=True)

        # User 7: MEIL Operator
        cls.user_operator = User.objects.create_user(
            username="platform_operator",
            password="SecurePass123!",
            first_name="Kiran",
            last_name="Varma",
        )
        UserRole.objects.create(user=cls.user_operator, role=cls.operator_role, is_primary=True)


class TestSiteManagerDashboardAuthAndRBAC(BaseSiteManagerDashboardTestCase):
    """Verifies authentication boundaries and role-based access control for Site Manager Dashboard."""

    def test_unauthenticated_request_redirects_to_login(self):
        """Unauthenticated user accessing /site-manager/dashboard/ must be redirected to login."""
        client = Client()
        url = reverse("core:site_manager_dashboard")
        response = client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login/", response.url)

    def test_unauthenticated_alias_redirects_to_login(self):
        """Unauthenticated user accessing /dashboard/site-manager/ must be redirected to login."""
        client = Client()
        url = reverse("core:site_manager_dashboard_alias")
        response = client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login/", response.url)

    def test_site_manager_persona_access_granted(self):
        """Authenticated SITE_MANAGER receives 200 OK."""
        client = Client()
        client.force_login(self.user_sm_a)
        response = client.get(reverse("core:site_manager_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboards/site_manager.html")

    def test_meil_operator_persona_access_granted(self):
        """Authenticated MEIL_OPERATOR supervisor receives 200 OK."""
        client = Client()
        client.force_login(self.user_operator)
        response = client.get(reverse("core:site_manager_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_subsidiary_manager_persona_denied(self):
        """SUBSIDIARY_MANAGER attempting to access Site Manager dashboard receives 403 Forbidden."""
        client = Client()
        client.force_login(self.user_sub_mgr)
        response = client.get(reverse("core:site_manager_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_esg_manager_persona_denied(self):
        """ESG_MANAGER attempting to access Site Manager dashboard receives 403 Forbidden."""
        client = Client()
        client.force_login(self.user_esg_mgr)
        response = client.get(reverse("core:site_manager_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_auditor_persona_denied(self):
        """AUDITOR attempting to access Site Manager dashboard receives 403 Forbidden."""
        client = Client()
        client.force_login(self.user_auditor)
        response = client.get(reverse("core:site_manager_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_canonical_alias_redirects_to_site_manager_dashboard(self):
        """Authenticated /dashboard/site-manager/ redirects to /site-manager/dashboard/."""
        client = Client()
        client.force_login(self.user_sm_a)
        response = client.get(reverse("core:site_manager_dashboard_alias"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("core:site_manager_dashboard"))


class TestSiteManagerDashboardScopeAndIsolation(BaseSiteManagerDashboardTestCase):
    """Verifies strict object-level scoping, IDOR prevention, and cross-site isolation."""

    def test_site_manager_sees_only_assigned_sites(self):
        """User A sees only Site 1a & 1b. Site 2a and Solar site are NOT in HTML response."""
        client = Client()
        client.force_login(self.user_sm_a)
        response = client.get(reverse("core:site_manager_dashboard"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        # Assigned sites must be present
        self.assertIn("SITE-DAM-101", content)
        self.assertIn("Dam Barrier Section", content)
        self.assertIn("SITE-DAM-102", content)
        self.assertIn("Dam Spillway Gates", content)

        # Unassigned sites must NOT be present
        self.assertNotIn("SITE-PWR-201", content)
        self.assertNotIn("Turbine Gallery 1", content)
        self.assertNotIn("SITE-SOL-301", content)
        self.assertNotIn("Solar Inverter Station", content)

    def test_site_manager_b_isolation(self):
        """User B sees only Site 2a. Sites 1a, 1b, and Solar site are NOT in HTML response."""
        client = Client()
        client.force_login(self.user_sm_b)
        response = client.get(reverse("core:site_manager_dashboard"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("SITE-PWR-201", content)
        self.assertIn("Turbine Gallery 1", content)
        self.assertNotIn("SITE-DAM-101", content)
        self.assertNotIn("SITE-DAM-102", content)
        self.assertNotIn("SITE-SOL-301", content)

    def test_query_string_tampering_ignored(self):
        """Passing ?site_id=<unassigned_site> does NOT leak unassigned site or change scope."""
        client = Client()
        client.force_login(self.user_sm_a)
        # Attempt to tamper with site_id query parameter
        response = client.get(f"{reverse('core:site_manager_dashboard')}?site_id={self.site_2a.id}")
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("SITE-DAM-101", content)
        self.assertNotIn("SITE-PWR-201", content)
        self.assertNotIn("Turbine Gallery 1", content)

    def test_unassigned_site_direct_detail_denied(self):
        """Direct URL tampering to unassigned site detail (/site-manager/sites/<id>/) returns 403."""
        client = Client()
        client.force_login(self.user_sm_a)
        response = client.get(reverse("core:site_detail", kwargs={"site_id": self.site_2a.id}))
        self.assertEqual(response.status_code, 403)


class TestSiteManagerDashboardMetricsAndAggregation(BaseSiteManagerDashboardTestCase):
    """Verifies accurate calculation of metrics, multi-site handling, and duplicate project prevention."""

    def test_duplicate_project_counting_prevented(self):
        """User A has 2 sites under PRJ-DAM-01. Project count must equal 1, not 2."""
        context = get_site_manager_dashboard_context(self.user_sm_a)
        self.assertEqual(context["sites_count"], 2)
        self.assertEqual(context["active_sites_count"], 2)
        self.assertEqual(context["projects_count"], 1)
        self.assertEqual(context["active_projects_count"], 1)

    def test_multiple_projects_counted_accurately(self):
        """When assigned to sites across multiple projects, distinct project count is accurate."""
        # Assign User B to an additional site under Project 1
        SiteAssignment.objects.create(user=self.user_sm_b, site=self.site_1a)
        context = get_site_manager_dashboard_context(self.user_sm_b)
        self.assertEqual(context["sites_count"], 2)  # Site 2a (Proj 2) + Site 1a (Proj 1)
        self.assertEqual(context["projects_count"], 2)  # Proj 2 + Proj 1
        self.assertEqual(context["active_projects_count"], 2)

    def test_reporting_period_resolution(self):
        """Open period FY2025-26 is correctly resolved as current_period."""
        context = get_site_manager_dashboard_context(self.user_sm_a)
        self.assertIsNotNone(context["current_period"])
        self.assertEqual(context["current_period"].code, "FY2025-26")
        self.assertEqual(context["current_period"].status, PeriodStatus.OPEN)

    def test_activity_master_catalog_count(self):
        """Catalog metrics reflect active approved schemas from Phase 06."""
        context = get_site_manager_dashboard_context(self.user_sm_a)
        self.assertEqual(context["active_activities_count"], 1)
        self.assertEqual(context["active_categories_count"], 2)

    def test_workflow_status_and_pending_actions_zero_count(self):
        """Real zero counts for pending items without fabricated metrics."""
        context = get_site_manager_dashboard_context(self.user_sm_a)
        self.assertEqual(context["pending_actions_count"], 0)
        self.assertEqual(context["workflow_status"]["draft_records_count"], 0)
        self.assertEqual(context["workflow_status"]["submitted_records_count"], 0)
        self.assertEqual(context["workflow_status"]["corrections_count"], 0)
        self.assertTrue(context["workflow_status"]["is_data_entry_ready"])


class TestSiteManagerDashboardEmptyStates(BaseSiteManagerDashboardTestCase):
    """Verifies that empty states and alerts render gracefully without errors."""

    def test_unassigned_site_manager_empty_state(self):
        """Site Manager with zero assigned sites sees proper empty state and alert."""
        client = Client()
        client.force_login(self.user_sm_unassigned)
        response = client.get(reverse("core:site_manager_dashboard"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("No Sites Assigned", content)
        self.assertIn("No operational sites are currently assigned to your account", content)
        self.assertIn("No Assigned Operational Sites", content)

    def test_no_open_reporting_period_empty_state(self):
        """When no reporting period is open, warning alert and inactive badge render."""
        # Temporarily close the open period
        self.open_period.status = PeriodStatus.CLOSED
        self.open_period.save()

        client = Client()
        client.force_login(self.user_sm_a)
        response = client.get(reverse("core:site_manager_dashboard"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("No Active Reporting Period", content)
        self.assertIn("None Open", content)

        # Restore period
        self.open_period.status = PeriodStatus.OPEN
        self.open_period.save()

    def test_pending_actions_empty_state(self):
        """When 0 actions are pending, displays 'You\'re All Caught Up'."""
        client = Client()
        client.force_login(self.user_sm_a)
        response = client.get(reverse("core:site_manager_dashboard"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertTrue("You're All Caught Up" in content or "You&#x27;re All Caught Up" in content or "You&#39;re All Caught Up" in content)
        self.assertIn("0 Pending", content)

    def test_recent_activity_empty_state(self):
        """When no audit logs exist, displays 'No Recent Activity'."""
        client = Client()
        client.force_login(self.user_sm_a)
        response = client.get(reverse("core:site_manager_dashboard"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("No Recent Activity", content)


class TestSiteManagerDashboardAuditLineage(BaseSiteManagerDashboardTestCase):
    """Verifies scoped audit logging in the recent activity feed."""

    def test_recent_activity_displays_user_and_site_logs(self):
        """Audit logs for user or user's assigned site appear in recent activity."""
        # Create an audit event for User A
        AuthAuditLog.objects.create(
            user=self.user_sm_a,
            event_type=AuthAuditLog.EventType.LOGIN_SUCCESS,
            resource_accessed="Site:SITE-DAM-101",
            details="User logged in to Dam site",
            success=True,
        )

        # Create an audit event for another user and other site
        AuthAuditLog.objects.create(
            user=self.user_sm_b,
            event_type=AuthAuditLog.EventType.LOGIN_SUCCESS,
            resource_accessed="Site:SITE-PWR-201",
            details="User B logged in to Powerhouse",
            success=True,
        )

        client = Client()
        client.force_login(self.user_sm_a)
        response = client.get(reverse("core:site_manager_dashboard"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        self.assertIn("User logged in to Dam site", content)
        self.assertNotIn("User B logged in to Powerhouse", content)


class TestSiteManagerDashboardQueryOptimization(BaseSiteManagerDashboardTestCase):
    """Verifies query count bounding and prefetching to prevent N+1 database queries."""

    def test_query_count_is_bounded(self):
        """
        Adding additional sites does not cause query explosion (select_related is active).
        Verifies O(1) query complexity with respect to assigned site count (no N+1 queries).
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client = Client()
        client.force_login(self.user_sm_a)

        # Baseline query count with 2 sites
        with CaptureQueriesContext(connection) as ctx_2_sites:
            response_1 = client.get(reverse("core:site_manager_dashboard"))
            self.assertEqual(response_1.status_code, 200)

        count_2_sites = len(ctx_2_sites)

        # Assign 2 more sites under another project to user_sm_a
        SiteAssignment.objects.create(user=self.user_sm_a, site=self.site_2a)
        SiteAssignment.objects.create(user=self.user_sm_a, site=self.site_solar)

        # Query count with 4 sites
        with CaptureQueriesContext(connection) as ctx_4_sites:
            response_2 = client.get(reverse("core:site_manager_dashboard"))
            self.assertEqual(response_2.status_code, 200)

        count_4_sites = len(ctx_4_sites)

        # The query count must NOT scale with the number of sites (no N+1 per site)
        # Any difference must be 0 or at most 2 due to extra distinct projects in scoping
        self.assertLessEqual(count_4_sites, count_2_sites + 2)
