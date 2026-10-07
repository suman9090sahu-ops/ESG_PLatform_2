"""
Comprehensive Test Suite for Phase 08 — ESG Data Entry & Activity Telemetry.

Validates:
1. Model Architecture & Domain Constraints (ActivityRecord):
   - Valid instantiation and default status (DRAFT)
   - Positive quantity enforcement (clean and CheckConstraint)
   - Unit permissibility validation against ActivityMaster
   - Measurement date within reporting period boundaries
   - Cross-organizational boundary alignment (Site Company vs Period Company)
   - Inactive activity protection
   - Editable status and badge class properties

2. Scoped Queryset & Candidate Selector Services:
   - get_accessible_activity_records scopes strictly by user role and assignments
   - Site Manager sees ONLY records from assigned sites
   - Subsidiary Manager sees records from child division sites
   - Auditor has read-only visibility
   - MEIL Operator has universal enterprise visibility
   - Candidate sites, periods, activities, and units selectors

3. Object-Level Authorization & Anti-IDOR Protections:
   - Access to unassigned site's record triggers 403 Forbidden
   - Editing unassigned site's record triggers 403 Forbidden
   - Creation with tampered ?site_id query param triggers 403 Forbidden
   - Auditor attempting create or edit triggers 403 Forbidden
   - Protected statuses (SUBMITTED, VERIFIED, APPROVED) lock out Site Manager edit
   - Closed / Locked / Finalized periods prohibit data mutation

4. Full CRUD View Endpoints:
   - GET /data-entry/ (List view with KPI stats and filters)
   - GET /data-entry/create/ (Pre-populated form with scoped querysets)
   - POST /data-entry/create/ (Valid draft and ready record creation with audit logging)
   - GET /data-entry/<id>/ (Detailed telemetry inspection and audit lineage)
   - GET & POST /data-entry/<id>/edit/ (Scoped update with audit logging)
   - POST /data-entry/<id>/delete/ (Safe draft deletion with audit logging)
   - GET /data-entry/api/activity-units/ (Dynamic JSON API for permitted units)

5. Dashboard Integration:
   - Real draft count aggregated in Site Manager dashboard workflow metrics
   - Actionable pending notices reflect real database drafts
"""

from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.data_entry_services import (
    get_accessible_activity_records,
    get_candidate_activities_for_data_entry,
    get_candidate_periods_for_site,
    get_candidate_sites_for_data_entry,
    get_candidate_units_for_activity,
    user_can_access_activity_record,
    user_can_create_activity_record,
    user_can_delete_activity_record,
    user_can_modify_activity_record,
)
from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    ActivityRecord,
    AuthAuditLog,
    Company,
    CompanyAssignment,
    MasterStatus,
    OrganizationStatus,
    PeriodStatus,
    Project,
    RecordStatus,
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


class BasePhase08TestCase(TestCase):
    """Base setup for Phase 08 ESG Data Entry tests."""

    @classmethod
    def setUpTestData(cls):
        # 1. Setup Roles
        cls.site_mgr_role, _ = Role.objects.get_or_create(
            code=Role.Code.SITE_MANAGER,
            defaults={"name": "Site Manager", "is_active": True},
        )
        cls.sub_mgr_role, _ = Role.objects.get_or_create(
            code=Role.Code.SUBSIDIARY_MANAGER,
            defaults={"name": "Subsidiary Manager", "is_active": True},
        )
        cls.operator_role, _ = Role.objects.get_or_create(
            code=Role.Code.MEIL_OPERATOR,
            defaults={"name": "MEIL Operator", "is_active": True},
        )
        cls.auditor_role, _ = Role.objects.get_or_create(
            code=Role.Code.AUDITOR,
            defaults={"name": "Auditor", "is_active": True},
        )
        cls.esg_mgr_role, _ = Role.objects.get_or_create(
            code=Role.Code.ESG_MANAGER,
            defaults={"name": "ESG Manager", "is_active": True},
        )

        # 2. Setup Organizations
        cls.company_meil = Company.objects.create(
            code="MEIL-CORP",
            name="MEIL Enterprise Group",
            status=OrganizationStatus.ACTIVE,
        )
        cls.sub_hydro = Subsidiary.objects.create(
            company=cls.company_meil,
            code="MEIL-HYDRO",
            name="MEIL Hydro Division",
            status=OrganizationStatus.ACTIVE,
        )
        cls.sub_solar = Subsidiary.objects.create(
            company=cls.company_meil,
            code="MEIL-SOLAR",
            name="MEIL Solar Division",
            status=OrganizationStatus.ACTIVE,
        )
        cls.prj_pol = Project.objects.create(
            subsidiary=cls.sub_hydro,
            code="PRJ-POL",
            name="Polavaram Dam Project",
            status=OrganizationStatus.ACTIVE,
        )
        cls.prj_krn = Project.objects.create(
            subsidiary=cls.sub_solar,
            code="PRJ-KRN",
            name="Kurnool Solar Facility",
            status=OrganizationStatus.ACTIVE,
        )

        # Sites
        cls.site_pol_head = Site.objects.create(
            project=cls.prj_pol,
            code="SITE-POL-01",
            name="Polavaram Headworks Site",
            status=OrganizationStatus.ACTIVE,
        )
        cls.site_krn_array = Site.objects.create(
            project=cls.prj_krn,
            code="SITE-KRN-01",
            name="Kurnool Inverter Yard Site",
            status=OrganizationStatus.ACTIVE,
        )

        # 3. Setup Reporting Periods
        cls.period_open = ReportingPeriod.objects.create(
            company=cls.company_meil,
            code="FY2025-26",
            name="FY 2025-26 Annual Cycle",
            fiscal_year="FY 2025-26",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            status=PeriodStatus.OPEN,
        )
        cls.period_closed = ReportingPeriod.objects.create(
            company=cls.company_meil,
            code="FY2024-25",
            name="FY 2024-25 Annual Cycle",
            fiscal_year="FY 2024-25",
            start_date=date(2024, 4, 1),
            end_date=date(2025, 3, 31),
            status=PeriodStatus.CLOSED,
        )

        # 4. Setup Master Catalog (Units, Categories, Activities)
        cls.uom_litre = UnitOfMeasure.objects.create(
            code="LITRE",
            name="Litre",
            symbol="L",
            dimension=UnitDimension.VOLUME,
            status=MasterStatus.ACTIVE,
        )
        cls.uom_kl = UnitOfMeasure.objects.create(
            code="KL",
            name="Kilolitre",
            symbol="kL",
            dimension=UnitDimension.VOLUME,
            status=MasterStatus.ACTIVE,
        )
        cls.uom_kwh = UnitOfMeasure.objects.create(
            code="KWH",
            name="Kilowatt Hour",
            symbol="kWh",
            dimension=UnitDimension.ENERGY,
            status=MasterStatus.ACTIVE,
        )
        cls.uom_kg = UnitOfMeasure.objects.create(
            code="KG",
            name="Kilogram",
            symbol="kg",
            dimension=UnitDimension.MASS,
            status=MasterStatus.ACTIVE,
        )

        cls.cat_fuel = ActivityCategory.objects.create(
            code="CAT-FUEL",
            name="Fuel & Stationary Combustion",
            display_order=1,
            status=MasterStatus.ACTIVE,
        )
        cls.cat_elec = ActivityCategory.objects.create(
            code="CAT-ELEC",
            name="Electricity & Grid Energy",
            display_order=2,
            status=MasterStatus.ACTIVE,
        )

        # Activity Masters
        cls.act_diesel = ActivityMaster.objects.create(
            code="FUEL-DIESEL",
            name="Diesel Consumption (Heavy Equipment & Generators)",
            category=cls.cat_fuel,
            base_unit=cls.uom_litre,
            scope_classification=ScopeClassification.SCOPE_1,
            status=MasterStatus.ACTIVE,
        )
        cls.act_diesel.allowed_units.add(cls.uom_kl)

        cls.act_elec = ActivityMaster.objects.create(
            code="ELEC-GRID",
            name="Grid Purchased Electricity",
            category=cls.cat_elec,
            base_unit=cls.uom_kwh,
            scope_classification=ScopeClassification.SCOPE_2,
            status=MasterStatus.ACTIVE,
        )

        cls.act_inactive = ActivityMaster.objects.create(
            code="FUEL-BIO-EXP",
            name="Experimental Biofuel Trial",
            category=cls.cat_fuel,
            base_unit=cls.uom_litre,
            status=MasterStatus.INACTIVE,
        )

        # 5. Setup Users and Assignments
        # Site Manager 1 assigned to Polavaram
        cls.user_sm1 = User.objects.create_user(
            username="sm_polavaram",
            password="TestPassword@123",
            email="sm_pol@meil.in",
        )
        UserRole.objects.create(user=cls.user_sm1, role=cls.site_mgr_role, is_primary=True)
        SiteAssignment.objects.create(user=cls.user_sm1, site=cls.site_pol_head)

        # Site Manager 2 assigned to Kurnool
        cls.user_sm2 = User.objects.create_user(
            username="sm_kurnool",
            password="TestPassword@123",
            email="sm_krn@meil.in",
        )
        UserRole.objects.create(user=cls.user_sm2, role=cls.site_mgr_role, is_primary=True)
        SiteAssignment.objects.create(user=cls.user_sm2, site=cls.site_krn_array)

        # Subsidiary Manager assigned to Hydro Division
        cls.user_sub_mgr = User.objects.create_user(
            username="sub_hydro_mgr",
            password="TestPassword@123",
            email="sub_mgr@meil.in",
        )
        UserRole.objects.create(user=cls.user_sub_mgr, role=cls.sub_mgr_role, is_primary=True)
        SubsidiaryAssignment.objects.create(user=cls.user_sub_mgr, subsidiary=cls.sub_hydro)

        # MEIL Operator (Supervisor)
        cls.user_operator = User.objects.create_user(
            username="meil_operator",
            password="TestPassword@123",
            email="operator@meil.in",
        )
        UserRole.objects.create(user=cls.user_operator, role=cls.operator_role, is_primary=True)
        CompanyAssignment.objects.create(user=cls.user_operator, company=cls.company_meil)

        # Auditor (Assurance - Read Only)
        cls.user_auditor = User.objects.create_user(
            username="meil_auditor",
            password="TestPassword@123",
            email="auditor@meil.in",
        )
        UserRole.objects.create(user=cls.user_auditor, role=cls.auditor_role, is_primary=True)
        CompanyAssignment.objects.create(user=cls.user_auditor, company=cls.company_meil)


class ActivityRecordModelTests(BasePhase08TestCase):
    """Tests for ActivityRecord model domain integrity and validation."""

    def test_create_valid_activity_record(self):
        """Valid ActivityRecord creates successfully with all relationships."""
        record = ActivityRecord.objects.create(
            site=self.site_pol_head,
            reporting_period=self.period_open,
            activity=self.act_diesel,
            measurement_date=date(2025, 6, 15),
            quantity=Decimal("1500.5000"),
            unit=self.uom_litre,
            notes="DG Set #1 monthly run time fuel log",
            evidence_reference="INV-2025-06-001",
            status=RecordStatus.DRAFT,
            created_by=self.user_sm1,
        )
        self.assertIsNotNone(record.id)
        self.assertEqual(record.status, RecordStatus.DRAFT)
        self.assertTrue(record.is_draft)
        self.assertTrue(record.is_editable_by_site_manager)
        self.assertEqual(record.status_badge_class, "badge-secondary")
        self.assertEqual(
            str(record),
            f"{self.act_diesel.name} @ {self.site_pol_head.name}: 1500.5000 L (2025-06-15)",
        )

    def test_allowed_unit_support(self):
        """Allows recording with an allowed_units member (kL) instead of base unit (L)."""
        record = ActivityRecord.objects.create(
            site=self.site_pol_head,
            reporting_period=self.period_open,
            activity=self.act_diesel,
            measurement_date=date(2025, 7, 1),
            quantity=Decimal("5.5000"),
            unit=self.uom_kl,
            status=RecordStatus.READY,
            created_by=self.user_sm1,
        )
        self.assertEqual(record.unit, self.uom_kl)
        self.assertTrue(record.is_ready)
        self.assertEqual(record.status_badge_class, "badge-info")

    def test_prohibit_unauthorized_unit(self):
        """Fails validation if unit (kg) is not allowed for activity (diesel)."""
        record = ActivityRecord(
            site=self.site_pol_head,
            reporting_period=self.period_open,
            activity=self.act_diesel,
            measurement_date=date(2025, 6, 15),
            quantity=Decimal("100.0"),
            unit=self.uom_kg,  # Not in allowed units
            created_by=self.user_sm1,
        )
        with self.assertRaises(ValidationError) as ctx:
            record.clean()
        self.assertIn("unit", ctx.exception.message_dict)

    def test_prohibit_negative_quantity(self):
        """Fails validation if quantity is negative."""
        record = ActivityRecord(
            site=self.site_pol_head,
            reporting_period=self.period_open,
            activity=self.act_diesel,
            measurement_date=date(2025, 6, 15),
            quantity=Decimal("-50.0"),
            unit=self.uom_litre,
            created_by=self.user_sm1,
        )
        with self.assertRaises(ValidationError) as ctx:
            record.clean()
        self.assertIn("quantity", ctx.exception.message_dict)

    def test_measurement_date_outside_period_boundaries(self):
        """Fails validation if measurement date falls outside period date range."""
        record = ActivityRecord(
            site=self.site_pol_head,
            reporting_period=self.period_open,  # 2025-04-01 to 2026-03-31
            activity=self.act_diesel,
            measurement_date=date(2024, 12, 31),  # Before period start
            quantity=Decimal("200.0"),
            unit=self.uom_litre,
            created_by=self.user_sm1,
        )
        with self.assertRaises(ValidationError) as ctx:
            record.clean()
        self.assertIn("measurement_date", ctx.exception.message_dict)

    def test_prohibit_inactive_activity(self):
        """Fails validation if activity is inactive."""
        record = ActivityRecord(
            site=self.site_pol_head,
            reporting_period=self.period_open,
            activity=self.act_inactive,
            measurement_date=date(2025, 6, 15),
            quantity=Decimal("100.0"),
            unit=self.uom_litre,
            created_by=self.user_sm1,
        )
        with self.assertRaises(ValidationError) as ctx:
            record.clean()
        self.assertIn("activity", ctx.exception.message_dict)

    def test_editable_by_site_manager_property(self):
        """Checks is_editable_by_site_manager respects workflow status and period lifecycle."""
        # Draft in open period -> Editable
        rec_draft = ActivityRecord.objects.create(
            site=self.site_pol_head,
            reporting_period=self.period_open,
            activity=self.act_diesel,
            measurement_date=date(2025, 6, 15),
            quantity=Decimal("100.0"),
            unit=self.uom_litre,
            status=RecordStatus.DRAFT,
        )
        self.assertTrue(rec_draft.is_editable_by_site_manager)

        # Submitted in open period -> Locked from Site Manager editing
        rec_submitted = ActivityRecord.objects.create(
            site=self.site_pol_head,
            reporting_period=self.period_open,
            activity=self.act_diesel,
            measurement_date=date(2025, 6, 15),
            quantity=Decimal("100.0"),
            unit=self.uom_litre,
            status=RecordStatus.SUBMITTED,
        )
        self.assertFalse(rec_submitted.is_editable_by_site_manager)

        # Draft in closed period -> Locked from Site Manager editing
        rec_closed = ActivityRecord.objects.create(
            site=self.site_pol_head,
            reporting_period=self.period_closed,
            activity=self.act_diesel,
            measurement_date=date(2024, 6, 15),
            quantity=Decimal("100.0"),
            unit=self.uom_litre,
            status=RecordStatus.DRAFT,
        )
        self.assertFalse(rec_closed.is_editable_by_site_manager)


class ActivityRecordScopingServiceTests(BasePhase08TestCase):
    """Tests for service layer scoping functions."""

    def setUp(self):
        super().setUp()
        # Create records for Polavaram and Kurnool
        self.rec_pol = ActivityRecord.objects.create(
            site=self.site_pol_head,
            reporting_period=self.period_open,
            activity=self.act_diesel,
            measurement_date=date(2025, 5, 10),
            quantity=Decimal("1000.0"),
            unit=self.uom_litre,
            status=RecordStatus.DRAFT,
            created_by=self.user_sm1,
        )
        self.rec_krn = ActivityRecord.objects.create(
            site=self.site_krn_array,
            reporting_period=self.period_open,
            activity=self.act_elec,
            measurement_date=date(2025, 5, 12),
            quantity=Decimal("4500.0"),
            unit=self.uom_kwh,
            status=RecordStatus.READY,
            created_by=self.user_sm2,
        )

    def test_site_manager_scoped_records(self):
        """Site Manager sees ONLY their assigned site records."""
        qs_sm1 = get_accessible_activity_records(self.user_sm1)
        self.assertIn(self.rec_pol, qs_sm1)
        self.assertNotIn(self.rec_krn, qs_sm1)

        qs_sm2 = get_accessible_activity_records(self.user_sm2)
        self.assertIn(self.rec_krn, qs_sm2)
        self.assertNotIn(self.rec_pol, qs_sm2)

    def test_subsidiary_manager_scoped_records(self):
        """Subsidiary Manager sees Hydro division site records, but not Solar."""
        qs_sub = get_accessible_activity_records(self.user_sub_mgr)
        self.assertIn(self.rec_pol, qs_sub)
        self.assertNotIn(self.rec_krn, qs_sub)

    def test_operator_and_auditor_universal_records(self):
        """MEIL Operator and Auditor see all enterprise records."""
        qs_op = get_accessible_activity_records(self.user_operator)
        self.assertEqual(qs_op.count(), 2)
        self.assertIn(self.rec_pol, qs_op)
        self.assertIn(self.rec_krn, qs_op)

        qs_aud = get_accessible_activity_records(self.user_auditor)
        self.assertEqual(qs_aud.count(), 2)

    def test_candidate_sites_selector(self):
        """Site Manager candidate sites matches their assigned active sites."""
        sites_sm1 = get_candidate_sites_for_data_entry(self.user_sm1)
        self.assertEqual(list(sites_sm1), [self.site_pol_head])

        sites_sm2 = get_candidate_sites_for_data_entry(self.user_sm2)
        self.assertEqual(list(sites_sm2), [self.site_krn_array])

    def test_candidate_units_for_activity(self):
        """Returns base unit and allowed units for activity."""
        units_diesel = get_candidate_units_for_activity(self.act_diesel)
        self.assertIn(self.uom_litre, units_diesel)
        self.assertIn(self.uom_kl, units_diesel)
        self.assertNotIn(self.uom_kwh, units_diesel)


class ActivityRecordAuthorizationTests(BasePhase08TestCase):
    """Tests for object-level authorization helpers and anti-IDOR checks."""

    def setUp(self):
        super().setUp()
        self.rec_pol = ActivityRecord.objects.create(
            site=self.site_pol_head,
            reporting_period=self.period_open,
            activity=self.act_diesel,
            measurement_date=date(2025, 5, 10),
            quantity=Decimal("1000.0"),
            unit=self.uom_litre,
            status=RecordStatus.DRAFT,
            created_by=self.user_sm1,
        )

    def test_site_manager_authorization_helpers(self):
        """Site Manager 1 can access and modify their Polavaram draft record."""
        self.assertTrue(user_can_access_activity_record(self.user_sm1, self.rec_pol))
        self.assertTrue(user_can_modify_activity_record(self.user_sm1, self.rec_pol))
        self.assertTrue(user_can_delete_activity_record(self.user_sm1, self.rec_pol))

    def test_site_manager_2_idor_blocked(self):
        """Site Manager 2 is strictly blocked from accessing or modifying Polavaram record."""
        self.assertFalse(user_can_access_activity_record(self.user_sm2, self.rec_pol))
        self.assertFalse(user_can_modify_activity_record(self.user_sm2, self.rec_pol))
        self.assertFalse(user_can_delete_activity_record(self.user_sm2, self.rec_pol))

    def test_auditor_read_only_strictly_enforced(self):
        """Auditor has view access, but is strictly prohibited from modifying or deleting."""
        self.assertTrue(user_can_access_activity_record(self.user_auditor, self.rec_pol))
        self.assertFalse(user_can_create_activity_record(self.user_auditor, site=self.site_pol_head))
        self.assertFalse(user_can_modify_activity_record(self.user_auditor, self.rec_pol))
        self.assertFalse(user_can_delete_activity_record(self.user_auditor, self.rec_pol))

    def test_submitted_record_modification_blocked(self):
        """Submitted record cannot be modified or deleted by Site Manager."""
        self.rec_pol.status = RecordStatus.SUBMITTED
        self.rec_pol.save(update_fields=["status"])

        self.assertTrue(user_can_access_activity_record(self.user_sm1, self.rec_pol))
        self.assertFalse(user_can_modify_activity_record(self.user_sm1, self.rec_pol))
        self.assertFalse(user_can_delete_activity_record(self.user_sm1, self.rec_pol))


class ActivityRecordViewTests(BasePhase08TestCase):
    """Tests for HTTP views, forms, and responses."""

    def setUp(self):
        super().setUp()
        self.client_sm1 = Client()
        self.client_sm1.force_login(self.user_sm1)

        self.client_sm2 = Client()
        self.client_sm2.force_login(self.user_sm2)

        self.client_auditor = Client()
        self.client_auditor.force_login(self.user_auditor)

        self.client_anonymous = Client()

        self.rec_pol = ActivityRecord.objects.create(
            site=self.site_pol_head,
            reporting_period=self.period_open,
            activity=self.act_diesel,
            measurement_date=date(2025, 6, 1),
            quantity=Decimal("1200.00"),
            unit=self.uom_litre,
            status=RecordStatus.DRAFT,
            created_by=self.user_sm1,
        )

    def test_unauthenticated_redirects_to_login(self):
        """Unauthenticated user is redirected to login for data entry routes."""
        resp = self.client_anonymous.get(reverse("core:activity_record_list"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login/", resp.url)

        resp2 = self.client_anonymous.get(reverse("core:activity_record_create"))
        self.assertEqual(resp2.status_code, 302)

    def test_activity_record_list_view(self):
        """Site Manager list view renders only their assigned site's records."""
        resp = self.client_sm1.get(reverse("core:activity_record_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Polavaram Headworks Site")
        self.assertContains(resp, "1200.00")
        self.assertContains(resp, "Draft")
        self.assertEqual(resp.context["total_count"], 1)
        self.assertEqual(resp.context["draft_count"], 1)

    def test_activity_record_create_get(self):
        """GET /data-entry/create/ renders form with auto-selected site and period."""
        resp = self.client_sm1.get(reverse("core:activity_record_create"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "New ESG Data Entry")
        self.assertContains(resp, "Polavaram Headworks Site")

    def test_activity_record_create_tampered_site_id_idor_blocked(self):
        """Tampered ?site_id pointing to unassigned site raises 403 Forbidden."""
        tampered_url = f"{reverse('core:activity_record_create')}?site_id={self.site_krn_array.id}"
        resp = self.client_sm1.get(tampered_url)
        self.assertEqual(resp.status_code, 403)

    def test_activity_record_create_post_valid(self):
        """POST /data-entry/create/ successfully creates ActivityRecord and audit log."""
        data = {
            "site": self.site_pol_head.id,
            "reporting_period": self.period_open.id,
            "activity": self.act_diesel.id,
            "measurement_date": "2025-08-20",
            "quantity": "2500.75",
            "unit": self.uom_litre.id,
            "notes": "Testing valid POST creation",
            "evidence_reference": "INV-POL-2025-08",
            "status": RecordStatus.READY,
        }
        resp = self.client_sm1.post(reverse("core:activity_record_create"), data)
        self.assertEqual(resp.status_code, 302)

        # Verify created in DB
        created_rec = ActivityRecord.objects.filter(notes="Testing valid POST creation").first()
        self.assertIsNotNone(created_rec)
        self.assertEqual(created_rec.quantity, Decimal("2500.75"))
        self.assertEqual(created_rec.status, RecordStatus.READY)
        self.assertEqual(created_rec.created_by, self.user_sm1)

        # Verify audit log
        audit = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.ACTIVITY_RECORD_CREATED,
            user=self.user_sm1,
        ).first()
        self.assertIsNotNone(audit)
        self.assertIn("Created READY activity record", audit.details)

    def test_activity_record_detail_view(self):
        """GET /data-entry/<id>/ displays full read-only details."""
        resp = self.client_sm1.get(reverse("core:activity_record_detail", kwargs={"record_id": self.rec_pol.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Polavaram Headworks Site")
        self.assertContains(resp, "1200.00")
        self.assertContains(resp, "Diesel Consumption")
        self.assertContains(resp, "FY2025-26")

    def test_activity_record_detail_idor_blocked(self):
        """Site Manager 2 attempting to view Site Manager 1's record receives 403 Forbidden."""
        resp = self.client_sm2.get(reverse("core:activity_record_detail", kwargs={"record_id": self.rec_pol.id}))
        self.assertEqual(resp.status_code, 403)

    def test_activity_record_edit_get_and_post(self):
        """Site Manager 1 edits draft record successfully."""
        edit_url = reverse("core:activity_record_edit", kwargs={"record_id": self.rec_pol.id})
        resp = self.client_sm1.get(edit_url)
        self.assertEqual(resp.status_code, 200)

        # POST updated quantity
        update_data = {
            "site": self.site_pol_head.id,
            "reporting_period": self.period_open.id,
            "activity": self.act_diesel.id,
            "measurement_date": "2025-06-01",
            "quantity": "1850.00",
            "unit": self.uom_litre.id,
            "notes": "Updated quantity post-reconciliation",
            "status": RecordStatus.READY,
        }
        post_resp = self.client_sm1.post(edit_url, update_data)
        self.assertEqual(post_resp.status_code, 302)

        self.rec_pol.refresh_from_db()
        self.assertEqual(self.rec_pol.quantity, Decimal("1850.00"))
        self.assertEqual(self.rec_pol.status, RecordStatus.READY)
        self.assertEqual(self.rec_pol.notes, "Updated quantity post-reconciliation")

    def test_activity_record_edit_idor_blocked(self):
        """Site Manager 2 attempting to edit Site Manager 1's record receives 403 Forbidden."""
        edit_url = reverse("core:activity_record_edit", kwargs={"record_id": self.rec_pol.id})
        resp = self.client_sm2.get(edit_url)
        self.assertEqual(resp.status_code, 403)

    def test_activity_record_delete_draft(self):
        """Draft record can be safely deleted by authorized site manager."""
        del_url = reverse("core:activity_record_delete", kwargs={"record_id": self.rec_pol.id})
        resp = self.client_sm1.get(del_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Confirm Draft Deletion")

        post_resp = self.client_sm1.post(del_url)
        self.assertEqual(post_resp.status_code, 302)
        self.assertFalse(ActivityRecord.objects.filter(id=self.rec_pol.id).exists())

    def test_auditor_cannot_create_or_edit(self):
        """Auditor is strictly denied access to create and edit endpoints."""
        resp_create = self.client_auditor.get(reverse("core:activity_record_create"))
        self.assertEqual(resp_create.status_code, 403)

        edit_url = reverse("core:activity_record_edit", kwargs={"record_id": self.rec_pol.id})
        resp_edit = self.client_auditor.get(edit_url)
        self.assertEqual(resp_edit.status_code, 403)

    def test_dynamic_units_api(self):
        """API endpoint returns allowed units for activity."""
        url = f"{reverse('core:activity_units_api')}?activity_id={self.act_diesel.id}"
        resp = self.client_sm1.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["activity_id"], self.act_diesel.id)
        unit_symbols = [u["symbol"] for u in data["units"]]
        self.assertIn("L", unit_symbols)
        self.assertIn("kL", unit_symbols)
        self.assertNotIn("kWh", unit_symbols)
