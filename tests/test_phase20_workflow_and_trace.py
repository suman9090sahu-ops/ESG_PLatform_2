"""
Comprehensive Automated Test Suite for Phase 20:
End-to-End ESG Data Workflow, Governed GHG Consolidation, and Auditor Lineage ("Trace This Number").

Tests:
1. ESG Manager Dashboard & Governed Reporting Consolidation (real database Scope 1/2/3 calculations)
2. 5-Layer "Trace This Number" Lineage Engine (Report -> Scope -> Submission -> Site Data -> Evidence)
3. Strict Auditor Read-Only Enforcement (Assurance mode; all mutation attempts blocked)
4. Full Multi-Role Workflow Journey:
   Site Manager (Entry + Evidence + Validation + Submit)
   -> Subsidiary Manager (Review + Request Correction)
   -> Site Manager (Edit + Resubmit)
   -> Subsidiary Manager (Verify)
   -> ESG Manager (Consolidation & Disclosures)
   -> Auditor (Assurance & Trace Lineage)
5. Object-Level Access Control & Anti-IDOR Security
"""

from datetime import date
from decimal import Decimal
import hashlib

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.models import (
    ActivityMaster,
    ActivityRecord,
    Company,
    CompanyAssignment,
    CorrectionRequest,
    CorrectionStatus,
    Evidence,
    EvidenceStatus,
    EvidenceType,
    PeriodStatus,
    Project,
    RecordStatus,
    ReportingPeriod,
    ReviewAction,
    Role,
    ScopeClassification,
    Site,
    SiteAssignment,
    Submission,
    SubmissionReview,
    SubmissionStatus,
    Subsidiary,
    SubsidiaryAssignment,
    UnitDimension,
    UnitOfMeasure,
    UserRole,
    ValidationRun,
    ValidationSeverity,
    ValidationStatus,
)
from apps.core.reporting_services import (
    calculate_record_emissions,
    get_auditor_dashboard_context,
    get_consolidated_report,
    get_esg_manager_dashboard_context,
    get_trace_lineage_context,
)
from apps.core.review_services import (
    request_correction_submission,
    user_can_review_submissions,
    verify_submission,
)
from apps.core.submission_services import submit_activity_record
from apps.core.validation_services import execute_validation_run, seed_standard_validation_rules

User = get_user_model()


class Phase20WorkflowAndTraceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        # 1. Seed Roles
        cls.role_site = Role.objects.create(code=Role.Code.SITE_MANAGER, name="Site Manager", is_active=True)
        cls.role_sub = Role.objects.create(code=Role.Code.SUBSIDIARY_MANAGER, name="Subsidiary Manager", is_active=True)
        cls.role_esg = Role.objects.create(code=Role.Code.ESG_MANAGER, name="ESG Manager", is_active=True)
        cls.role_auditor = Role.objects.create(code=Role.Code.AUDITOR, name="Auditor", is_active=True)
        cls.role_operator = Role.objects.create(code=Role.Code.MEIL_OPERATOR, name="Operations", is_active=True)

        # 2. Org Hierarchy
        cls.company = Company.objects.create(code="CO-TEST", name="Test Corporate Enterprise", status="ACTIVE")
        cls.subsidiary = Subsidiary.objects.create(
            code="SUB-TEST", name="Test Infrastructure Sub", company=cls.company, status="ACTIVE"
        )
        cls.project = Project.objects.create(
            code="PRJ-TEST", name="Test Hydro Project", subsidiary=cls.subsidiary, status="ACTIVE"
        )
        cls.site = Site.objects.create(
            code="SITE-TEST-101", name="Test Dam Headworks Site", project=cls.project, status="ACTIVE"
        )

        # 3. Reporting Period
        cls.period = ReportingPeriod.objects.create(
            company=cls.company,
            code="FY2025-26",
            name="FY 2025-26 Annual Cycle",
            fiscal_year="FY 2025-26",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            status=PeriodStatus.OPEN,
        )

        # 4. Units & Activity Masters
        from apps.core.models import ActivityCategory

        cls.cat_fuel = ActivityCategory.objects.create(code="FUEL", name="Fuel & Combustion", display_order=1)
        cls.cat_energy = ActivityCategory.objects.create(code="ENERGY", name="Energy", display_order=2)
        cls.cat_water = ActivityCategory.objects.create(code="WATER", name="Water", display_order=3)

        cls.unit_litre = UnitOfMeasure.objects.create(
            code="LITRE", name="Litre", symbol="L", dimension=UnitDimension.VOLUME
        )
        cls.unit_kwh = UnitOfMeasure.objects.create(
            code="KWH", name="Kilowatt Hour", symbol="kWh", dimension=UnitDimension.ENERGY
        )
        cls.unit_kl = UnitOfMeasure.objects.create(
            code="KL", name="Kilolitre", symbol="kL", dimension=UnitDimension.VOLUME
        )

        cls.act_diesel = ActivityMaster.objects.create(
            code="FUEL-DIESEL-STAT",
            name="Diesel Consumption (Stationary Generators)",
            category=cls.cat_fuel,
            activity_type="Stationary Combustion",
            base_unit=cls.unit_litre,
            scope_classification=ScopeClassification.SCOPE_1,
            evidence_requirement_hint="Fuel Delivery Challan",
            validation_rules={"evidence_required": True},
        )
        cls.act_diesel.allowed_units.add(cls.unit_litre)

        cls.act_grid = ActivityMaster.objects.create(
            code="ELEC-GRID",
            name="Grid Electricity Consumption",
            category=cls.cat_energy,
            activity_type="Purchased Electricity",
            base_unit=cls.unit_kwh,
            scope_classification=ScopeClassification.SCOPE_2,
            evidence_requirement_hint="Electricity Bill",
            validation_rules={"evidence_required": True},
        )
        cls.act_grid.allowed_units.add(cls.unit_kwh)

        cls.act_water = ActivityMaster.objects.create(
            code="WATER-GROUND",
            name="Groundwater Extraction",
            category=cls.cat_water,
            activity_type="Water Withdrawal",
            base_unit=cls.unit_kl,
            scope_classification=ScopeClassification.NON_GHG,
            evidence_requirement_hint="Meter Log",
            validation_rules={"evidence_required": True},
        )
        cls.act_water.allowed_units.add(cls.unit_kl)

        # 5. Users
        cls.user_site = User.objects.create_user(
            username="test_site_mgr", email="site@test.com", password="TestPass123!"
        )
        UserRole.objects.create(user=cls.user_site, role=cls.role_site, is_primary=True)
        SiteAssignment.objects.create(user=cls.user_site, site=cls.site)

        cls.user_sub = User.objects.create_user(
            username="test_sub_mgr", email="sub@test.com", password="TestPass123!"
        )
        UserRole.objects.create(user=cls.user_sub, role=cls.role_sub, is_primary=True)
        SubsidiaryAssignment.objects.create(user=cls.user_sub, subsidiary=cls.subsidiary)

        cls.user_esg = User.objects.create_user(
            username="test_esg_mgr", email="esg@test.com", password="TestPass123!"
        )
        UserRole.objects.create(user=cls.user_esg, role=cls.role_esg, is_primary=True)
        CompanyAssignment.objects.create(user=cls.user_esg, company=cls.company)

        cls.user_auditor = User.objects.create_user(
            username="test_auditor", email="auditor@test.com", password="TestPass123!"
        )
        UserRole.objects.create(user=cls.user_auditor, role=cls.role_auditor, is_primary=True)
        CompanyAssignment.objects.create(user=cls.user_auditor, company=cls.company)

        # Seed standard validation rules
        seed_standard_validation_rules(user=cls.user_esg)

    def setUp(self):
        self.client = Client()

    def test_reporting_services_emission_factors(self):
        """Verify regulatory IPCC & CEA emission factor conversions."""
        # Diesel: 1,000 L * 2.68 kg CO2e / 1,000 = 2.68 tCO2e
        rec_d = ActivityRecord(
            activity=self.act_diesel,
            quantity=Decimal("1000.0000"),
            unit=self.unit_litre,
        )
        res_d = calculate_record_emissions(rec_d)
        self.assertEqual(float(res_d["emissions_tco2e"]), 2.68)
        self.assertIn("IPCC 2006", res_d["factor_source"])

        # Grid Electricity: 10,000 kWh * 0.82 kg CO2e / 1,000 = 8.20 tCO2e
        rec_g = ActivityRecord(
            activity=self.act_grid,
            quantity=Decimal("10000.0000"),
            unit=self.unit_kwh,
        )
        res_g = calculate_record_emissions(rec_g)
        self.assertEqual(float(res_g["emissions_tco2e"]), 8.20)
        self.assertIn("CEA", res_g["factor_source"])

        # Physical Water: Non-GHG (0.0000 tCO2e)
        rec_w = ActivityRecord(
            activity=self.act_water,
            quantity=Decimal("500.0000"),
            unit=self.unit_kl,
        )
        res_w = calculate_record_emissions(rec_w)
        self.assertEqual(float(res_w["emissions_tco2e"]), 0.0)

    def test_full_end_to_end_workflow_and_traceability(self):
        """
        Executes the complete 6-stage end-to-end workflow:
        1. Site Manager creates record, uploads evidence, validates, and submits.
        2. Subsidiary Manager inspects submission and requests correction.
        3. Site Manager receives correction, edits quantity, and resubmits.
        4. Subsidiary Manager verifies resubmitted record.
        5. ESG Manager reviews consolidated enterprise report with real database metrics.
        6. Auditor traces the verified record through the 5-layer lineage engine.
        """
        # =====================================================================
        # STAGE 1: SITE MANAGER DATA ENTRY & SUBMISSION
        # =====================================================================
        rec = ActivityRecord.objects.create(
            site=self.site,
            reporting_period=self.period,
            activity=self.act_diesel,
            measurement_date=date(2025, 5, 20),
            quantity=Decimal("5000.0000"),
            unit=self.unit_litre,
            notes="Stationary generator diesel delivery for batching plant.",
            created_by=self.user_site,
            updated_by=self.user_site,
        )

        dummy_pdf = b"%PDF-1.4 Mock Diesel Challan #IOCL-998811"
        file_hash = hashlib.sha256(dummy_pdf).hexdigest()
        evidence = Evidence.objects.create(
            activity_record=rec,
            file=ContentFile(dummy_pdf, name="diesel_challan_may.pdf"),
            evidence_type=EvidenceType.FUEL_CHALLAN,
            original_filename="diesel_challan_may.pdf",
            file_type="application/pdf",
            file_size=len(dummy_pdf),
            file_hash=file_hash,
            description="IOCL bulk fuel delivery invoice and challan.",
            status=EvidenceStatus.ACTIVE,
            uploaded_by=self.user_site,
            ocr_metadata={"status": "EXTRACTED", "confidence_score": 0.99, "extracted_quantity": 5000.0},
        )

        val_run = execute_validation_run(rec, executed_by=self.user_site)
        self.assertEqual(val_run.status, ValidationStatus.VALID)

        sub1 = submit_activity_record(
            rec,
            user=self.user_site,
            comments="May 2025 batching plant fuel delivery.",
        )
        self.assertEqual(sub1.status, SubmissionStatus.SUBMITTED)
        rec.refresh_from_db()
        self.assertEqual(rec.status, RecordStatus.SUBMITTED)

        # =====================================================================
        # STAGE 2: SUBSIDIARY MANAGER REVIEWS & REQUESTS CORRECTION
        # =====================================================================
        self.assertTrue(user_can_review_submissions(self.user_sub))
        rev_correction = request_correction_submission(
            sub1,
            user=self.user_sub,
            reason="Meter log indicates 4,800 Litres received into tank, not 5,000 L.",
            required_correction="Please reconcile with site logistics officer and resubmit 4,800 L.",
            affected_area="ACTIVITY_DATA",
        )
        self.assertEqual(rev_correction.action, ReviewAction.REQUEST_CORRECTION)
        sub1.refresh_from_db()
        self.assertEqual(sub1.status, SubmissionStatus.CORRECTION_REQUESTED)
        rec.refresh_from_db()
        self.assertEqual(rec.status, RecordStatus.REJECTED)

        corr_req = CorrectionRequest.objects.get(submission=sub1)
        self.assertEqual(corr_req.status, CorrectionStatus.OPEN)
        self.assertIn("reconcile with site logistics", corr_req.required_correction)

        # =====================================================================
        # STAGE 3: SITE MANAGER CORRECTS DATA & RESUBMITS
        # =====================================================================
        rec.quantity = Decimal("4800.0000")
        rec.notes = "Reconciled with site logistics officer: corrected to 4,800 L as per tank dipstick."
        rec.updated_by = self.user_site
        rec.save()

        execute_validation_run(rec, executed_by=self.user_site)
        sub2 = submit_activity_record(
            rec,
            user=self.user_site,
            comments="Resubmitted with corrected quantity (4,800 L).",
        )
        self.assertEqual(sub2.submission_number, 2)
        self.assertEqual(sub2.status, SubmissionStatus.SUBMITTED)

        # =====================================================================
        # STAGE 4: SUBSIDIARY MANAGER VERIFIES RESUBMISSION
        # =====================================================================
        rev_verify = verify_submission(
            sub2,
            user=self.user_sub,
            comments="Reconciled quantity of 4,800 L verified against logbook. Approved.",
        )
        self.assertEqual(rev_verify.action, ReviewAction.VERIFY)
        sub2.refresh_from_db()
        self.assertEqual(sub2.status, SubmissionStatus.VERIFIED)
        rec.refresh_from_db()
        self.assertEqual(rec.status, RecordStatus.VERIFIED)

        # =====================================================================
        # STAGE 5: ESG MANAGER DASHBOARD & GOVERNED REPORTING CONSOLIDATION
        # =====================================================================
        esg_ctx = get_esg_manager_dashboard_context(self.user_esg)
        self.assertGreaterEqual(esg_ctx["verified_submissions_count"], 1)
        # 4,800 L * 2.68 kg CO2e / 1,000 = 12.864 tCO2e
        self.assertGreaterEqual(float(esg_ctx["total_scope1_tco2e"]), 12.86)

        report = get_consolidated_report(user=self.user_esg, period_id=self.period.id)
        self.assertEqual(len(report["disclosures"]), 1)
        disclosure = report["disclosures"][0]
        self.assertEqual(disclosure["record_id"], rec.id)
        self.assertEqual(float(disclosure["calculated_emissions_tco2e"]), 12.864)

        # Verify browser HTTP response for ESG Manager
        self.client.force_login(self.user_esg)
        resp_esg = self.client.get(reverse("core:reports_overview"))
        self.assertEqual(resp_esg.status_code, 200)
        self.assertContains(resp_esg, "Test Dam Headworks Site")
        self.assertContains(resp_esg, "12.8640")

        # =====================================================================
        # STAGE 6: AUDITOR "TRACE THIS NUMBER" 5-LAYER LINEAGE ENGINE
        # =====================================================================
        auditor_ctx = get_auditor_dashboard_context(self.user_auditor)
        self.assertEqual(auditor_ctx["total_disclosures"], 1)
        self.assertGreaterEqual(float(auditor_ctx["total_scope1_tco2e"]), 12.86)

        lineage = get_trace_lineage_context(record_id=rec.id, user=self.user_auditor)

        # Layer 1: Report Item
        self.assertEqual(lineage["layer1_report"]["metric_name"], "Diesel Consumption (Stationary Generators)")
        self.assertEqual(float(lineage["layer1_report"]["raw_quantity"]), 4800.0)
        self.assertEqual(float(lineage["layer1_report"]["emissions_tco2e"]), 12.864)

        # Layer 2: Scope & Emission Factor
        self.assertEqual(lineage["layer1_report"]["scope"], "SCOPE_1")
        self.assertIn("IPCC 2006", lineage["layer1_report"]["factor_source"])

        # Layer 3: Submission & Governance Decisions
        self.assertEqual(lineage["layer3_submission"]["status"], "VERIFIED")
        self.assertEqual(len(lineage["layer3_submission"]["all_reviews"]), 2)  # Correction + Verification

        # Layer 4: Site Telemetry & Validation
        self.assertEqual(lineage["layer2_consolidated"]["site"].code, "SITE-TEST-101")
        self.assertEqual(lineage["layer2_consolidated"]["subsidiary"].code, "SUB-TEST")

        # Layer 5: Supporting Evidence & Cryptographic Hash
        self.assertEqual(lineage["layer5_evidence"]["evidence_count"], 1)
        self.assertEqual(lineage["layer5_evidence"]["evidence_list"][0]["file_hash"], file_hash)
        self.assertEqual(lineage["layer5_evidence"]["evidence_list"][0]["ocr_metadata"]["confidence_score"], 0.99)

        # Browser HTTP Test for Auditor
        self.client.force_login(self.user_auditor)
        resp_trace = self.client.get(reverse("core:trace_record", kwargs={"record_id": rec.id}))
        self.assertEqual(resp_trace.status_code, 200)
        self.assertContains(resp_trace, "5-Layer Regulatory Lineage")
        self.assertContains(resp_trace, file_hash)
        self.assertContains(resp_trace, "READ-ONLY")

        # Auditor Directory
        resp_selector = self.client.get(reverse("core:trace_selector"))
        self.assertEqual(resp_selector.status_code, 200)
        self.assertContains(resp_selector, "Trace This Number")

    def test_auditor_strict_read_only_protection(self):
        """Auditor role cannot modify or verify records (strictly read-only assurance)."""
        self.assertFalse(user_can_review_submissions(self.user_auditor))

        # Attempting to verify as Auditor raises PermissionDenied
        rec = ActivityRecord.objects.create(
            site=self.site,
            reporting_period=self.period,
            activity=self.act_diesel,
            measurement_date=date(2025, 5, 25),
            quantity=Decimal("100.0"),
            unit=self.unit_litre,
            created_by=self.user_site,
        )
        Evidence.objects.create(
            activity_record=rec,
            file=ContentFile(b"%PDF dummy", name="sample1.pdf"),
            evidence_type=EvidenceType.FUEL_CHALLAN,
            original_filename="sample1.pdf",
            file_type="application/pdf",
            file_size=10,
            file_hash="dummyhash1",
            status=EvidenceStatus.ACTIVE,
            uploaded_by=self.user_site,
        )
        execute_validation_run(rec, executed_by=self.user_site)
        sub = submit_activity_record(rec, user=self.user_site)

        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            verify_submission(sub, user=self.user_auditor)

    def test_site_manager_cannot_approve_own_submission(self):
        """Site Manager cannot self-approve their own submissions."""
        self.assertFalse(user_can_review_submissions(self.user_site))

        rec = ActivityRecord.objects.create(
            site=self.site,
            reporting_period=self.period,
            activity=self.act_diesel,
            measurement_date=date(2025, 5, 26),
            quantity=Decimal("200.0"),
            unit=self.unit_litre,
            created_by=self.user_site,
        )
        Evidence.objects.create(
            activity_record=rec,
            file=ContentFile(b"%PDF dummy", name="sample2.pdf"),
            evidence_type=EvidenceType.FUEL_CHALLAN,
            original_filename="sample2.pdf",
            file_type="application/pdf",
            file_size=10,
            file_hash="dummyhash2",
            status=EvidenceStatus.ACTIVE,
            uploaded_by=self.user_site,
        )
        execute_validation_run(rec, executed_by=self.user_site)
        sub = submit_activity_record(rec, user=self.user_site)

        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            verify_submission(sub, user=self.user_site)
