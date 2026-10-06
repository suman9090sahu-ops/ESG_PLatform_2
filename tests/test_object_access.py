"""
Object-Level Authorization & IDOR Test Suite for MEIL ESG CONTROL TOWER.

Validates:
- Object-level access verification for Operational Sites & Subsidiaries
- IDOR (Insecure Direct Object Reference) prevention via direct URL tampering:
  - User A assigned to Site 101 -> accesses /site-manager/sites/101/ -> 200 ALLOWED
  - User A assigned to Site 101 -> accesses /site-manager/sites/102/ (User B's site) -> 403 DENIED
- Subsidiary-level object isolation:
  - Subsidiary Manager assigned to Hydro Division -> accesses Hydro -> 200 ALLOWED
  - Subsidiary Manager assigned to Hydro Division -> accesses Solar Division -> 403 DENIED
- Multi-tier inheritance:
  - Subsidiary Manager can inspect sites under their assigned subsidiary
  - Subsidiary Manager denied from inspecting sites under other subsidiaries
- Privilege Escalation Prevention:
  - Lower-privileged users cannot access administrative endpoints or assign roles
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.auth_services import (
    user_can_access_company,
    user_can_access_project,
    user_can_access_site,
    user_can_access_subsidiary,
)
from apps.core.models import (
    AuthAuditLog,
    Company,
    Project,
    Role,
    Site,
    SiteAssignment,
    Subsidiary,
    SubsidiaryAssignment,
    UserRole,
)

User = get_user_model()


class ObjectLevelAuthorizationTests(TestCase):
    """Test suite for object-level scoping, IDOR protection, and privilege escalation."""

    def setUp(self):
        self.client = Client()
        self.password = "EnterpriseSecretPass123!@"

        # 1. Setup Roles
        self.site_role = Role.objects.create(code=Role.Code.SITE_MANAGER, name="Site Manager")
        self.sub_role = Role.objects.create(code=Role.Code.SUBSIDIARY_MANAGER, name="Subsidiary Manager")
        self.auditor_role = Role.objects.create(code=Role.Code.AUDITOR, name="Assurance Auditor")
        self.operator_role = Role.objects.create(code=Role.Code.MEIL_OPERATOR, name="MEIL Operator")

        # 2. Setup Organizational Hierarchy
        self.company = Company.objects.create(name="MEIL Enterprise", code="MEIL-ENT")

        self.hydro_sub = Subsidiary.objects.create(
            name="Hydro Division", code="MEIL-HYDRO", company=self.company
        )
        self.solar_sub = Subsidiary.objects.create(
            name="Solar Division", code="MEIL-SOLAR", company=self.company
        )

        self.hydro_proj = Project.objects.create(
            name="Polavaram Project", code="PRJ-POL", subsidiary=self.hydro_sub
        )
        self.solar_proj = Project.objects.create(
            name="Kurnool Solar Project", code="PRJ-KRN", subsidiary=self.solar_sub
        )

        # Operational Sites: Site 101 (Hydro), Site 102 (Hydro), Site 201 (Solar)
        self.site_101 = Site.objects.create(
            name="Polavaram Dam Headworks", code="SITE-POL-101", project=self.hydro_proj
        )
        self.site_102 = Site.objects.create(
            name="Polavaram Spillway Channel", code="SITE-POL-102", project=self.hydro_proj
        )
        self.site_201 = Site.objects.create(
            name="Kurnool Array 1", code="SITE-KRN-201", project=self.solar_proj
        )

        # 3. Setup Users & Scopes
        # User A: Assigned to Site 101 only
        self.user_a = User.objects.create_user(username="user_a_site101", password=self.password)
        UserRole.objects.create(user=self.user_a, role=self.site_role, is_primary=True)
        SiteAssignment.objects.create(user=self.user_a, site=self.site_101)

        # User B: Assigned to Site 102 only
        self.user_b = User.objects.create_user(username="user_b_site102", password=self.password)
        UserRole.objects.create(user=self.user_b, role=self.site_role, is_primary=True)
        SiteAssignment.objects.create(user=self.user_b, site=self.site_102)

        # Subsidiary Manager: Assigned to Hydro Division
        self.sub_mgr = User.objects.create_user(username="hydro_manager", password=self.password)
        UserRole.objects.create(user=self.sub_mgr, role=self.sub_role, is_primary=True)
        SubsidiaryAssignment.objects.create(user=self.sub_mgr, subsidiary=self.hydro_sub)

        # Auditor: Independent read-only
        self.auditor = User.objects.create_user(username="assurance_auditor", password=self.password)
        UserRole.objects.create(user=self.auditor, role=self.auditor_role, is_primary=True)

        # Operator: Platform Lead
        self.operator = User.objects.create_user(username="meil_lead", password=self.password)
        UserRole.objects.create(user=self.operator, role=self.operator_role, is_primary=True)

    # -------------------------------------------------------------------------
    # 1. SITE-LEVEL OBJECT AUTHORIZATION & IDOR TESTS
    # -------------------------------------------------------------------------

    def test_site_manager_access_assigned_site_allowed(self):
        """User A can access their assigned site 101 via direct URL."""
        self.client.login(username="user_a_site101", password=self.password)
        response = self.client.get(reverse("core:site_detail", kwargs={"site_id": self.site_101.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.site_101.name)
        self.assertContains(response, "ACCESS PERMITTED")

    def test_idor_direct_url_tampering_denied(self):
        """User A attempting to access Site 102 by tampering URL parameter is rejected with 403 Forbidden."""
        self.client.login(username="user_a_site101", password=self.password)
        # Attempt direct IDOR manipulation to Site 102
        response = self.client.get(reverse("core:site_detail", kwargs={"site_id": self.site_102.id}))
        self.assertEqual(response.status_code, 403)

        # Verify audit log captured IDOR violation attempt
        audit_entry = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            user=self.user_a,
        ).first()
        self.assertIsNotNone(audit_entry)
        self.assertIn("IDOR violation", audit_entry.details)

    def test_service_helper_user_can_access_site(self):
        """Service helper user_can_access_site evaluates correctly."""
        self.assertTrue(user_can_access_site(self.user_a, self.site_101))
        self.assertFalse(user_can_access_site(self.user_a, self.site_102))
        self.assertFalse(user_can_access_site(self.user_a, self.site_201))

        self.assertFalse(user_can_access_site(self.user_b, self.site_101))
        self.assertTrue(user_can_access_site(self.user_b, self.site_102))

    # -------------------------------------------------------------------------
    # 2. SUBSIDIARY-LEVEL OBJECT AUTHORIZATION & HIERARCHY INHERITANCE
    # -------------------------------------------------------------------------

    def test_subsidiary_manager_access_assigned_subsidiary_allowed(self):
        """Subsidiary manager can inspect their assigned Hydro division."""
        self.client.login(username="hydro_manager", password=self.password)
        response = self.client.get(reverse("core:subsidiary_detail", kwargs={"subsidiary_id": self.hydro_sub.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.hydro_sub.name)

    def test_subsidiary_manager_access_unassigned_subsidiary_denied(self):
        """Subsidiary manager receives 403 when tampering URL to access Solar division."""
        self.client.login(username="hydro_manager", password=self.password)
        response = self.client.get(reverse("core:subsidiary_detail", kwargs={"subsidiary_id": self.solar_sub.id}))
        self.assertEqual(response.status_code, 403)

    def test_subsidiary_manager_can_access_sites_under_assigned_subsidiary(self):
        """Subsidiary manager inherits access to sites under assigned subsidiary."""
        # Hydro manager can access Hydro sites 101 and 102
        self.assertTrue(user_can_access_site(self.sub_mgr, self.site_101))
        self.assertTrue(user_can_access_site(self.sub_mgr, self.site_102))
        # But cannot access Solar site 201
        self.assertFalse(user_can_access_site(self.sub_mgr, self.site_201))

        self.client.login(username="hydro_manager", password=self.password)
        # Access to site 101 -> 200 OK
        resp_101 = self.client.get(reverse("core:site_detail", kwargs={"site_id": self.site_101.id}))
        self.assertEqual(resp_101.status_code, 200)

        # Access to site 201 -> 403 Forbidden
        resp_201 = self.client.get(reverse("core:site_detail", kwargs={"site_id": self.site_201.id}))
        self.assertEqual(resp_201.status_code, 403)

    # -------------------------------------------------------------------------
    # 3. AUDITOR & OPERATOR PRIVILEGE ENFORCEMENT
    # -------------------------------------------------------------------------

    def test_auditor_has_transparent_read_access_across_sites(self):
        """Auditor can inspect sites for assurance purposes."""
        self.client.login(username="assurance_auditor", password=self.password)
        resp_101 = self.client.get(reverse("core:site_detail", kwargs={"site_id": self.site_101.id}))
        self.assertEqual(resp_101.status_code, 200)

        resp_201 = self.client.get(reverse("core:site_detail", kwargs={"site_id": self.site_201.id}))
        self.assertEqual(resp_201.status_code, 200)

    def test_operator_has_operational_read_access(self):
        """MEIL Operator can inspect operational sites."""
        self.client.login(username="meil_lead", password=self.password)
        resp_101 = self.client.get(reverse("core:site_detail", kwargs={"site_id": self.site_101.id}))
        self.assertEqual(resp_101.status_code, 200)

    # -------------------------------------------------------------------------
    # 4. PRIVILEGE ESCALATION CHECKS
    # -------------------------------------------------------------------------

    def test_non_staff_cannot_access_django_admin(self):
        """Site manager without is_staff cannot access /admin/ (redirected or 302)."""
        self.client.login(username="user_a_site101", password=self.password)
        response = self.client.get(reverse("admin:index"))
        self.assertNotEqual(response.status_code, 200)

    def test_unauthenticated_direct_url_redirected(self):
        """Unauthenticated direct request to site detail endpoint redirects to login."""
        response = self.client.get(reverse("core:site_detail", kwargs={"site_id": self.site_101.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("core:login"), response.url)
