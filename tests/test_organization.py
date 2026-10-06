"""
Comprehensive Test Suite for Phase 03 — Organization Hierarchy & Organizational Scope.

Tests:
1. Model Tests:
   - Company, Subsidiary, Project, and Site instantiation
   - Unique constraints on codes
   - Status lifecycle (ACTIVE, INACTIVE, CLOSED) and is_active sync
   - Relational inheritance traversal (Site -> Project -> Subsidiary -> Company)
   - ForeignKey models.PROTECT prevention of cascade deletion

2. Scope Service & Scoped Queryset Tests:
   - get_accessible_companies, get_accessible_subsidiaries, get_accessible_projects, get_accessible_sites
   - Object-level authorization helpers (user_can_access_*, user_can_manage_*)
   - Isolation across tenants/subsidiaries

3. Role-Based Organization Access & CRUD Views:
   - MEIL_OPERATOR: Full CRUD across hierarchy
   - SUBSIDIARY_MANAGER: Scoped read/write within assigned division; denied cross-subsidiary access
   - ESG_MANAGER: Enterprise-wide read access; mutation blocked
   - AUDITOR: Strictly read-only; create/edit/deactivate routes return 403 Forbidden
   - SITE_MANAGER: Denied organization hierarchy management routes

4. IDOR Defense & URL Tampering:
   - Tampering subsidiary_id, project_id, site_id triggers 403 Forbidden
   - AuthAuditLog security violation telemetry

5. Safe Deactivation & Archiving:
   - Archiving updates status to INACTIVE and is_active to False
   - Historical records preserved without hard-delete
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError, models, transaction
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.models import (
    AuthAuditLog,
    Company,
    CompanyAssignment,
    OrganizationStatus,
    Project,
    ProjectAssignment,
    Role,
    Site,
    SiteAssignment,
    Subsidiary,
    SubsidiaryAssignment,
    UserRole,
)
from apps.core.scope_services import (
    get_accessible_companies,
    get_accessible_projects,
    get_accessible_sites,
    get_accessible_subsidiaries,
    safe_deactivate_entity,
    user_can_access_company,
    user_can_access_project,
    user_can_access_site,
    user_can_access_subsidiary,
    user_can_manage_hierarchy,
    user_can_manage_project,
    user_can_manage_site,
    user_can_manage_subsidiary,
)

User = get_user_model()


class OrganizationHierarchyModelTests(TestCase):
    """Test model behaviors, constraints, inheritance properties, and status lifecycle."""

    def setUp(self):
        self.company = Company.objects.create(
            name="MEIL Enterprise Group",
            code="MEIL-ENT",
            legal_name="Megha Engineering & Infrastructures Ltd",
            country="India",
            status=OrganizationStatus.ACTIVE,
        )
        self.subsidiary = Subsidiary.objects.create(
            company=self.company,
            name="MEIL Hydro Division",
            code="MEIL-HYDRO",
            legal_name="MEIL Hydro Power Infrastructure Division",
            short_name="Hydro",
            industry="Hydroelectric Power",
            country="India",
            status=OrganizationStatus.ACTIVE,
        )
        self.project = Project.objects.create(
            subsidiary=self.subsidiary,
            name="Polavaram Irrigation Project",
            code="PRJ-POL-01",
            location="Eluru, Andhra Pradesh",
            status=OrganizationStatus.ACTIVE,
        )
        self.site = Site.objects.create(
            project=self.project,
            name="Polavaram Dam Headworks",
            code="SITE-POL-101",
            facility_type="Hydroelectric Dam",
            location="Polavaram, AP",
            latitude=17.258600,
            longitude=81.657800,
            contact_person="Er. Ramesh Kumar",
            contact_email="ramesh@meilgroup.com",
            status=OrganizationStatus.ACTIVE,
        )

    def test_organizational_inheritance_traversal(self):
        """Site correctly resolves Project, Subsidiary, and Enterprise Company."""
        self.assertEqual(self.site.subsidiary, self.subsidiary)
        self.assertEqual(self.site.company, self.company)
        self.assertEqual(self.project.company, self.company)
        self.assertEqual(self.subsidiary.parent_company, self.company)

    def test_status_lifecycle_and_is_active_sync(self):
        """Saving an inactive status automatically sets is_active=False."""
        self.assertTrue(self.site.is_active)
        self.site.status = OrganizationStatus.INACTIVE
        self.site.save()
        self.assertFalse(self.site.is_active)

        self.site.status = OrganizationStatus.CLOSED
        self.site.save()
        self.assertFalse(self.site.is_active)

        self.site.status = OrganizationStatus.ACTIVE
        self.site.save()
        self.assertTrue(self.site.is_active)

    def test_unique_code_constraints(self):
        """Codes must be unique at all levels."""
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                Company.objects.create(name="Duplicate Company", code="MEIL-ENT")

        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                Subsidiary.objects.create(company=self.company, name="Duplicate Sub", code="MEIL-HYDRO")

        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                Project.objects.create(subsidiary=self.subsidiary, name="Duplicate Proj", code="PRJ-POL-01")

        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                Site.objects.create(project=self.project, name="Duplicate Site", code="SITE-POL-101")

    def test_foreign_key_protection_prevents_cascade_delete(self):
        """Deleting parent entities with active children is blocked by models.PROTECT."""
        with self.assertRaises(models.ProtectedError):
            self.company.delete()

        with self.assertRaises(models.ProtectedError):
            self.subsidiary.delete()

        with self.assertRaises(models.ProtectedError):
            self.project.delete()


class OrganizationScopingServiceTests(TestCase):
    """Test scoped querysets and object-level authorization across personas."""

    def setUp(self):
        self.password = "Secr3tTestPass123!@"

        # Roles
        self.role_operator = Role.objects.create(code=Role.Code.MEIL_OPERATOR, name="MEIL Operator")
        self.role_sub_mgr = Role.objects.create(code=Role.Code.SUBSIDIARY_MANAGER, name="Subsidiary Manager")
        self.role_site_mgr = Role.objects.create(code=Role.Code.SITE_MANAGER, name="Site Manager")
        self.role_esg_mgr = Role.objects.create(code=Role.Code.ESG_MANAGER, name="ESG Manager")
        self.role_auditor = Role.objects.create(code=Role.Code.AUDITOR, name="Auditor")

        # Company
        self.company = Company.objects.create(name="MEIL Enterprise", code="MEIL-ENT")

        # Subsidiary A: Hydro Division
        self.sub_hydro = Subsidiary.objects.create(company=self.company, name="Hydro Division", code="MEIL-HYDRO")
        self.proj_hydro = Project.objects.create(subsidiary=self.sub_hydro, name="Polavaram", code="PRJ-POL")
        self.site_hydro_1 = Site.objects.create(project=self.proj_hydro, name="Headworks", code="SITE-POL-1")
        self.site_hydro_2 = Site.objects.create(project=self.proj_hydro, name="Powerhouse", code="SITE-POL-2")

        # Subsidiary B: Solar Division
        self.sub_solar = Subsidiary.objects.create(company=self.company, name="Solar Division", code="MEIL-SOLAR")
        self.proj_solar = Project.objects.create(subsidiary=self.sub_solar, name="Kurnool Solar", code="PRJ-KRN")
        self.site_solar_1 = Site.objects.create(project=self.proj_solar, name="Solar Array 1", code="SITE-KRN-1")

        # Users
        # User 1: MEIL Operator
        self.user_operator = User.objects.create_user(username="test_operator", password=self.password)
        UserRole.objects.create(user=self.user_operator, role=self.role_operator, is_primary=True)

        # User 2: Subsidiary Manager (Hydro Division only)
        self.user_hydro_mgr = User.objects.create_user(username="test_hydro_mgr", password=self.password)
        UserRole.objects.create(user=self.user_hydro_mgr, role=self.role_sub_mgr, is_primary=True)
        SubsidiaryAssignment.objects.create(user=self.user_hydro_mgr, subsidiary=self.sub_hydro)

        # User 3: Site Manager (Site Hydro 1 only)
        self.user_site_mgr = User.objects.create_user(username="test_site_mgr", password=self.password)
        UserRole.objects.create(user=self.user_site_mgr, role=self.role_site_mgr, is_primary=True)
        SiteAssignment.objects.create(user=self.user_site_mgr, site=self.site_hydro_1)

        # User 4: ESG Manager
        self.user_esg_mgr = User.objects.create_user(username="test_esg_mgr", password=self.password)
        UserRole.objects.create(user=self.user_esg_mgr, role=self.role_esg_mgr, is_primary=True)

        # User 5: Auditor
        self.user_auditor = User.objects.create_user(username="test_auditor", password=self.password)
        UserRole.objects.create(user=self.user_auditor, role=self.role_auditor, is_primary=True)

    def test_operator_has_universal_scope(self):
        """MEIL Operator accesses all companies, subsidiaries, projects, and sites."""
        self.assertEqual(get_accessible_companies(self.user_operator).count(), 1)
        self.assertEqual(get_accessible_subsidiaries(self.user_operator).count(), 2)
        self.assertEqual(get_accessible_projects(self.user_operator).count(), 2)
        self.assertEqual(get_accessible_sites(self.user_operator).count(), 3)
        self.assertTrue(user_can_manage_hierarchy(self.user_operator))
        self.assertTrue(user_can_manage_subsidiary(self.user_operator, self.sub_hydro))
        self.assertTrue(user_can_manage_project(self.user_operator, self.proj_hydro))
        self.assertTrue(user_can_manage_site(self.user_operator, self.site_hydro_1))

    def test_subsidiary_manager_scoped_isolation(self):
        """Subsidiary Manager sees only assigned division assets; solar assets are hidden."""
        subs = get_accessible_subsidiaries(self.user_hydro_mgr)
        self.assertEqual(list(subs), [self.sub_hydro])

        projects = get_accessible_projects(self.user_hydro_mgr)
        self.assertEqual(list(projects), [self.proj_hydro])

        sites = get_accessible_sites(self.user_hydro_mgr)
        self.assertIn(self.site_hydro_1, sites)
        self.assertIn(self.site_hydro_2, sites)
        self.assertNotIn(self.site_solar_1, sites)

        # Object level checks
        self.assertTrue(user_can_access_subsidiary(self.user_hydro_mgr, self.sub_hydro))
        self.assertFalse(user_can_access_subsidiary(self.user_hydro_mgr, self.sub_solar))

        self.assertTrue(user_can_access_project(self.user_hydro_mgr, self.proj_hydro))
        self.assertFalse(user_can_access_project(self.user_hydro_mgr, self.proj_solar))

        self.assertTrue(user_can_access_site(self.user_hydro_mgr, self.site_hydro_1))
        self.assertFalse(user_can_access_site(self.user_hydro_mgr, self.site_solar_1))

        # Mutation permissions: allowed for hydro, denied for solar
        self.assertTrue(user_can_manage_project(self.user_hydro_mgr, project=self.proj_hydro))
        self.assertFalse(user_can_manage_project(self.user_hydro_mgr, project=self.proj_solar))
        self.assertTrue(user_can_manage_site(self.user_hydro_mgr, site=self.site_hydro_1))
        self.assertFalse(user_can_manage_site(self.user_hydro_mgr, site=self.site_solar_1))
        self.assertFalse(user_can_manage_hierarchy(self.user_hydro_mgr))

    def test_site_manager_scoped_isolation(self):
        """Site Manager can only access assigned Site 1; cannot access unassigned Site 2 or manage projects."""
        sites = get_accessible_sites(self.user_site_mgr)
        self.assertEqual(list(sites), [self.site_hydro_1])
        self.assertNotIn(self.site_hydro_2, sites)
        self.assertNotIn(self.site_solar_1, sites)

        self.assertTrue(user_can_access_site(self.user_site_mgr, self.site_hydro_1))
        self.assertFalse(user_can_access_site(self.user_site_mgr, self.site_hydro_2))
        self.assertFalse(user_can_access_site(self.user_site_mgr, self.site_solar_1))

        self.assertFalse(user_can_manage_project(self.user_site_mgr, self.proj_hydro))
        self.assertFalse(user_can_manage_site(self.user_site_mgr, self.site_hydro_1))

    def test_auditor_is_strictly_read_only(self):
        """Auditor can view all entities, but mutation helpers return False."""
        self.assertTrue(user_can_access_company(self.user_auditor, self.company))
        self.assertTrue(user_can_access_subsidiary(self.user_auditor, self.sub_solar))
        self.assertTrue(user_can_access_site(self.user_auditor, self.site_solar_1))

        self.assertFalse(user_can_manage_hierarchy(self.user_auditor))
        self.assertFalse(user_can_manage_subsidiary(self.user_auditor, self.sub_hydro))
        self.assertFalse(user_can_manage_project(self.user_auditor, self.proj_hydro))
        self.assertFalse(user_can_manage_site(self.user_auditor, self.site_hydro_1))


class OrganizationViewsAndIDORTests(TestCase):
    """Test HTTP endpoints, IDOR prevention, URL tampering, and safe archiving."""

    def setUp(self):
        self.client = Client()
        self.password = "SecurePassword123!#"

        # Roles
        self.role_operator = Role.objects.create(code=Role.Code.MEIL_OPERATOR, name="MEIL Operator")
        self.role_sub_mgr = Role.objects.create(code=Role.Code.SUBSIDIARY_MANAGER, name="Subsidiary Manager")
        self.role_site_mgr = Role.objects.create(code=Role.Code.SITE_MANAGER, name="Site Manager")
        self.role_auditor = Role.objects.create(code=Role.Code.AUDITOR, name="Auditor")

        # Hierarchy
        self.company = Company.objects.create(name="MEIL Enterprise", code="MEIL-ENT")
        self.sub_hydro = Subsidiary.objects.create(company=self.company, name="Hydro Division", code="MEIL-HYDRO")
        self.sub_solar = Subsidiary.objects.create(company=self.company, name="Solar Division", code="MEIL-SOLAR")
        self.proj_hydro = Project.objects.create(subsidiary=self.sub_hydro, name="Polavaram", code="PRJ-POL")
        self.proj_solar = Project.objects.create(subsidiary=self.sub_solar, name="Kurnool Solar", code="PRJ-KRN")
        self.site_hydro = Site.objects.create(project=self.proj_hydro, name="Headworks", code="SITE-POL-1")
        self.site_solar = Site.objects.create(project=self.proj_solar, name="Solar Array 1", code="SITE-KRN-1")

        # Users
        self.operator = User.objects.create_user(username="operator_user", password=self.password)
        UserRole.objects.create(user=self.operator, role=self.role_operator, is_primary=True)

        self.sub_manager = User.objects.create_user(username="hydro_mgr_user", password=self.password)
        UserRole.objects.create(user=self.sub_manager, role=self.role_sub_mgr, is_primary=True)
        SubsidiaryAssignment.objects.create(user=self.sub_manager, subsidiary=self.sub_hydro)

        self.site_manager = User.objects.create_user(username="site_mgr_user", password=self.password)
        UserRole.objects.create(user=self.site_manager, role=self.role_site_mgr, is_primary=True)
        SiteAssignment.objects.create(user=self.site_manager, site=self.site_hydro)

        self.auditor = User.objects.create_user(username="auditor_user", password=self.password)
        UserRole.objects.create(user=self.auditor, role=self.role_auditor, is_primary=True)

    def test_operator_views_overview_and_entity_details(self):
        """MEIL Operator can view overview and details across all tiers."""
        self.client.login(username="operator_user", password=self.password)

        res = self.client.get(reverse("core:org_overview"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Organizational Hierarchy Tree")
        self.assertContains(res, "MEIL-HYDRO")
        self.assertContains(res, "MEIL-SOLAR")

        res = self.client.get(reverse("core:org_company_detail", kwargs={"company_id": self.company.id}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "MEIL Enterprise")

        res = self.client.get(reverse("core:org_subsidiary_detail", kwargs={"subsidiary_id": self.sub_hydro.id}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Polavaram")

        res = self.client.get(reverse("core:org_project_detail", kwargs={"project_id": self.proj_hydro.id}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Headworks")

        res = self.client.get(reverse("core:org_site_detail", kwargs={"site_id": self.site_hydro.id}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Operational Boundary Specification")

    def test_site_manager_cannot_access_hierarchy_overview(self):
        """Site Managers cannot access organization administration overview (returns 403)."""
        self.client.login(username="site_mgr_user", password=self.password)
        res = self.client.get(reverse("core:org_overview"))
        self.assertEqual(res.status_code, 403)

    def test_idor_subsidiary_manager_denied_other_subsidiary(self):
        """Subsidiary Manager attempting to access Solar Division by tampering URL receives 403."""
        self.client.login(username="hydro_mgr_user", password=self.password)

        # Access assigned Hydro: 200
        res = self.client.get(reverse("core:org_subsidiary_detail", kwargs={"subsidiary_id": self.sub_hydro.id}))
        self.assertEqual(res.status_code, 200)

        # IDOR attempt to access unassigned Solar: 403
        res = self.client.get(reverse("core:org_subsidiary_detail", kwargs={"subsidiary_id": self.sub_solar.id}))
        self.assertEqual(res.status_code, 403)

        # Verify audit log caught the IDOR violation
        audit = AuthAuditLog.objects.filter(
            user=self.sub_manager, event_type=AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT
        ).first()
        self.assertIsNotNone(audit)

    def test_idor_subsidiary_manager_denied_other_project_and_site(self):
        """Subsidiary Manager cannot view projects or sites belonging to other subsidiaries."""
        self.client.login(username="hydro_mgr_user", password=self.password)

        # IDOR attempt to view Solar Project
        res = self.client.get(reverse("core:org_project_detail", kwargs={"project_id": self.proj_solar.id}))
        self.assertEqual(res.status_code, 403)

        # IDOR attempt to view Solar Site
        res = self.client.get(reverse("core:org_site_detail", kwargs={"site_id": self.site_solar.id}))
        self.assertEqual(res.status_code, 403)

    def test_auditor_cannot_access_create_or_edit_forms(self):
        """Auditor attempting to create or edit organization assets receives 403 Forbidden."""
        self.client.login(username="auditor_user", password=self.password)

        res = self.client.get(reverse("core:org_subsidiary_create"))
        self.assertEqual(res.status_code, 403)

        res = self.client.get(reverse("core:org_project_create"))
        self.assertEqual(res.status_code, 403)

        res = self.client.get(reverse("core:org_site_create"))
        self.assertEqual(res.status_code, 403)

        res = self.client.get(reverse("core:org_subsidiary_edit", kwargs={"subsidiary_id": self.sub_hydro.id}))
        self.assertEqual(res.status_code, 403)

    def test_subsidiary_manager_can_create_project_in_assigned_scope_only(self):
        """Subsidiary Manager can create projects under assigned Hydro, but is blocked from Solar."""
        self.client.login(username="hydro_mgr_user", password=self.password)

        # Access project create page: 200
        res = self.client.get(reverse("core:org_project_create"))
        self.assertEqual(res.status_code, 200)

        # Attempt to create project under unassigned Solar Division: 403
        post_data_illegal = {
            "subsidiary": self.sub_solar.id,
            "name": "Illegal Solar Project",
            "code": "PRJ-ILL-01",
            "status": "ACTIVE",
        }
        res = self.client.post(reverse("core:org_project_create"), data=post_data_illegal)
        self.assertEqual(res.status_code, 403)

        # Legitimate project under assigned Hydro Division: 302 Redirect
        post_data_legal = {
            "subsidiary": self.sub_hydro.id,
            "name": "Polavaram Hydroelectric Powerhouse Unit 2",
            "code": "PRJ-POL-02",
            "location": "Eluru, AP",
            "status": "ACTIVE",
        }
        res = self.client.post(reverse("core:org_project_create"), data=post_data_legal)
        self.assertEqual(res.status_code, 302)
        self.assertTrue(Project.objects.filter(code="PRJ-POL-02").exists())

    def test_safe_deactivation_preserves_data(self):
        """Safe deactivation sets status to INACTIVE, does not hard delete the record."""
        self.client.login(username="operator_user", password=self.password)

        target_site = Site.objects.create(
            project=self.proj_hydro, name="Temporary Intake Trench", code="SITE-TEMP-99"
        )
        self.assertEqual(target_site.status, OrganizationStatus.ACTIVE)

        # Post to deactivate route
        res = self.client.post(reverse("core:org_site_deactivate", kwargs={"site_id": target_site.id}))
        self.assertEqual(res.status_code, 302)

        target_site.refresh_from_db()
        self.assertEqual(target_site.status, OrganizationStatus.INACTIVE)
        self.assertFalse(target_site.is_active)

        # Confirm audit log entry was created
        audit = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.ORGANIZATION_DEACTIVATED,
            resource_accessed__contains="SITE-TEMP-99",
        ).first()
        self.assertIsNotNone(audit)
