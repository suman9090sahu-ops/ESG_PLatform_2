"""
Comprehensive Test Suite for Phase 06 — Activity Master & ESG Catalog Foundation.

Validates:
1. Model Architecture & Integrity Rules:
   - Category creation, uniqueness, ordering, uppercase codes
   - UnitOfMeasure creation, uniqueness, symbols, dimensions
   - ActivityMaster creation, code uniqueness, category/base_unit PROTECT constraints
   - Allowed units ManyToMany relationship
   - Scope classification, frequency, and lifecycle state fields
   - Automatic code uppercase normalization
   - Historical referential integrity protection (no hard delete)

2. Master Data Governance & RBAC Services:
   - user_can_manage_activity_master (MEIL_OPERATOR, ESG_MANAGER = True; SITE_MANAGER, SUBSIDIARY_MANAGER, AUDITOR = False)
   - user_can_view_activity_master (All authenticated roles = True)
   - Queryset scoping: Site Manager confined strictly to ACTIVE approved activities; Admins see full lifecycle
   - Safe deactivation preserves historical data lineage without hard-deleting records
   - validate_activity_unit helper logic

3. HTTP Views & Authorization:
   - Catalog list view accessible to all 5 personas
   - Detail view accessible to all 5 personas
   - Create view: 200 for MEIL_OPERATOR & ESG_MANAGER; 403 Forbidden for SITE_MANAGER, SUBSIDIARY_MANAGER, AUDITOR
   - Edit view: 200 for MEIL_OPERATOR & ESG_MANAGER; 403 Forbidden for others
   - Deactivate toggle: 302 for MEIL_OPERATOR & ESG_MANAGER; 403 Forbidden for others
   - Audit logging with AuthAuditLog on all lifecycle mutations

4. IDOR Protection & Object Tampering Defense:
   - Access to non-existent ID returns 404 Not Found
   - Site Manager attempting to inspect deactivated activity directly returns 403 Forbidden
   - Unauthorized POST mutations to categories and units return 403 Forbidden
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, models
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.activity_services import (
    get_accessible_activity_categories,
    get_accessible_activity_masters,
    get_accessible_units,
    safe_activate_activity_master,
    safe_deactivate_activity_master,
    user_can_manage_activity_master,
    user_can_view_activity_master,
    validate_activity_unit,
)
from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    AuthAuditLog,
    CollectionFrequency,
    Company,
    CompanyAssignment,
    MasterStatus,
    Project,
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


class BaseActivityMasterTestCase(TestCase):
    """Base fixture establishing standard enterprise roles and personas."""

    def setUp(self):
        # 1. Roles
        self.role_operator, _ = Role.objects.get_or_create(code=Role.Code.MEIL_OPERATOR, defaults={"name": "MEIL Operator"})
        self.role_esg, _ = Role.objects.get_or_create(code=Role.Code.ESG_MANAGER, defaults={"name": "ESG Manager"})
        self.role_sub, _ = Role.objects.get_or_create(code=Role.Code.SUBSIDIARY_MANAGER, defaults={"name": "Subsidiary Manager"})
        self.role_site, _ = Role.objects.get_or_create(code=Role.Code.SITE_MANAGER, defaults={"name": "Site Manager"})
        self.role_auditor, _ = Role.objects.get_or_create(code=Role.Code.AUDITOR, defaults={"name": "Auditor"})

        # 2. Hierarchy
        self.company = Company.objects.create(code="CO-TEST", name="Test Enterprise", status="ACTIVE")
        self.subsidiary = Subsidiary.objects.create(code="SUB-TEST", name="Test Hydro Division", company=self.company, status="ACTIVE")
        self.project = Project.objects.create(code="PRJ-TEST", name="Test Power Project", subsidiary=self.subsidiary, status="ACTIVE")
        self.site = Site.objects.create(code="SITE-TEST", name="Test Dam Headworks", project=self.project, status="ACTIVE")

        # 3. Personas
        self.user_operator = User.objects.create_user(username="test_operator", password="Password123!")
        UserRole.objects.create(user=self.user_operator, role=self.role_operator, is_primary=True)
        CompanyAssignment.objects.create(user=self.user_operator, company=self.company)

        self.user_esg = User.objects.create_user(username="test_esg", password="Password123!")
        UserRole.objects.create(user=self.user_esg, role=self.role_esg, is_primary=True)
        CompanyAssignment.objects.create(user=self.user_esg, company=self.company)

        self.user_sub = User.objects.create_user(username="test_sub", password="Password123!")
        UserRole.objects.create(user=self.user_sub, role=self.role_sub, is_primary=True)
        SubsidiaryAssignment.objects.create(user=self.user_sub, subsidiary=self.subsidiary)

        self.user_site = User.objects.create_user(username="test_site", password="Password123!")
        UserRole.objects.create(user=self.user_site, role=self.role_site, is_primary=True)
        SiteAssignment.objects.create(user=self.user_site, site=self.site)

        self.user_auditor = User.objects.create_user(username="test_auditor", password="Password123!")
        UserRole.objects.create(user=self.user_auditor, role=self.role_auditor, is_primary=True)
        CompanyAssignment.objects.create(user=self.user_auditor, company=self.company)

        # 4. Standard Categories
        self.cat_fuel = ActivityCategory.objects.create(code="FUEL", name="Fuel & Combustion", display_order=1)
        self.cat_energy = ActivityCategory.objects.create(code="ENERGY", name="Electricity & Energy", display_order=2)
        self.cat_water = ActivityCategory.objects.create(code="WATER", name="Water Resources", display_order=3)

        # 5. Standard Units
        self.unit_litre = UnitOfMeasure.objects.create(code="LITRE", name="Litre", symbol="L", dimension=UnitDimension.VOLUME)
        self.unit_kwh = UnitOfMeasure.objects.create(code="KWH", name="Kilowatt Hour", symbol="kWh", dimension=UnitDimension.ENERGY)
        self.unit_mwh = UnitOfMeasure.objects.create(code="MWH", name="Megawatt Hour", symbol="MWh", dimension=UnitDimension.ENERGY)
        self.unit_kl = UnitOfMeasure.objects.create(code="KL", name="Kilolitre", symbol="kL", dimension=UnitDimension.VOLUME)

        # 6. Standard Activities
        self.act_diesel = ActivityMaster.objects.create(
            code="FUEL-DIESEL",
            name="Diesel Consumption",
            category=self.cat_fuel,
            activity_type="Stationary Combustion",
            base_unit=self.unit_litre,
            scope_classification=ScopeClassification.SCOPE_1,
            collection_frequency=CollectionFrequency.MONTHLY,
            evidence_requirement_hint="Fuel Delivery Challan / DG Log Book",
            status=MasterStatus.ACTIVE,
            created_by=self.user_operator,
            updated_by=self.user_operator,
        )
        self.act_diesel.allowed_units.add(self.unit_litre, self.unit_kl)

        self.act_grid = ActivityMaster.objects.create(
            code="ELEC-GRID",
            name="Grid Electricity",
            category=self.cat_energy,
            activity_type="Purchased Electricity",
            base_unit=self.unit_kwh,
            scope_classification=ScopeClassification.SCOPE_2,
            collection_frequency=CollectionFrequency.MONTHLY,
            status=MasterStatus.ACTIVE,
            created_by=self.user_operator,
            updated_by=self.user_operator,
        )
        self.act_grid.allowed_units.add(self.unit_kwh, self.unit_mwh)


class ActivityMasterModelTests(BaseActivityMasterTestCase):
    """Tests model definitions, constraints, and data integrity."""

    def test_category_creation_and_attributes(self):
        cat = ActivityCategory.objects.create(code="waste", name="Waste Management", display_order=4)
        self.assertEqual(cat.code, "WASTE")  # Uppercased
        self.assertEqual(cat.status, MasterStatus.ACTIVE)
        self.assertTrue(cat.is_active)
        self.assertEqual(str(cat), "Waste Management (WASTE)")
        self.assertEqual(cat.status_badge_class, "badge-success")

    def test_category_unique_code_constraint(self):
        with self.assertRaises(IntegrityError):
            ActivityCategory.objects.create(code="FUEL", name="Duplicate Fuel")

    def test_unit_creation_and_attributes(self):
        unit = UnitOfMeasure.objects.create(code="tonne", name="Metric Tonne", symbol="t", dimension=UnitDimension.MASS)
        self.assertEqual(unit.code, "TONNE")  # Uppercased
        self.assertEqual(unit.symbol, "t")
        self.assertEqual(str(unit), "Metric Tonne (t)")
        self.assertEqual(unit.status_badge_class, "badge-success")

    def test_unit_unique_code_constraint(self):
        with self.assertRaises(IntegrityError):
            UnitOfMeasure.objects.create(code="LITRE", name="Duplicate Litre", symbol="L", dimension=UnitDimension.VOLUME)

    def test_activity_master_creation_and_attributes(self):
        act = ActivityMaster.objects.create(
            code="water-borewell",
            name="Borewell Water",
            category=self.cat_water,
            activity_type="Groundwater",
            base_unit=self.unit_kl,
            scope_classification=ScopeClassification.NON_GHG,
            collection_frequency=CollectionFrequency.MONTHLY,
        )
        self.assertEqual(act.code, "WATER-BOREWELL")  # Uppercased
        self.assertEqual(act.status, MasterStatus.ACTIVE)
        self.assertTrue(act.is_active)
        self.assertEqual(act.scope_badge_class, "badge-success")
        self.assertEqual(str(act), "Borewell Water [WATER-BOREWELL]")

    def test_activity_master_unique_code_constraint(self):
        with self.assertRaises(IntegrityError):
            ActivityMaster.objects.create(
                code="FUEL-DIESEL",
                name="Another Diesel",
                category=self.cat_fuel,
                activity_type="Combustion",
                base_unit=self.unit_litre,
            )

    def test_category_protect_on_delete(self):
        """Historical integrity: Deleting a category referenced by activities must raise ProtectedError."""
        with self.assertRaises(models.ProtectedError):
            self.cat_fuel.delete()

    def test_base_unit_protect_on_delete(self):
        """Historical integrity: Deleting a base unit referenced by activities must raise ProtectedError."""
        with self.assertRaises(models.ProtectedError):
            self.unit_litre.delete()

    def test_allowed_units_m2m(self):
        self.assertIn(self.unit_litre, self.act_diesel.allowed_units.all())
        self.assertIn(self.unit_kl, self.act_diesel.allowed_units.all())
        self.assertNotIn(self.unit_kwh, self.act_diesel.allowed_units.all())


class ActivityMasterGovernanceServiceTests(BaseActivityMasterTestCase):
    """Tests service layer RBAC evaluation, scoping, and lifecycle state management."""

    def test_user_can_manage_activity_master(self):
        self.assertTrue(user_can_manage_activity_master(self.user_operator))
        self.assertTrue(user_can_manage_activity_master(self.user_esg))
        self.assertFalse(user_can_manage_activity_master(self.user_site))
        self.assertFalse(user_can_manage_activity_master(self.user_sub))
        self.assertFalse(user_can_manage_activity_master(self.user_auditor))

    def test_user_can_view_activity_master(self):
        self.assertTrue(user_can_view_activity_master(self.user_operator))
        self.assertTrue(user_can_view_activity_master(self.user_esg))
        self.assertTrue(user_can_view_activity_master(self.user_sub))
        self.assertTrue(user_can_view_activity_master(self.user_site))
        self.assertTrue(user_can_view_activity_master(self.user_auditor))

    def test_queryset_scoping_active_vs_inactive(self):
        # Create an inactive activity
        act_inactive = ActivityMaster.objects.create(
            code="FUEL-COAL-LEGACY",
            name="Legacy Coal Boiler",
            category=self.cat_fuel,
            activity_type="Stationary",
            base_unit=self.unit_litre,
            status=MasterStatus.INACTIVE,
        )

        # Operational Site Manager sees ONLY active activities
        site_qs = get_accessible_activity_masters(self.user_site)
        self.assertIn(self.act_diesel, site_qs)
        self.assertNotIn(act_inactive, site_qs)

        # Master Admins can see all activities when include_inactive=True
        admin_qs = get_accessible_activity_masters(self.user_operator, include_inactive=True)
        self.assertIn(self.act_diesel, admin_qs)
        self.assertIn(act_inactive, admin_qs)

    def test_safe_deactivate_and_activate_lifecycle(self):
        # 1. Deactivate
        safe_deactivate_activity_master(self.act_diesel, self.user_operator)
        self.act_diesel.refresh_from_db()
        self.assertEqual(self.act_diesel.status, MasterStatus.INACTIVE)
        self.assertFalse(self.act_diesel.is_active)
        self.assertEqual(self.act_diesel.updated_by, self.user_operator)

        # Verify audit event
        audit = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.ACTIVITY_MASTER_DEACTIVATED,
            resource_accessed__contains=self.act_diesel.code,
        ).first()
        self.assertIsNotNone(audit)

        # 2. Unauthorized role attempting safe_deactivate raises PermissionDenied
        with self.assertRaises(PermissionDenied):
            safe_deactivate_activity_master(self.act_grid, self.user_site)

        # 3. Activate again
        safe_activate_activity_master(self.act_diesel, self.user_operator)
        self.act_diesel.refresh_from_db()
        self.assertEqual(self.act_diesel.status, MasterStatus.ACTIVE)
        self.assertTrue(self.act_diesel.is_active)

    def test_validate_activity_unit_helper(self):
        # Allowed unit
        self.assertTrue(validate_activity_unit(self.act_diesel, self.unit_litre))
        self.assertTrue(validate_activity_unit(self.act_diesel, self.unit_kl))
        # Non-allowed unit
        self.assertFalse(validate_activity_unit(self.act_diesel, self.unit_kwh))


class ActivityMasterViewAuthorizationTests(BaseActivityMasterTestCase):
    """Tests HTTP endpoints and server-side RBAC enforcement across 5 personas."""

    def setUp(self):
        super().setUp()
        self.client_anon = Client()

        self.client_operator = Client()
        self.client_operator.force_login(self.user_operator)

        self.client_esg = Client()
        self.client_esg.force_login(self.user_esg)

        self.client_sub = Client()
        self.client_sub.force_login(self.user_sub)

        self.client_site = Client()
        self.client_site.force_login(self.user_site)

        self.client_auditor = Client()
        self.client_auditor.force_login(self.user_auditor)

    def test_unauthenticated_user_redirected(self):
        res = self.client_anon.get(reverse("core:activity_list"))
        self.assertEqual(res.status_code, 302)
        self.assertIn("/auth/login/", res.url)

    def test_list_view_accessible_to_all_roles(self):
        for client, name in [
            (self.client_operator, "MEIL_OPERATOR"),
            (self.client_esg, "ESG_MANAGER"),
            (self.client_sub, "SUBSIDIARY_MANAGER"),
            (self.client_site, "SITE_MANAGER"),
            (self.client_auditor, "AUDITOR"),
        ]:
            res = client.get(reverse("core:activity_list"))
            self.assertEqual(res.status_code, 200, f"List view failed for role {name}")
            self.assertContains(res, "FUEL-DIESEL")
            self.assertContains(res, "ELEC-GRID")

    def test_list_view_create_button_visibility(self):
        # Master admins see Define New Activity button
        res_admin = self.client_operator.get(reverse("core:activity_list"))
        self.assertContains(res_admin, "Define New Activity")

        # Site manager does NOT see Define New Activity button
        res_site = self.client_site.get(reverse("core:activity_list"))
        self.assertNotContains(res_site, "Define New Activity")

    def test_detail_view_accessible_to_all_roles(self):
        for client, name in [
            (self.client_operator, "MEIL_OPERATOR"),
            (self.client_esg, "ESG_MANAGER"),
            (self.client_sub, "SUBSIDIARY_MANAGER"),
            (self.client_site, "SITE_MANAGER"),
            (self.client_auditor, "AUDITOR"),
        ]:
            res = client.get(reverse("core:activity_detail", args=[self.act_diesel.id]))
            self.assertEqual(res.status_code, 200, f"Detail view failed for role {name}")
            self.assertContains(res, "Diesel Consumption")
            self.assertContains(res, "FUEL-DIESEL")

    def test_create_view_authorized_roles(self):
        res_get = self.client_operator.get(reverse("core:activity_create"))
        self.assertEqual(res_get.status_code, 200)

        # POST creation
        post_data = {
            "code": "WASTE-SCRAP",
            "name": "Metal Scrap Disposal",
            "category": self.cat_fuel.id,
            "activity_type": "Solid Waste",
            "base_unit": self.unit_litre.id,
            "allowed_units": [self.unit_litre.id],
            "scope_classification": ScopeClassification.SCOPE_3,
            "collection_frequency": CollectionFrequency.MONTHLY,
            "status": MasterStatus.ACTIVE,
        }
        res_post = self.client_operator.post(reverse("core:activity_create"), data=post_data)
        self.assertEqual(res_post.status_code, 302)
        created_act = ActivityMaster.objects.filter(code="WASTE-SCRAP").first()
        self.assertIsNotNone(created_act)
        self.assertEqual(created_act.created_by, self.user_operator)

    def test_create_view_unauthorized_roles_denied(self):
        # SITE_MANAGER, SUBSIDIARY_MANAGER, and AUDITOR must get 403 Forbidden
        for client, name in [
            (self.client_site, "SITE_MANAGER"),
            (self.client_sub, "SUBSIDIARY_MANAGER"),
            (self.client_auditor, "AUDITOR"),
        ]:
            res_get = client.get(reverse("core:activity_create"))
            self.assertEqual(res_get.status_code, 403, f"Create GET should be 403 for {name}")

            res_post = client.post(reverse("core:activity_create"), data={"code": "HACK"})
            self.assertEqual(res_post.status_code, 403, f"Create POST should be 403 for {name}")

    def test_edit_view_authorized_roles(self):
        res_get = self.client_esg.get(reverse("core:activity_edit", args=[self.act_diesel.id]))
        self.assertEqual(res_get.status_code, 200)

        post_data = {
            "code": "FUEL-DIESEL",
            "name": "Diesel Consumption - Updated Name",
            "category": self.cat_fuel.id,
            "activity_type": "Stationary Combustion",
            "base_unit": self.unit_litre.id,
            "allowed_units": [self.unit_litre.id],
            "scope_classification": ScopeClassification.SCOPE_1,
            "collection_frequency": CollectionFrequency.MONTHLY,
            "status": MasterStatus.ACTIVE,
        }
        res_post = self.client_esg.post(reverse("core:activity_edit", args=[self.act_diesel.id]), data=post_data)
        self.assertEqual(res_post.status_code, 302)
        self.act_diesel.refresh_from_db()
        self.assertEqual(self.act_diesel.name, "Diesel Consumption - Updated Name")
        self.assertEqual(self.act_diesel.updated_by, self.user_esg)

    def test_edit_view_unauthorized_roles_denied(self):
        for client, name in [
            (self.client_site, "SITE_MANAGER"),
            (self.client_sub, "SUBSIDIARY_MANAGER"),
            (self.client_auditor, "AUDITOR"),
        ]:
            res = client.get(reverse("core:activity_edit", args=[self.act_diesel.id]))
            self.assertEqual(res.status_code, 403, f"Edit should be 403 for {name}")

    def test_deactivate_view_authorization(self):
        # 1. GET returns 405 Method Not Allowed (POST only)
        res_get = self.client_operator.get(reverse("core:activity_deactivate", args=[self.act_diesel.id]))
        self.assertEqual(res_get.status_code, 405)

        # 2. Unauthorized roles get 403 Forbidden
        for client, name in [
            (self.client_site, "SITE_MANAGER"),
            (self.client_sub, "SUBSIDIARY_MANAGER"),
            (self.client_auditor, "AUDITOR"),
        ]:
            res = client.post(reverse("core:activity_deactivate", args=[self.act_diesel.id]))
            self.assertEqual(res.status_code, 403, f"Deactivate should be 403 for {name}")

        # 3. Authorized MEIL_OPERATOR deactivates
        res_post = self.client_operator.post(reverse("core:activity_deactivate", args=[self.act_diesel.id]))
        self.assertEqual(res_post.status_code, 302)
        self.act_diesel.refresh_from_db()
        self.assertEqual(self.act_diesel.status, MasterStatus.INACTIVE)

        # 4. Calling again toggles status back to ACTIVE
        res_toggle = self.client_operator.post(reverse("core:activity_deactivate", args=[self.act_diesel.id]))
        self.assertEqual(res_toggle.status_code, 302)
        self.act_diesel.refresh_from_db()
        self.assertEqual(self.act_diesel.status, MasterStatus.ACTIVE)


class ActivityMasterIDORAndSecurityTests(BaseActivityMasterTestCase):
    """Tests IDOR, direct object manipulation, and tampering defenses."""

    def setUp(self):
        super().setUp()
        self.client_operator = Client()
        self.client_operator.force_login(self.user_operator)

        self.client_site = Client()
        self.client_site.force_login(self.user_site)

    def test_nonexistent_activity_returns_404(self):
        # Non-existent ID returns 404 Not Found
        res_detail = self.client_operator.get(reverse("core:activity_detail", args=[99999]))
        self.assertEqual(res_detail.status_code, 404)

        res_edit = self.client_operator.get(reverse("core:activity_edit", args=[99999]))
        self.assertEqual(res_edit.status_code, 404)

        res_deact = self.client_operator.post(reverse("core:activity_deactivate", args=[99999]))
        self.assertEqual(res_deact.status_code, 404)

    def test_deactivated_activity_inaccessible_to_site_manager(self):
        """Site Manager attempting to access an inactive master activity URL gets 403 Forbidden."""
        self.act_diesel.status = MasterStatus.INACTIVE
        self.act_diesel.is_active = False
        self.act_diesel.save()

        res_site = self.client_site.get(reverse("core:activity_detail", args=[self.act_diesel.id]))
        self.assertEqual(res_site.status_code, 403)

        # Audit log tracks the unauthorized access attempt
        audit = AuthAuditLog.objects.filter(
            user=self.user_site,
            event_type=AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
        ).first()
        self.assertIsNotNone(audit)

        # Master admin can still view it
        res_admin = self.client_operator.get(reverse("core:activity_detail", args=[self.act_diesel.id]))
        self.assertEqual(res_admin.status_code, 200)

    def test_category_and_unit_views_security(self):
        # List view is accessible
        res_cat = self.client_site.get(reverse("core:category_list"))
        self.assertEqual(res_cat.status_code, 200)

        res_units = self.client_site.get(reverse("core:unit_list"))
        self.assertEqual(res_units.status_code, 200)

        # Creation endpoints are protected
        res_create_cat = self.client_site.get(reverse("core:category_create"))
        self.assertEqual(res_create_cat.status_code, 403)

        res_create_unit = self.client_site.get(reverse("core:unit_create"))
        self.assertEqual(res_create_unit.status_code, 403)
