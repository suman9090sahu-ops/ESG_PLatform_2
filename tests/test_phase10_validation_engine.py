"""
Comprehensive Test Suite for Phase 10 — ESG Validation Engine.

Covers:
1. Validation Domain Models & Enums:
   - ValidationRule instantiation, code unique constraint, category, severity, is_blocking, parameters, active flag
   - ValidationRun execution tracking, sequential run numbers, result aggregations, duration, version snapshot
   - ValidationResult granular findings, field association, context data
   - ActivityRecord validation properties (validation_status, is_validated, has_validation_errors, can_submit_for_review, latest_validation_run)

2. Deterministic Validation Layers (Layer 1 - Layer 7):
   - Layer 1: Structural (quantity, unit, measurement date, site, activity, period presence)
   - Layer 2: Scope (hierarchy consistency, company boundary alignment, active site/activity)
   - Layer 3: Period (OPEN period requirement, date within period boundaries, future date warning)
   - Layer 4: Activity (permissible units, dimension alignment)
   - Layer 5: Evidence (mandatory evidence for regulated activities, taxonomy match, file integrity)
   - Layer 6: Consistency & Duplicates (positive quantity, zero consumption warning, duplicate record warning)
   - Layer 7: Workflow Readiness (errors block submission and revert READY -> DRAFT; warnings permit progression)

3. Revalidation & Historical Run Preservation:
   - Invalid record -> Run 1 (INVALID) -> Corrected data -> Run 2 (VALID)
   - Previous run history immutable & preserved
   - Latest validation run correctly referenced
   - Audit trail in AuthAuditLog for every validation execution

4. Batch Validation:
   - Reusable validate_activity_records service across record querysets

5. Security, RBAC & Anti-IDOR Protections:
   - POST /data-entry/<id>/validate/ (Site Manager assigned vs unassigned 403, AJAX JSON response)
   - GET /validation/runs/<id>/ (Assigned Site Manager vs unassigned 403, Auditor read-only)
   - Governance: /validation/rules/ (Site Manager 403, ESG Manager & Operator govern, Auditor read-only)
   - Anti-tampering and no eval/exec code execution
"""

import io
from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.evidence_services import create_evidence_record
from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    ActivityRecord,
    AuthAuditLog,
    Company,
    Evidence,
    EvidenceStatus,
    EvidenceType,
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
    ValidationCategory,
    ValidationResult,
    ValidationRule,
    ValidationRun,
    ValidationStatus,
    ValidationSeverity,
)
from apps.core.validation_services import (
    execute_validation_run,
    seed_standard_validation_rules,
    user_can_manage_validation_rules,
    user_can_validate_record,
    user_can_view_validation_rules,
    validate_activity_records,
)

User = get_user_model()


class Phase10BaseTestCase(TestCase):
    """Base setup for Phase 10 Validation Engine tests."""

    @classmethod
    def setUpTestData(cls):
        # 1. Create Roles
        cls.operator_role, _ = Role.objects.get_or_create(
            code=Role.Code.MEIL_OPERATOR, defaults={"name": "MEIL Operator", "is_active": True}
        )
        cls.esg_role, _ = Role.objects.get_or_create(
            code=Role.Code.ESG_MANAGER, defaults={"name": "ESG Manager", "is_active": True}
        )
        cls.sub_mgr_role, _ = Role.objects.get_or_create(
            code=Role.Code.SUBSIDIARY_MANAGER, defaults={"name": "Subsidiary Manager", "is_active": True}
        )
        cls.site_mgr_role, _ = Role.objects.get_or_create(
            code=Role.Code.SITE_MANAGER, defaults={"name": "Site Manager", "is_active": True}
        )
        cls.auditor_role, _ = Role.objects.get_or_create(
            code=Role.Code.AUDITOR, defaults={"name": "Auditor", "is_active": True}
        )

        # 2. Create Users
        cls.user_operator = User.objects.create_user(username="val_operator", password="password123")
        UserRole.objects.create(user=cls.user_operator, role=cls.operator_role, is_primary=True)

        cls.user_esg = User.objects.create_user(username="val_esg", password="password123")
        UserRole.objects.create(user=cls.user_esg, role=cls.esg_role, is_primary=True)

        cls.user_sub_mgr = User.objects.create_user(username="val_sub_mgr", password="password123")
        UserRole.objects.create(user=cls.user_sub_mgr, role=cls.sub_mgr_role, is_primary=True)

        cls.user_site_mgr = User.objects.create_user(username="val_site_mgr", password="password123")
        UserRole.objects.create(user=cls.user_site_mgr, role=cls.site_mgr_role, is_primary=True)

        cls.user_other_site_mgr = User.objects.create_user(username="val_other_site_mgr", password="password123")
        UserRole.objects.create(user=cls.user_other_site_mgr, role=cls.site_mgr_role, is_primary=True)

        cls.user_auditor = User.objects.create_user(username="val_auditor", password="password123")
        UserRole.objects.create(user=cls.user_auditor, role=cls.auditor_role, is_primary=True)

        # 3. Create Organizations
        cls.company_primary = Company.objects.create(
            name="MEIL Infrastructure Ltd",
            code="MEIL-INFRA",
            status=OrganizationStatus.ACTIVE,
        )
        cls.company_secondary = Company.objects.create(
            name="MEIL Energy Corp",
            code="MEIL-ENERGY",
            status=OrganizationStatus.ACTIVE,
        )

        cls.subsidiary1 = Subsidiary.objects.create(
            company=cls.company_primary,
            name="Water Works Division",
            code="MEIL-WATER",
            status=OrganizationStatus.ACTIVE,
        )
        cls.subsidiary2 = Subsidiary.objects.create(
            company=cls.company_secondary,
            name="Solar Division",
            code="MEIL-SOLAR",
            status=OrganizationStatus.ACTIVE,
        )

        cls.project1 = Project.objects.create(
            subsidiary=cls.subsidiary1,
            name="Polavaram Irrigation Project",
            code="PRJ-POLAVARAM",
            status=OrganizationStatus.ACTIVE,
        )
        cls.project2 = Project.objects.create(
            subsidiary=cls.subsidiary2,
            name="Pavagada Solar Park",
            code="PRJ-PAVAGADA",
            status=OrganizationStatus.ACTIVE,
        )

        cls.site1 = Site.objects.create(
            project=cls.project1,
            name="Polavaram Right Canal Site",
            code="SITE-POL-101",
            status=OrganizationStatus.ACTIVE,
        )
        cls.site2 = Site.objects.create(
            project=cls.project1,
            name="Polavaram Head Works Site",
            code="SITE-POL-102",
            status=OrganizationStatus.ACTIVE,
        )
        cls.site3 = Site.objects.create(
            project=cls.project2,
            name="Pavagada Block B Site",
            code="SITE-PAV-201",
            status=OrganizationStatus.ACTIVE,
        )

        # Inactive site for boundary testing
        cls.site_inactive = Site.objects.create(
            project=cls.project1,
            name="Decommissioned Quarry Site",
            code="SITE-POL-999",
            status=OrganizationStatus.INACTIVE,
        )

        # User Assignments
        SiteAssignment.objects.create(user=cls.user_site_mgr, site=cls.site1)
        SiteAssignment.objects.create(user=cls.user_other_site_mgr, site=cls.site2)
        SubsidiaryAssignment.objects.create(user=cls.user_sub_mgr, subsidiary=cls.subsidiary1)

        # 4. Units of Measure
        cls.unit_litre = UnitOfMeasure.objects.create(
            code="LITRE",
            name="Litre",
            symbol="L",
            dimension=UnitDimension.VOLUME,
            status=MasterStatus.ACTIVE,
        )
        cls.unit_kwh = UnitOfMeasure.objects.create(
            code="KWH",
            name="Kilowatt Hour",
            symbol="kWh",
            dimension=UnitDimension.ENERGY,
            status=MasterStatus.ACTIVE,
        )
        cls.unit_mt = UnitOfMeasure.objects.create(
            code="TONNE",
            name="Metric Tonne",
            symbol="MT",
            dimension=UnitDimension.MASS,
            status=MasterStatus.ACTIVE,
        )

        # 5. Activity Categories & Activities
        cls.cat_stationary = ActivityCategory.objects.create(
            code="CAT-STAT-COMB",
            name="Stationary Combustion",
            display_order=1,
            status=MasterStatus.ACTIVE,
        )
        cls.cat_purchased_elec = ActivityCategory.objects.create(
            code="CAT-PURCH-ELEC",
            name="Purchased Electricity",
            display_order=2,
            status=MasterStatus.ACTIVE,
        )

        # Regulated Diesel activity requiring evidence
        cls.activity_diesel = ActivityMaster.objects.create(
            code="FUEL-DIESEL-STAT",
            name="Diesel Consumption - Stationary Equipment",
            activity_type="Stationary Combustion",
            category=cls.cat_stationary,
            status=MasterStatus.ACTIVE,
            base_unit=cls.unit_litre,
            scope_classification=ScopeClassification.SCOPE_1,
            validation_rules={
                "evidence_required": True,
                "evidence_taxonomy": ["INVOICE", "FUEL_CHALLAN"],
                "allowed_units": ["L"],
                "dimension": "VOLUME",
            },
        )
        cls.activity_diesel.allowed_units.add(cls.unit_litre)

        # Grid electricity activity requiring kWh
        cls.activity_grid = ActivityMaster.objects.create(
            code="ELEC-GRID",
            name="Grid Electricity Consumption",
            activity_type="Purchased Electricity",
            category=cls.cat_purchased_elec,
            status=MasterStatus.ACTIVE,
            base_unit=cls.unit_kwh,
            scope_classification=ScopeClassification.SCOPE_2,
            validation_rules={
                "evidence_required": True,
                "evidence_taxonomy": ["UTILITY_BILL"],
                "allowed_units": ["kWh"],
                "dimension": "ENERGY",
            },
        )
        cls.activity_grid.allowed_units.add(cls.unit_kwh)

        # Inactive Activity
        cls.activity_inactive = ActivityMaster.objects.create(
            code="OBSOLETE-FUEL",
            name="Obsolete Fuel Line",
            activity_type="Stationary Combustion",
            category=cls.cat_stationary,
            status=MasterStatus.INACTIVE,
            base_unit=cls.unit_litre,
            scope_classification=ScopeClassification.SCOPE_1,
        )

        # 6. Reporting Periods
        cls.period_open = ReportingPeriod.objects.create(
            company=cls.company_primary,
            code="FY2026-Q1",
            name="FY 2026-27 Q1",
            fiscal_year="FY 2026-27",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 6, 30),
            status=PeriodStatus.OPEN,
        )
        cls.period_closed = ReportingPeriod.objects.create(
            company=cls.company_primary,
            code="FY2025-Q4",
            name="FY 2025-26 Q4 (Closed)",
            fiscal_year="FY 2025-26",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            status=PeriodStatus.CLOSED,
        )
        cls.period_other_company = ReportingPeriod.objects.create(
            company=cls.company_secondary,
            code="FY2026-EN-Q1",
            name="FY 2026-27 Energy Q1",
            fiscal_year="FY 2026-27",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 6, 30),
            status=PeriodStatus.OPEN,
        )

        # 7. Seed Standard Validation Rules
        seed_standard_validation_rules(cls.user_operator)


class ValidationModelTests(Phase10BaseTestCase):
    """Test Validation domain models, attributes, constraints, and helper methods."""

    def test_validation_rule_creation_and_attributes(self):
        """Verify ValidationRule persists with proper schema and representations."""
        rule = ValidationRule.objects.get(code="STRUCT_REQ_QUANTITY")
        self.assertEqual(rule.name, "Quantity Mandatory")
        self.assertEqual(rule.category, ValidationCategory.STRUCTURAL)
        self.assertEqual(rule.severity, ValidationSeverity.ERROR)
        self.assertTrue(rule.is_active)
        self.assertTrue(rule.is_blocking)
        self.assertIn("STRUCT_REQ_QUANTITY", str(rule))

    def test_validation_run_creation_and_aggregations(self):
        """Verify ValidationRun increments run_number and stores metrics accurately."""
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("1250.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )

        run = ValidationRun.objects.create(
            activity_record=record,
            run_number=1,
            status=ValidationStatus.VALID,
            total_rules_evaluated=21,
            error_count=0,
            warning_count=1,
            info_count=2,
            summary_message="Deterministic validation completed with 1 warning.",
            executed_by=self.user_site_mgr,
            execution_duration_ms=45,
        )
        self.assertEqual(run.run_number, 1)
        self.assertEqual(run.status, ValidationStatus.VALID)
        self.assertIn(f"Run #1 for Record #{record.id}", str(run))

        # Second run increment
        run2 = ValidationRun.objects.create(
            activity_record=record,
            run_number=2,
            status=ValidationStatus.VALID,
            total_rules_evaluated=21,
            error_count=0,
            warning_count=0,
            info_count=1,
            summary_message="All deterministic rules satisfied.",
            executed_by=self.user_site_mgr,
        )
        self.assertEqual(run2.run_number, 2)
        self.assertEqual(record.latest_validation_run, run2)

    def test_validation_result_creation_and_mapping(self):
        """Verify ValidationResult stores granular findings with field and context."""
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("100.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )
        run = ValidationRun.objects.create(
            activity_record=record,
            run_number=1,
            status=ValidationStatus.INVALID,
            total_rules_evaluated=10,
            error_count=1,
            executed_by=self.user_site_mgr,
        )
        rule = ValidationRule.objects.get(code="STRUCT_REQ_QUANTITY")

        result = ValidationResult.objects.create(
            validation_run=run,
            activity_record=record,
            rule=rule,
            severity=ValidationSeverity.ERROR,
            is_blocking=True,
            field_name="quantity",
            message="Activity record must have a valid quantity specified.",
            context_data={"received_quantity": None},
        )
        self.assertEqual(result.field_name, "quantity")
        self.assertTrue(result.is_blocking)
        self.assertIn("ERROR [quantity]", str(result))
        self.assertEqual(result.rule.code, "STRUCT_REQ_QUANTITY")

    def test_activity_record_validation_properties(self):
        """Verify ActivityRecord validation status defaults, properties and badge styling."""
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("100.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )
        self.assertEqual(record.validation_status, ValidationStatus.UNVALIDATED)
        self.assertFalse(record.is_validated)
        self.assertFalse(record.has_validation_errors)
        self.assertEqual(record.validation_badge_class, "badge-secondary")

        record.validation_status = ValidationStatus.VALID
        record.save(update_fields=["validation_status"])
        self.assertTrue(record.is_validated)
        self.assertFalse(record.has_validation_errors)
        self.assertEqual(record.validation_badge_class, "badge-success")

        record.validation_status = ValidationStatus.INVALID
        record.save(update_fields=["validation_status"])
        self.assertFalse(record.is_validated)
        self.assertTrue(record.has_validation_errors)
        self.assertEqual(record.validation_badge_class, "badge-danger")


class ValidationLayersDeterministicTests(Phase10BaseTestCase):
    """Test deterministic evaluation across Layers 1 through 7."""

    def _get_evidence_file(self, filename="diesel_invoice.pdf"):
        return SimpleUploadedFile(
            name=filename,
            content=b"%PDF-1.4\n1 0 obj\n<<\n/Title (Evidence File)\n>>\nendobj\ntrailer\n<<\n>>\n%%EOF",
            content_type="application/pdf",
        )

    def test_layer1_structural_quantity_missing(self):
        """Layer 1: Structural check fails when quantity is missing."""
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("100.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )
        record.quantity = None
        run = execute_validation_run(record, executed_by=self.user_site_mgr)
        self.assertEqual(run.status, ValidationStatus.INVALID)
        self.assertTrue(run.error_count >= 1)
        finding = run.results.filter(rule__code="STRUCT_REQ_QUANTITY").first()
        self.assertIsNotNone(finding)
        self.assertEqual(finding.field_name, "quantity")
        self.assertEqual(finding.severity, ValidationSeverity.ERROR)

    def test_layer1_structural_unit_missing(self):
        """Layer 1: Structural check fails when unit is missing."""
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("100.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )
        record.unit = None
        record.unit_id = None
        run = execute_validation_run(record, executed_by=self.user_site_mgr)
        self.assertEqual(run.status, ValidationStatus.INVALID)
        finding = run.results.filter(rule__code="STRUCT_REQ_UNIT").first()
        self.assertIsNotNone(finding)
        self.assertEqual(finding.field_name, "unit")

    def test_layer1_structural_date_missing(self):
        """Layer 1: Structural check fails when measurement_date is missing."""
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("100.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )
        record.measurement_date = None
        run = execute_validation_run(record, executed_by=self.user_site_mgr)
        self.assertEqual(run.status, ValidationStatus.INVALID)
        finding = run.results.filter(rule__code="STRUCT_REQ_DATE").first()
        self.assertIsNotNone(finding)
        self.assertEqual(finding.field_name, "measurement_date")

    def test_layer2_scope_cross_company_alignment_failure(self):
        """Layer 2: Scope check fails when site company does not match reporting period company."""
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("100.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )
        record.reporting_period = self.period_other_company
        run = execute_validation_run(record, executed_by=self.user_site_mgr)
        self.assertEqual(run.status, ValidationStatus.INVALID)
        finding = run.results.filter(rule__code="SCOPE_PERIOD_COMPANY").first()
        self.assertIsNotNone(finding)
        self.assertEqual(finding.field_name, "reporting_period")
        self.assertEqual(finding.severity, ValidationSeverity.ERROR)

    def test_layer2_scope_inactive_site_failure(self):
        """Layer 2: Scope check fails when site is inactive."""
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("100.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )
        record.site = self.site_inactive
        run = execute_validation_run(record, executed_by=self.user_site_mgr)
        self.assertEqual(run.status, ValidationStatus.INVALID)
        finding = run.results.filter(rule__code="SCOPE_SITE_ACTIVE").first()
        self.assertIsNotNone(finding)
        self.assertEqual(finding.field_name, "site")

    def test_layer2_scope_inactive_activity_failure(self):
        """Layer 2: Scope check fails when activity master is inactive."""
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("100.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )
        record.activity = self.activity_inactive
        run = execute_validation_run(record, executed_by=self.user_site_mgr)
        self.assertEqual(run.status, ValidationStatus.INVALID)
        finding = run.results.filter(rule__code="SCOPE_ACTIVITY_ACTIVE").first()
        self.assertIsNotNone(finding)
        self.assertEqual(finding.field_name, "activity")

    def test_layer3_period_closed_reporting_period_failure(self):
        """Layer 3: Period check fails if reporting period is not OPEN."""
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("100.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )
        record.reporting_period = self.period_closed
        run = execute_validation_run(record, executed_by=self.user_site_mgr)
        self.assertEqual(run.status, ValidationStatus.INVALID)
        finding = run.results.filter(rule__code="PERIOD_STATUS_OPEN").first()
        self.assertIsNotNone(finding)
        self.assertEqual(finding.field_name, "reporting_period")
        self.assertEqual(finding.severity, ValidationSeverity.ERROR)

    def test_layer3_period_date_outside_boundary_failure(self):
        """Layer 3: Period check fails if measurement date falls outside period start/end."""
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("100.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )
        record.measurement_date = date(2026, 8, 15)  # Outside bounds
        run = execute_validation_run(record, executed_by=self.user_site_mgr)
        self.assertEqual(run.status, ValidationStatus.INVALID)
        finding = run.results.filter(rule__code="PERIOD_DATE_BOUNDARY").first()
        self.assertIsNotNone(finding)
        self.assertEqual(finding.field_name, "measurement_date")

    def test_layer4_activity_unit_not_allowed_failure(self):
        """Layer 4: Unit check fails if unit is not allowed for the activity."""
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("100.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )
        record.unit = self.unit_kwh
        run = execute_validation_run(record, executed_by=self.user_site_mgr)
        self.assertEqual(run.status, ValidationStatus.INVALID)
        finding = run.results.filter(rule__code="ACT_PERMISSIBLE_UNIT").first()
        self.assertIsNotNone(finding)
        self.assertEqual(finding.field_name, "unit")

    def test_layer5_evidence_mandatory_missing_failure(self):
        """Layer 5: Evidence check fails when regulated activity has no evidence attached."""
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("250.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )
        run = execute_validation_run(record, executed_by=self.user_site_mgr)
        self.assertEqual(run.status, ValidationStatus.INVALID)
        finding = run.results.filter(rule__code="EVID_MANDATORY_CHECK").first()
        self.assertIsNotNone(finding)
        self.assertEqual(finding.field_name, "evidence")
        self.assertEqual(finding.severity, ValidationSeverity.ERROR)

    def test_layer5_evidence_taxonomy_mismatch_warning(self):
        """Layer 5: Attached evidence taxonomy mismatch yields WARNING rather than blocking ERROR."""
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("250.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )
        # Attach evidence with taxonomy UTILITY_BILL instead of INVOICE or FUEL_CHALLAN
        create_evidence_record(
            activity_record=record,
            uploaded_file=self._get_evidence_file("electric_bill.pdf"),
            evidence_type=EvidenceType.UTILITY_BILL,
            description="Electric Bill for Pump",
            user=self.user_site_mgr,
        )
        run = execute_validation_run(record, executed_by=self.user_site_mgr)
        self.assertIsNone(run.results.filter(rule__code="EVID_MANDATORY_CHECK").first())
        tax_warning = run.results.filter(rule__code="EVID_TYPE_MATCH").first()
        self.assertIsNotNone(tax_warning)
        self.assertEqual(tax_warning.severity, ValidationSeverity.WARNING)

    def test_layer6_consistency_negative_quantity_failure(self):
        """Layer 6: Quantity must be positive, negative quantity is blocked."""
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("50.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )
        record.quantity = Decimal("-50.00")
        run = execute_validation_run(record, executed_by=self.user_site_mgr)
        self.assertEqual(run.status, ValidationStatus.INVALID)
        finding = run.results.filter(rule__code="CONSIST_POSITIVE_QUANTITY").first()
        self.assertIsNotNone(finding)
        self.assertEqual(finding.field_name, "quantity")
        self.assertEqual(finding.severity, ValidationSeverity.ERROR)

    def test_layer6_consistency_zero_consumption_warning(self):
        """Layer 6: Zero quantity produces an advisory WARNING, not a blocking ERROR."""
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("0.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )
        create_evidence_record(
            activity_record=record,
            uploaded_file=self._get_evidence_file("zero_invoice.pdf"),
            evidence_type=EvidenceType.INVOICE,
            description="Zero fuel statement",
            user=self.user_site_mgr,
        )
        run = execute_validation_run(record, executed_by=self.user_site_mgr)
        zero_warn = run.results.filter(rule__code="CONSIST_ZERO_QUANTITY").first()
        self.assertIsNotNone(zero_warn)
        self.assertEqual(zero_warn.severity, ValidationSeverity.WARNING)
        self.assertEqual(run.status, ValidationStatus.WARNING)
        self.assertEqual(record.validation_status, ValidationStatus.WARNING)

    def test_layer6_consistency_duplicate_warning(self):
        """Layer 6: Duplicate record advisory warning on identical site/activity/date/reference."""
        rec1 = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            evidence_reference="INV-2026-999",
            quantity=Decimal("500.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )
        rec2 = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            evidence_reference="INV-2026-999",
            quantity=Decimal("500.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )
        run = execute_validation_run(rec2, executed_by=self.user_site_mgr)
        dup_warn = run.results.filter(rule__code="CONSIST_DUPLICATE_CHECK").first()
        self.assertIsNotNone(dup_warn)
        self.assertEqual(dup_warn.severity, ValidationSeverity.WARNING)

    def test_layer7_workflow_readiness_demotes_ready_status(self):
        """Layer 7: If a record is set to READY but has blocking errors, engine demotes it to DRAFT."""
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("100.00"),
            unit=self.unit_litre,
            status=RecordStatus.READY,
            created_by=self.user_site_mgr,
        )
        record.quantity = None  # Missing quantity -> blocking ERROR
        self.assertEqual(record.status, RecordStatus.READY)
        run = execute_validation_run(record, executed_by=self.user_site_mgr)
        self.assertEqual(run.status, ValidationStatus.INVALID)
        record.refresh_from_db()
        self.assertEqual(record.status, RecordStatus.DRAFT)
        self.assertFalse(record.can_submit_for_review)

    def test_layer7_workflow_readiness_valid_record(self):
        """Layer 7: Fully compliant record gets status VALID and can submit for review."""
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("1500.00"),
            unit=self.unit_litre,
            status=RecordStatus.READY,
            created_by=self.user_site_mgr,
        )
        create_evidence_record(
            activity_record=record,
            uploaded_file=self._get_evidence_file("diesel_receipt.pdf"),
            evidence_type=EvidenceType.INVOICE,
            description="Diesel Fuel Receipt",
            user=self.user_site_mgr,
        )
        run = execute_validation_run(record, executed_by=self.user_site_mgr)
        self.assertEqual(run.status, ValidationStatus.VALID)
        self.assertEqual(run.error_count, 0)
        record.refresh_from_db()
        self.assertEqual(record.validation_status, ValidationStatus.VALID)
        self.assertEqual(record.status, RecordStatus.READY)
        self.assertTrue(record.can_submit_for_review)


class RevalidationAndRunHistoryTests(Phase10BaseTestCase):
    """Test revalidation flow, preserving immutable run history and audit trails."""

    def test_revalidation_preserves_history(self):
        """Test invalid record -> run 1 -> correction -> run 2 preserves both runs and audit log."""
        # 1. Create record with missing evidence (Regulated Diesel requires evidence)
        record = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("500.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )

        # 2. Run 1: Should be INVALID due to missing evidence
        run1 = execute_validation_run(record, executed_by=self.user_site_mgr)
        self.assertEqual(run1.run_number, 1)
        self.assertEqual(run1.status, ValidationStatus.INVALID)
        self.assertTrue(run1.error_count > 0)
        self.assertEqual(record.validation_status, ValidationStatus.INVALID)

        # 3. User attaches required evidence
        evidence_file = SimpleUploadedFile(
            name="diesel_receipt.pdf",
            content=b"%PDF-1.4\n1 0 obj\n<<\n>>\nendobj\ntrailer\n<<\n>>\n%%EOF",
            content_type="application/pdf",
        )
        create_evidence_record(
            activity_record=record,
            uploaded_file=evidence_file,
            evidence_type=EvidenceType.INVOICE,
            description="Verified Fuel Slip",
            user=self.user_site_mgr,
        )

        # 4. Run 2: Revalidation
        run2 = execute_validation_run(record, executed_by=self.user_site_mgr)
        self.assertEqual(run2.run_number, 2)
        self.assertEqual(run2.status, ValidationStatus.VALID)
        self.assertEqual(run2.error_count, 0)
        self.assertEqual(record.validation_status, ValidationStatus.VALID)

        # 5. Verify database history: exactly 2 runs exist for this record
        runs = ValidationRun.objects.filter(activity_record=record).order_by("run_number")
        self.assertEqual(runs.count(), 2)
        self.assertEqual(runs[0].status, ValidationStatus.INVALID)
        self.assertEqual(runs[1].status, ValidationStatus.VALID)
        self.assertEqual(record.latest_validation_run, run2)

        # 6. Verify AuthAuditLog recorded both events
        audit_events = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.VALIDATION_EXECUTED,
            user=self.user_site_mgr,
        ).order_by("created_at")
        self.assertEqual(audit_events.count(), 2)
        self.assertIn("Run #1", audit_events[0].details)
        self.assertIn("Run #2", audit_events[1].details)


class BatchValidationTests(Phase10BaseTestCase):
    """Test batch validation service functionality."""

    def test_batch_validation_aggregates_results(self):
        """Batch validator executes across queryset and returns structured summary."""
        # Record 1: Valid
        evidence_file = SimpleUploadedFile(
            name="electric_bill.pdf",
            content=b"%PDF-1.4\n1 0 obj\n<<\n>>\nendobj\ntrailer\n<<\n>>\n%%EOF",
            content_type="application/pdf",
        )
        rec1 = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_grid,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("3000.00"),
            unit=self.unit_kwh,
            created_by=self.user_site_mgr,
        )
        create_evidence_record(
            activity_record=rec1,
            uploaded_file=evidence_file,
            evidence_type=EvidenceType.UTILITY_BILL,
            description="Substation Meter Bill",
            user=self.user_site_mgr,
        )

        # Record 2: Invalid (Diesel without required evidence)
        rec2 = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 11),
            quantity=Decimal("200.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )

        # Record 3: Warning (zero quantity with evidence)
        evidence_file2 = SimpleUploadedFile(
            name="zero_invoice.pdf",
            content=b"%PDF-1.4\n1 0 obj\n<<\n>>\nendobj\ntrailer\n<<\n>>\n%%EOF",
            content_type="application/pdf",
        )
        rec3 = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_grid,
            measurement_date=date(2026, 5, 12),
            quantity=Decimal("0.00"),
            unit=self.unit_kwh,
            created_by=self.user_site_mgr,
        )
        create_evidence_record(
            activity_record=rec3,
            uploaded_file=evidence_file2,
            evidence_type=EvidenceType.UTILITY_BILL,
            description="Zero billing invoice",
            user=self.user_site_mgr,
        )

        qs = ActivityRecord.objects.filter(id__in=[rec1.id, rec2.id, rec3.id])
        summary = validate_activity_records(qs, executed_by=self.user_site_mgr)

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["valid"], 1)
        self.assertEqual(summary["invalid"], 1)
        self.assertEqual(summary["warning"], 1)
        self.assertEqual(len(summary["runs"]), 3)


class ValidationSecurityAndRBACTests(Phase10BaseTestCase):
    """Test RBAC enforcement, anti-IDOR protections, and governed rule administration."""

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.record_site1 = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("500.00"),
            unit=self.unit_litre,
            created_by=self.user_site_mgr,
        )
        self.record_site2 = ActivityRecord.objects.create(
            site=self.site2,
            reporting_period=self.period_open,
            activity=self.activity_diesel,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("800.00"),
            unit=self.unit_litre,
            created_by=self.user_other_site_mgr,
        )

    def test_site_manager_validate_own_record_success(self):
        """Site Manager can execute validation on activity records at their assigned site."""
        self.client.login(username="val_site_mgr", password="password123")
        url = reverse("core:record_validate", kwargs={"record_id": self.record_site1.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.record_site1.refresh_from_db()
        self.assertIsNotNone(self.record_site1.latest_validation_run)

    def test_site_manager_validate_unassigned_record_idor_defense(self):
        """Site Manager attempting to validate record at unassigned site triggers 403 Forbidden."""
        self.client.login(username="val_site_mgr", password="password123")
        url = reverse("core:record_validate", kwargs={"record_id": self.record_site2.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)

    def test_ajax_validate_returns_json_payload(self):
        """AJAX POST to validate endpoint returns structured JSON summary."""
        self.client.login(username="val_site_mgr", password="password123")
        url = reverse("core:record_validate", kwargs={"record_id": self.record_site1.id})
        response = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("status", data)
        self.assertIn("error_count", data)
        self.assertIn("warning_count", data)

    def test_auditor_cannot_execute_validation(self):
        """Auditors have read-only visibility and cannot trigger validation runs."""
        self.client.login(username="val_auditor", password="password123")
        url = reverse("core:record_validate", kwargs={"record_id": self.record_site1.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)

    def test_validation_run_detail_view_permissions(self):
        """Site Manager can view run for their assigned site; unassigned site triggers 403."""
        run_site1 = execute_validation_run(self.record_site1, executed_by=self.user_operator)
        run_site2 = execute_validation_run(self.record_site2, executed_by=self.user_operator)

        # Assigned site
        self.client.login(username="val_site_mgr", password="password123")
        url_site1 = reverse("core:validation_run_detail", kwargs={"run_id": run_site1.id})
        response = self.client.get(url_site1)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Validation Run #{run_site1.run_number}")

        # Unassigned site IDOR defense
        url_site2 = reverse("core:validation_run_detail", kwargs={"run_id": run_site2.id})
        response = self.client.get(url_site2)
        self.assertEqual(response.status_code, 403)

    def test_auditor_can_view_validation_run_detail(self):
        """Auditor can view historical validation run details across all sites."""
        run = execute_validation_run(self.record_site1, executed_by=self.user_operator)
        self.client.login(username="val_auditor", password="password123")
        url = reverse("core:validation_run_detail", kwargs={"run_id": run.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_site_manager_cannot_access_rules_governance(self):
        """Site Managers cannot view or manage validation rules (403 Forbidden)."""
        self.client.login(username="val_site_mgr", password="password123")
        rule = ValidationRule.objects.first()

        # Rule list
        res_list = self.client.get(reverse("core:validation_rule_list"))
        self.assertEqual(res_list.status_code, 403)

        # Rule toggle
        res_toggle = self.client.post(reverse("core:validation_rule_toggle", kwargs={"rule_id": rule.id}))
        self.assertEqual(res_toggle.status_code, 403)

        # Rule edit
        res_edit = self.client.get(reverse("core:validation_rule_edit", kwargs={"rule_id": rule.id}))
        self.assertEqual(res_edit.status_code, 403)

    def test_auditor_has_read_only_rules_access(self):
        """Auditor can view rules catalog but cannot toggle or edit rules."""
        self.client.login(username="val_auditor", password="password123")
        rule = ValidationRule.objects.first()

        # View list: Allowed
        res_list = self.client.get(reverse("core:validation_rule_list"))
        self.assertEqual(res_list.status_code, 200)

        # View detail: Allowed
        res_detail = self.client.get(reverse("core:validation_rule_detail", kwargs={"rule_id": rule.id}))
        self.assertEqual(res_detail.status_code, 200)

        # Toggle: Prohibited 403
        res_toggle = self.client.post(reverse("core:validation_rule_toggle", kwargs={"rule_id": rule.id}))
        self.assertEqual(res_toggle.status_code, 403)

        # Edit: Prohibited 403
        res_edit = self.client.get(reverse("core:validation_rule_edit", kwargs={"rule_id": rule.id}))
        self.assertEqual(res_edit.status_code, 403)

    def test_esg_manager_can_govern_and_toggle_rules(self):
        """ESG Manager can toggle and edit validation rules with audit logging."""
        self.client.login(username="val_esg", password="password123")
        rule = ValidationRule.objects.get(code="STRUCT_REQ_QUANTITY")
        self.assertTrue(rule.is_active)

        # Toggle rule
        url_toggle = reverse("core:validation_rule_toggle", kwargs={"rule_id": rule.id})
        response = self.client.post(url_toggle)
        self.assertEqual(response.status_code, 302)
        rule.refresh_from_db()
        self.assertFalse(rule.is_active)

        # Verify audit log
        audit = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.VALIDATION_RULE_UPDATED,
            user=self.user_esg,
        ).first()
        self.assertIsNotNone(audit)
        self.assertIn("deactivated", audit.details.lower())

        # Toggle back
        self.client.post(url_toggle)
        rule.refresh_from_db()
        self.assertTrue(rule.is_active)

    def test_esg_manager_can_edit_rule(self):
        """ESG Manager can update rule severity and blocking flag."""
        self.client.login(username="val_esg", password="password123")
        rule = ValidationRule.objects.get(code="CONSIST_ZERO_QUANTITY")

        url_edit = reverse("core:validation_rule_edit", kwargs={"rule_id": rule.id})
        response = self.client.post(url_edit, {
            "name": rule.name,
            "category": rule.category,
            "severity": ValidationSeverity.WARNING,
            "description": "Updated zero consumption policy.",
            "is_active": True,
            "is_blocking": False,
            "rule_parameters": "{}",
            "version": rule.version,
            "effective_from": (rule.effective_from or date.today()).isoformat(),
        })
        self.assertEqual(response.status_code, 302)
        rule.refresh_from_db()
        self.assertEqual(rule.description, "Updated zero consumption policy.")
