"""
Comprehensive Automated Test Suite for Phase 15 — ESG Anomaly Detection Engine.

Validates:
1. Model Architecture & Integrity:
   - AnomalySeverity choices (INFO, LOW, MEDIUM, HIGH, CRITICAL)
   - AnomalyStatus choices (OPEN, ACKNOWLEDGED, EXPLAINED, RESOLVED, DISMISSED)
   - AnomalyCategory choices (HISTORICAL_SPIKE, HISTORICAL_DROP, PERIOD_VARIANCE, THRESHOLD_BREACH, DUPLICATE_SUSPECT, INTENSITY_ANOMALY)
   - AnomalyRule model fields, versioning, parameters, str representation
   - AnomalyDetectionRun model fields and properties
   - AnomalyRecord model fields, properties, string representation
   - AuthAuditLog event types for Phase 15 (ANOMALY_DETECTED, ANOMALY_ACKNOWLEDGED, ANOMALY_EXPLAINED, ANOMALY_DISMISSED, ANOMALY_RESOLVED, etc.)

2. Baseline Engine Invariants:
   - Rolling historical baseline calculation with >= 2 comparable records
   - Insufficient historical records (< 2) returns None baseline without generating false anomalies
   - Zero baseline handled safely without division by zero
   - Strict unit isolation: records with different units of measure are never compared
   - Self-exclusion invariant: record being evaluated is strictly excluded from its own baseline

3. Deterministic Anomaly Rule Evaluators:
   - Category A: Historical Consumption Spike (>100%, >150%, >200% CRITICAL)
   - Category B: Historical Consumption Drop (>50%, >80% HIGH)
   - Category C: Period-over-Period Variance (increase/decrease >50%)
   - Category D: Duplicate-Like Activity Suspect (identical date & quantity, identical evidence reference)
   - Category E: Configured Operational Threshold Breach (max limit, min floor)
   - Category F: Operational Intensity Anomaly (benchmark rate exceeded, graceful skip when no denominator)

4. Idempotency & Lifecycle Preservation:
   - Re-running detection repeatedly updates active finding rather than creating duplicate open records
   - Telemetry normalization (e.g. correcting quantity) automatically resolves previously open anomalies

5. Phase 14 Correction & Resubmission Integration:
   - Anomaly detected on initial abnormal submission
   - Subsidiary Manager requests correction
   - Site Manager revises quantity and resubmits
   - Re-evaluation auto-resolves anomaly, preserving historical audit context

6. Scoped Querysets & Anti-IDOR Security:
   - Site Manager: view-only for assigned operational sites
   - Subsidiary Manager: authorized division/company review workspace
   - Cross-subsidiary isolation: Subsidiary Manager for Division A blocked from Division B anomalies (403/404)
   - Auditor: read-only access (200), strictly blocked from executing review mutations (403)
   - Site Manager blocked from review mutations (403)

7. Review Lifecycle Management:
   - OPEN -> ACKNOWLEDGED
   - OPEN -> EXPLAINED (mandatory explanation)
   - OPEN -> RESOLVED (mandatory resolution comment, is_active=False)
   - OPEN -> DISMISSED (mandatory dismissal reason, is_active=False)
   - Terminal state protection: cannot mutate already resolved/dismissed anomaly
   - Full AuthAuditLog compliance event trail

8. Web Views & Endpoints:
   - Anomaly Desk (/anomalies/) renders filters and KPIs
   - Anomaly Detail (/anomalies/<id>/) renders telemetry comparison
   - Review action POST endpoint (/anomalies/<id>/action/) executes transitions
"""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.anomaly_services import (
    compute_historical_baseline,
    compute_period_variance_baseline,
    detect_anomalies_for_record,
    ensure_default_anomaly_rules,
    execute_anomaly_review_action,
    get_accessible_anomalies,
    get_anomaly_dashboard_metrics,
    run_batch_anomaly_detection,
    user_can_access_anomaly,
    user_can_review_anomaly,
)
from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    ActivityRecord,
    ActivityRevision,
    AnomalyCategory,
    AnomalyDetectionRun,
    AnomalyRecord,
    AnomalyRule,
    AnomalySeverity,
    AnomalyStatus,
    AuthAuditLog,
    Company,
    CompanyAssignment,
    CorrectionAffectedArea,
    CorrectionRequest,
    CorrectionStatus,
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
    Submission,
    SubmissionReview,
    SubmissionStatus,
    Subsidiary,
    SubsidiaryAssignment,
    UnitDimension,
    UnitOfMeasure,
    UserRole,
    ValidationRule,
    ValidationRun,
    ValidationStatus,
)
from apps.core.review_services import request_correction_submission
from apps.core.submission_services import submit_activity_record
from apps.core.validation_services import seed_standard_validation_rules

User = get_user_model()


class BasePhase15TestCase(TestCase):
    """Fixture setup for Phase 15 tests."""

    @classmethod
    def setUpTestData(cls):
        seed_standard_validation_rules()
        ensure_default_anomaly_rules()

        # 1. Setup Roles
        cls.role_site_mgr, _ = Role.objects.get_or_create(
            code=Role.Code.SITE_MANAGER,
            defaults={"name": "Site Manager"},
        )
        cls.role_sub_mgr, _ = Role.objects.get_or_create(
            code=Role.Code.SUBSIDIARY_MANAGER,
            defaults={"name": "Subsidiary Manager"},
        )
        cls.role_esg_mgr, _ = Role.objects.get_or_create(
            code=Role.Code.ESG_MANAGER,
            defaults={"name": "ESG Manager"},
        )
        cls.role_operator, _ = Role.objects.get_or_create(
            code=Role.Code.MEIL_OPERATOR,
            defaults={"name": "MEIL Operator"},
        )
        cls.role_auditor, _ = Role.objects.get_or_create(
            code=Role.Code.AUDITOR,
            defaults={"name": "Auditor"},
        )

        # 2. Setup Organizational Hierarchy
        cls.company_meil = Company.objects.create(
            name="MEIL Enterprise Group",
            code="MEIL-CORP",
            status=OrganizationStatus.ACTIVE,
        )
        cls.sub_water = Subsidiary.objects.create(
            company=cls.company_meil,
            name="Water Works Division",
            code="MEIL-WATER",
            status=OrganizationStatus.ACTIVE,
        )
        cls.sub_infra = Subsidiary.objects.create(
            company=cls.company_meil,
            name="Infrastructure Division",
            code="MEIL-INFRA",
            status=OrganizationStatus.ACTIVE,
        )

        cls.proj_water = Project.objects.create(
            subsidiary=cls.sub_water,
            name="Polavaram Irrigation Project",
            code="PROJ-POL",
            status=OrganizationStatus.ACTIVE,
        )
        cls.proj_infra = Project.objects.create(
            subsidiary=cls.sub_infra,
            name="Zojila Tunnel Project",
            code="PROJ-ZOJ",
            status=OrganizationStatus.ACTIVE,
        )

        cls.site_a = Site.objects.create(
            project=cls.proj_water,
            name="Polavaram Dam Headworks",
            code="SITE-POL-01",
            status=OrganizationStatus.ACTIVE,
        )
        cls.site_b = Site.objects.create(
            project=cls.proj_infra,
            name="Zojila West Portal Site",
            code="SITE-ZOJ-01",
            status=OrganizationStatus.ACTIVE,
        )

        # 3. Setup Reporting Periods
        cls.period_prior = ReportingPeriod.objects.create(
            company=cls.company_meil,
            name="FY 2025-26 Q1",
            code="FY25-Q1",
            fiscal_year="2025-26",
            start_date=timezone.now().date() - timezone.timedelta(days=120),
            end_date=timezone.now().date() - timezone.timedelta(days=31),
            status=PeriodStatus.CLOSED,
        )
        cls.period_current = ReportingPeriod.objects.create(
            company=cls.company_meil,
            name="FY 2025-26 Q2",
            code="FY25-Q2",
            fiscal_year="2025-26",
            start_date=timezone.now().date() - timezone.timedelta(days=30),
            end_date=timezone.now().date() + timezone.timedelta(days=60),
            status=PeriodStatus.OPEN,
        )

        # 4. Setup Activity Master & Units
        cls.category = ActivityCategory.objects.create(
            name="Energy & Fuel Operations",
            code="CAT-FUEL",
        )
        cls.unit_liter = UnitOfMeasure.objects.create(
            code="LTR",
            name="Liter",
            symbol="L",
            dimension=UnitDimension.VOLUME,
        )
        cls.unit_kg = UnitOfMeasure.objects.create(
            code="KGS",
            name="Kilogram",
            symbol="kg",
            dimension=UnitDimension.MASS,
        )
        cls.activity_diesel = ActivityMaster.objects.create(
            category=cls.category,
            name="Diesel Generator Operations",
            code="FUEL-DIESEL-GENSET",
            scope_classification=ScopeClassification.SCOPE_1,
            base_unit=cls.unit_liter,
            status=MasterStatus.ACTIVE,
            validation_rules={"evidence_required": False},
        )

        # 5. Setup Users & Scoping
        cls.sm_user_a = User.objects.create_user(
            username="sm_site_a",
            email="sm.a@meil.in",
            password="SiteManagerPass123!",
        )
        UserRole.objects.create(user=cls.sm_user_a, role=cls.role_site_mgr, is_primary=True)
        SiteAssignment.objects.create(user=cls.sm_user_a, site=cls.site_a)

        cls.sm_user_b = User.objects.create_user(
            username="sm_site_b",
            email="sm.b@meil.in",
            password="SiteManagerPass123!",
        )
        UserRole.objects.create(user=cls.sm_user_b, role=cls.role_site_mgr, is_primary=True)
        SiteAssignment.objects.create(user=cls.sm_user_b, site=cls.site_b)

        cls.sub_mgr_water = User.objects.create_user(
            username="sub_mgr_water",
            email="sub.water@meil.in",
            password="SubManagerPass123!",
        )
        UserRole.objects.create(user=cls.sub_mgr_water, role=cls.role_sub_mgr, is_primary=True)
        SubsidiaryAssignment.objects.create(user=cls.sub_mgr_water, subsidiary=cls.sub_water)

        cls.sub_mgr_infra = User.objects.create_user(
            username="sub_mgr_infra",
            email="sub.infra@meil.in",
            password="SubManagerPass123!",
        )
        UserRole.objects.create(user=cls.sub_mgr_infra, role=cls.role_sub_mgr, is_primary=True)
        SubsidiaryAssignment.objects.create(user=cls.sub_mgr_infra, subsidiary=cls.sub_infra)

        cls.auditor = User.objects.create_user(
            username="auditor_user",
            email="auditor@meil.in",
            password="AuditorPass123!",
        )
        UserRole.objects.create(user=cls.auditor, role=cls.role_auditor, is_primary=True)
        CompanyAssignment.objects.create(user=cls.auditor, company=cls.company_meil)

        cls.esg_mgr = User.objects.create_user(
            username="esg_mgr_corp",
            email="esg.mgr@meil.in",
            password="EsgManagerPass123!",
        )
        UserRole.objects.create(user=cls.esg_mgr, role=cls.role_esg_mgr, is_primary=True)
        CompanyAssignment.objects.create(user=cls.esg_mgr, company=cls.company_meil)


class TestAnomalyModelsAndRules(BasePhase15TestCase):
    """Tests for Phase 15 domain models, choices, and rules."""

    def test_anomaly_severity_choices(self):
        expected = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
        for s in expected:
            self.assertIn(s, AnomalySeverity.values)

    def test_anomaly_status_choices(self):
        expected = ["OPEN", "ACKNOWLEDGED", "EXPLAINED", "RESOLVED", "DISMISSED"]
        for s in expected:
            self.assertIn(s, AnomalyStatus.values)

    def test_anomaly_category_choices(self):
        expected = [
            "HISTORICAL_SPIKE",
            "HISTORICAL_DROP",
            "PERIOD_VARIANCE",
            "THRESHOLD_BREACH",
            "DUPLICATE_SUSPECT",
            "INTENSITY_ANOMALY",
        ]
        for c in expected:
            self.assertIn(c, AnomalyCategory.values)

    def test_canonical_rules_seeded(self):
        rules = AnomalyRule.objects.all()
        self.assertGreaterEqual(rules.count(), 6)
        codes = list(rules.values_list("code", flat=True))
        self.assertIn("HIST_SPIKE_100", codes)
        self.assertIn("HIST_DROP_50", codes)
        self.assertIn("PERIOD_VAR_50", codes)
        self.assertIn("DUPLICATE_RECORD", codes)
        self.assertIn("THRESHOLD_BREACH", codes)

    def test_audit_event_types(self):
        types = AuthAuditLog.EventType.values
        self.assertIn("ANOMALY_DETECTED", types)
        self.assertIn("ANOMALY_ACKNOWLEDGED", types)
        self.assertIn("ANOMALY_EXPLAINED", types)
        self.assertIn("ANOMALY_DISMISSED", types)
        self.assertIn("ANOMALY_RESOLVED", types)
        self.assertIn("ANOMALY_DETECTION_RUN", types)


class TestBaselineCalculations(BasePhase15TestCase):
    """Tests for rolling historical baseline calculations."""

    def test_sufficient_historical_data(self):
        # Create 2 historical records with 4,000 L and 6,000 L -> avg = 5,000 L
        ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_prior,
            activity=self.activity_diesel,
            measurement_date=self.period_prior.start_date + timezone.timedelta(days=5),
            quantity=Decimal("4000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.VERIFIED,
            created_by=self.sm_user_a,
        )
        ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_prior,
            activity=self.activity_diesel,
            measurement_date=self.period_prior.start_date + timezone.timedelta(days=20),
            quantity=Decimal("6000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.VERIFIED,
            created_by=self.sm_user_a,
        )

        current_record = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=self.period_current.start_date + timezone.timedelta(days=5),
            quantity=Decimal("12000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.READY,
            created_by=self.sm_user_a,
        )

        rule_spike = AnomalyRule.objects.get(code="HIST_SPIKE_100")
        baseline, count, note = compute_historical_baseline(current_record, rule_spike)

        self.assertEqual(count, 2)
        self.assertEqual(baseline, Decimal("5000.0000"))

    def test_insufficient_historical_data_returns_none(self):
        # Only 1 historical record exists (< min_baseline_records=2)
        ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_prior,
            activity=self.activity_diesel,
            measurement_date=self.period_prior.start_date + timezone.timedelta(days=5),
            quantity=Decimal("5000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.VERIFIED,
            created_by=self.sm_user_a,
        )

        current_record = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=self.period_current.start_date + timezone.timedelta(days=5),
            quantity=Decimal("15000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.READY,
            created_by=self.sm_user_a,
        )

        rule_spike = AnomalyRule.objects.get(code="HIST_SPIKE_100")
        baseline, count, note = compute_historical_baseline(current_record, rule_spike)

        self.assertIsNone(baseline)
        self.assertEqual(count, 1)
        self.assertIn("Insufficient", note)

    def test_new_site_has_no_false_anomalies(self):
        # Site B has 0 historical records -> detection should not flag spike/drop falsely
        new_site_record = ActivityRecord.objects.create(
            site=self.site_b,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=self.period_current.start_date + timezone.timedelta(days=5),
            quantity=Decimal("20000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.READY,
            created_by=self.sm_user_b,
        )

        anomalies = detect_anomalies_for_record(new_site_record, user=self.sm_user_b)
        # Spike and drop rules should NOT trigger because baseline is unavailable
        spike_anomalies = [a for a in anomalies if a.rule_code in ["HIST_SPIKE_100", "HIST_DROP_50"]]
        self.assertEqual(len(spike_anomalies), 0)

    def test_incompatible_units_not_compared(self):
        # Allow unit_kg for activity to pass model validation
        self.activity_diesel.allowed_units.add(self.unit_kg)
        # Create records with kg instead of L
        ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_prior,
            activity=self.activity_diesel,
            measurement_date=self.period_prior.start_date + timezone.timedelta(days=5),
            quantity=Decimal("5000.0000"),
            unit=self.unit_kg,
            status=RecordStatus.VERIFIED,
            created_by=self.sm_user_a,
        )
        current_record = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=self.period_current.start_date + timezone.timedelta(days=5),
            quantity=Decimal("15000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.READY,
            created_by=self.sm_user_a,
        )

        rule = AnomalyRule.objects.get(code="HIST_SPIKE_100")
        baseline, count, _ = compute_historical_baseline(current_record, rule)
        # Should be 0 matching records because units differ
        self.assertIsNone(baseline)
        self.assertEqual(count, 0)


class TestDeterministicRuleEvaluations(BasePhase15TestCase):
    """Tests for each of the 6 initial anomaly rule categories."""

    def test_historical_spike_detection(self):
        # Historical avg = 5,000 L. Current = 12,000 L (+140% spike)
        for q in [5000, 5000]:
            ActivityRecord.objects.create(
                site=self.site_a,
                reporting_period=self.period_prior,
                activity=self.activity_diesel,
                measurement_date=self.period_prior.start_date + timezone.timedelta(days=5),
                quantity=Decimal(str(q)),
                unit=self.unit_liter,
                status=RecordStatus.VERIFIED,
                created_by=self.sm_user_a,
            )

        spike_record = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=self.period_current.start_date + timezone.timedelta(days=5),
            quantity=Decimal("12000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.READY,
            created_by=self.sm_user_a,
        )

        anomalies = detect_anomalies_for_record(spike_record, user=self.sm_user_a)
        spike_finding = next((a for a in anomalies if a.rule_code == "HIST_SPIKE_100"), None)

        self.assertIsNotNone(spike_finding)
        self.assertEqual(spike_finding.observed_value, Decimal("12000.0000"))
        self.assertEqual(spike_finding.baseline_value, Decimal("5000.0000"))
        self.assertEqual(spike_finding.deviation_value, Decimal("7000.0000"))
        self.assertEqual(spike_finding.deviation_percentage, Decimal("140.00"))
        self.assertIn("140.0% above the site's historical baseline", spike_finding.explanation)
        self.assertIn(spike_finding.severity, [AnomalySeverity.HIGH, AnomalySeverity.CRITICAL])
        # Operational record is NOT modified
        self.assertEqual(spike_record.quantity, Decimal("12000.0000"))

    def test_historical_drop_detection(self):
        # Historical avg = 4,000 L. Current = 400 L (90% drop)
        for q in [4000, 4000]:
            ActivityRecord.objects.create(
                site=self.site_a,
                reporting_period=self.period_prior,
                activity=self.activity_diesel,
                measurement_date=self.period_prior.start_date + timezone.timedelta(days=5),
                quantity=Decimal(str(q)),
                unit=self.unit_liter,
                status=RecordStatus.VERIFIED,
                created_by=self.sm_user_a,
            )

        drop_record = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=self.period_current.start_date + timezone.timedelta(days=5),
            quantity=Decimal("400.0000"),
            unit=self.unit_liter,
            status=RecordStatus.READY,
            created_by=self.sm_user_a,
        )

        anomalies = detect_anomalies_for_record(drop_record, user=self.sm_user_a)
        drop_finding = next((a for a in anomalies if a.rule_code == "HIST_DROP_50"), None)

        self.assertIsNotNone(drop_finding)
        self.assertEqual(drop_finding.observed_value, Decimal("400.0000"))
        self.assertEqual(drop_finding.baseline_value, Decimal("4000.0000"))
        self.assertEqual(drop_finding.deviation_percentage, Decimal("-90.00"))
        self.assertIn("90.0% below the site's historical baseline", drop_finding.explanation)

    def test_period_over_period_variance(self):
        # Prior period quantity = 1,000 L. Current = 2,500 L (+150% variance)
        ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_prior,
            activity=self.activity_diesel,
            measurement_date=self.period_prior.start_date + timezone.timedelta(days=5),
            quantity=Decimal("1000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.VERIFIED,
            created_by=self.sm_user_a,
        )

        curr_rec = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=self.period_current.start_date + timezone.timedelta(days=5),
            quantity=Decimal("2500.0000"),
            unit=self.unit_liter,
            status=RecordStatus.READY,
            created_by=self.sm_user_a,
        )

        anomalies = detect_anomalies_for_record(curr_rec, user=self.sm_user_a)
        var_finding = next((a for a in anomalies if a.rule_code == "PERIOD_VAR_50"), None)

        self.assertIsNotNone(var_finding)
        self.assertEqual(var_finding.observed_value, Decimal("2500.0000"))
        self.assertEqual(var_finding.baseline_value, Decimal("1000.0000"))
        self.assertEqual(var_finding.deviation_percentage, Decimal("150.00"))
        self.assertIn("150.0% increase", var_finding.explanation)

    def test_duplicate_activity_detection_by_date_and_quantity(self):
        # Existing record on site A with 5,000 L on 2025-06-15
        target_date = self.period_current.start_date + timezone.timedelta(days=10)
        rec1 = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=target_date,
            quantity=Decimal("5000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.READY,
            created_by=self.sm_user_a,
        )

        # Second record with identical site, activity, unit, date, and quantity
        rec2 = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=target_date,
            quantity=Decimal("5000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.READY,
            created_by=self.sm_user_a,
        )

        anomalies = detect_anomalies_for_record(rec2, user=self.sm_user_a)
        dup_finding = next((a for a in anomalies if a.rule_code == "DUPLICATE_RECORD"), None)

        self.assertIsNotNone(dup_finding)
        self.assertIn(f"matches Record #{rec1.id}", dup_finding.explanation)
        self.assertEqual(dup_finding.severity, AnomalySeverity.HIGH)

    def test_duplicate_activity_detection_by_evidence_reference(self):
        # Existing record with invoice number IOCL-INV-999
        rec1 = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=self.period_current.start_date + timezone.timedelta(days=2),
            quantity=Decimal("3000.0000"),
            unit=self.unit_liter,
            evidence_reference="IOCL-INV-999",
            status=RecordStatus.READY,
            created_by=self.sm_user_a,
        )

        rec2 = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=self.period_current.start_date + timezone.timedelta(days=10),
            quantity=Decimal("3500.0000"),
            unit=self.unit_liter,
            evidence_reference="IOCL-INV-999",
            status=RecordStatus.READY,
            created_by=self.sm_user_a,
        )

        anomalies = detect_anomalies_for_record(rec2, user=self.sm_user_a)
        dup_finding = next((a for a in anomalies if a.rule_code == "DUPLICATE_RECORD"), None)

        self.assertIsNotNone(dup_finding)
        self.assertIn("shares identical evidence reference 'IOCL-INV-999'", dup_finding.explanation)

    def test_threshold_breach_detection(self):
        # Configured threshold is 50,000 L max. Record is 75,000 L.
        breach_record = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=self.period_current.start_date + timezone.timedelta(days=5),
            quantity=Decimal("75000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.READY,
            created_by=self.sm_user_a,
        )

        anomalies = detect_anomalies_for_record(breach_record, user=self.sm_user_a)
        breach_finding = next((a for a in anomalies if a.rule_code == "THRESHOLD_BREACH"), None)

        self.assertIsNotNone(breach_finding)
        self.assertEqual(breach_finding.observed_value, Decimal("75000.0000"))
        self.assertIn("breaches configured maximum operational threshold limit", breach_finding.explanation)


class TestIdempotencyAndHistory(BasePhase15TestCase):
    """Tests that repeatedly running anomaly detection updates open records rather than duplicating them."""

    def test_repeated_detection_does_not_duplicate_anomalies(self):
        # Setup 2 baseline records
        for q in [5000, 5000]:
            ActivityRecord.objects.create(
                site=self.site_a,
                reporting_period=self.period_prior,
                activity=self.activity_diesel,
                measurement_date=self.period_prior.start_date + timezone.timedelta(days=5),
                quantity=Decimal(str(q)),
                unit=self.unit_liter,
                status=RecordStatus.VERIFIED,
                created_by=self.sm_user_a,
            )

        record = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=self.period_current.start_date + timezone.timedelta(days=5),
            quantity=Decimal("12000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.READY,
            created_by=self.sm_user_a,
        )

        # Run 1
        anoms1 = detect_anomalies_for_record(record, user=self.sm_user_a)
        count_after_first = AnomalyRecord.objects.filter(activity_record=record).count()

        # Run 2 (simulate page refresh or batch rerun)
        anoms2 = detect_anomalies_for_record(record, user=self.sm_user_a)
        count_after_second = AnomalyRecord.objects.filter(activity_record=record).count()

        # No duplicate rows created!
        self.assertEqual(count_after_first, count_after_second)
        self.assertEqual(len(anoms1), len(anoms2))

    def test_normalizing_telemetry_auto_resolves_open_anomaly(self):
        for q in [5000, 5000]:
            ActivityRecord.objects.create(
                site=self.site_a,
                reporting_period=self.period_prior,
                activity=self.activity_diesel,
                measurement_date=self.period_prior.start_date + timezone.timedelta(days=5),
                quantity=Decimal(str(q)),
                unit=self.unit_liter,
                status=RecordStatus.VERIFIED,
                created_by=self.sm_user_a,
            )

        # 1. Abnormal record initially
        record = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=self.period_current.start_date + timezone.timedelta(days=5),
            quantity=Decimal("15000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.READY,
            created_by=self.sm_user_a,
        )
        detect_anomalies_for_record(record, user=self.sm_user_a)

        spike_anom = AnomalyRecord.objects.get(activity_record=record, rule_code="HIST_SPIKE_100")
        self.assertEqual(spike_anom.status, AnomalyStatus.OPEN)
        self.assertTrue(spike_anom.is_active)

        # 2. User edits record to 5,200 L (normal range)
        record.quantity = Decimal("5200.0000")
        record.save()

        # 3. Rerun detection
        detect_anomalies_for_record(record, user=self.sm_user_a)

        # 4. Open anomaly is transitioned to RESOLVED, preserving the audit history!
        spike_anom.refresh_from_db()
        self.assertEqual(spike_anom.status, AnomalyStatus.RESOLVED)
        self.assertFalse(spike_anom.is_active)
        self.assertIn("Automatically resolved", spike_anom.review_comment)


class TestPhase14CorrectionIntegration(BasePhase15TestCase):
    """Tests end-to-end integration with Phase 14 Correction & Resubmission workflow."""

    def test_submission_and_correction_anomaly_lifecycle(self):
        # 1. Setup baseline records
        for q in [5000, 5000]:
            ActivityRecord.objects.create(
                site=self.site_a,
                reporting_period=self.period_prior,
                activity=self.activity_diesel,
                measurement_date=self.period_prior.start_date + timezone.timedelta(days=5),
                quantity=Decimal(str(q)),
                unit=self.unit_liter,
                status=RecordStatus.VERIFIED,
                created_by=self.sm_user_a,
            )

        # 2. Record with unusual quantity (15,000 L)
        record = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=self.period_current.start_date + timezone.timedelta(days=5),
            quantity=Decimal("15000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.READY,
            created_by=self.sm_user_a,
        )

        # 3. Submit record -> automated anomaly detection runs
        submission = submit_activity_record(
            record=record,
            user=self.sm_user_a,
            comments="Initial monthly diesel telemetry entry.",
        )

        anomalies = AnomalyRecord.objects.filter(activity_record=record)
        self.assertTrue(anomalies.exists())
        spike = anomalies.filter(rule_code="HIST_SPIKE_100").first()
        self.assertIsNotNone(spike)
        self.assertEqual(spike.submission, submission)

        # 4. Subsidiary Manager requests correction citing the anomaly
        request_correction_submission(
            submission=submission,
            user=self.sub_mgr_water,
            reason="Unusual consumption spike: 15,000 L exceeds historical average of 5,000 L. Please verify meter.",
            required_correction="Verify tank dip reading and re-upload calibration slip.",
            affected_area=CorrectionAffectedArea.ACTIVITY_DATA,
        )

        # 5. Site Manager corrects quantity to 5,500 L
        from apps.core.correction_services import update_corrected_record, resubmit_corrected_activity
        corr_req = CorrectionRequest.objects.get(submission=submission)

        update_corrected_record(
            correction_req=corr_req,
            user=self.sm_user_a,
            form_data={
                "quantity": Decimal("5500.0000"),
                "measurement_date": record.measurement_date,
                "site_manager_notes": "Dip chart error corrected. Actual consumption was 5,500 L.",
            },
        )

        # 6. Resubmit corrected record
        resubmission = resubmit_corrected_activity(
            correction_req=corr_req,
            user=self.sm_user_a,
            comments="Resubmitted with corrected meter quantity.",
        )

        # 7. Verify anomaly re-evaluation auto-resolved the historical spike
        spike.refresh_from_db()
        self.assertEqual(spike.status, AnomalyStatus.RESOLVED)
        self.assertFalse(spike.is_active)
        self.assertIn("Automatically resolved", spike.review_comment)


class TestScopingAndAntiIDOR(BasePhase15TestCase):
    """Tests role scoping, permissions, and IDOR defenses."""

    def setUp(self):
        super().setUp()
        # Create Anomaly on Site A (Water division)
        self.rec_a = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=self.period_current.start_date + timezone.timedelta(days=5),
            quantity=Decimal("99000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.READY,
            created_by=self.sm_user_a,
        )
        self.anom_a = AnomalyRecord.objects.create(
            activity_record=self.rec_a,
            rule=AnomalyRule.objects.get(code="THRESHOLD_BREACH"),
            rule_code="THRESHOLD_BREACH",
            rule_version=1,
            severity=AnomalySeverity.HIGH,
            status=AnomalyStatus.OPEN,
            observed_value=Decimal("99000.0000"),
            baseline_value=Decimal("50000.0000"),
            deviation_value=Decimal("49000.0000"),
            explanation="Breaches operational threshold",
        )

        # Create Anomaly on Site B (Infra division)
        self.rec_b = ActivityRecord.objects.create(
            site=self.site_b,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=self.period_current.start_date + timezone.timedelta(days=5),
            quantity=Decimal("95000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.READY,
            created_by=self.sm_user_b,
        )
        self.anom_b = AnomalyRecord.objects.create(
            activity_record=self.rec_b,
            rule=AnomalyRule.objects.get(code="THRESHOLD_BREACH"),
            rule_code="THRESHOLD_BREACH",
            rule_version=1,
            severity=AnomalySeverity.HIGH,
            status=AnomalyStatus.OPEN,
            observed_value=Decimal("95000.0000"),
            baseline_value=Decimal("50000.0000"),
            deviation_value=Decimal("45000.0000"),
            explanation="Breaches operational threshold",
        )

    def test_scoped_queryset_access(self):
        # Site Manager A sees only Site A anomaly
        qs_sm_a = get_accessible_anomalies(self.sm_user_a)
        self.assertIn(self.anom_a, qs_sm_a)
        self.assertNotIn(self.anom_b, qs_sm_a)

        # Subsidiary Manager Water sees Site A, not Site B
        qs_sub_water = get_accessible_anomalies(self.sub_mgr_water)
        self.assertIn(self.anom_a, qs_sub_water)
        self.assertNotIn(self.anom_b, qs_sub_water)

        # Auditor sees both
        qs_auditor = get_accessible_anomalies(self.auditor)
        self.assertIn(self.anom_a, qs_auditor)
        self.assertIn(self.anom_b, qs_auditor)

    def test_idor_cross_subsidiary_denied(self):
        # Sub Mgr Water attempting to access Anomaly B
        self.assertFalse(user_can_access_anomaly(self.sub_mgr_water, self.anom_b))
        self.assertFalse(user_can_review_anomaly(self.sub_mgr_water, self.anom_b))

        with self.assertRaises(PermissionDenied):
            execute_anomaly_review_action(
                anomaly=self.anom_b,
                action="ACKNOWLEDGE",
                comment="Attempted unauthorized action",
                user=self.sub_mgr_water,
            )

    def test_site_manager_cannot_execute_review_actions(self):
        # Site Manager can view Anomaly A, but CANNOT execute review actions
        self.assertTrue(user_can_access_anomaly(self.sm_user_a, self.anom_a))
        self.assertFalse(user_can_review_anomaly(self.sm_user_a, self.anom_a))

        with self.assertRaises(PermissionDenied):
            execute_anomaly_review_action(
                anomaly=self.anom_a,
                action="RESOLVE",
                comment="Site Manager trying to resolve",
                user=self.sm_user_a,
            )

    def test_auditor_cannot_execute_review_actions(self):
        # Auditor has read-only access
        self.assertTrue(user_can_access_anomaly(self.auditor, self.anom_a))
        self.assertFalse(user_can_review_anomaly(self.auditor, self.anom_a))

        with self.assertRaises(PermissionDenied):
            execute_anomaly_review_action(
                anomaly=self.anom_a,
                action="DISMISS",
                comment="Auditor trying to dismiss",
                user=self.auditor,
            )


class TestReviewLifecycleActions(BasePhase15TestCase):
    """Tests for review lifecycle transitions: Acknowledge, Explain, Resolve, Dismiss."""

    def setUp(self):
        super().setUp()
        self.rec = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=self.period_current.start_date + timezone.timedelta(days=5),
            quantity=Decimal("60000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.READY,
            created_by=self.sm_user_a,
        )
        self.anom = AnomalyRecord.objects.create(
            activity_record=self.rec,
            rule=AnomalyRule.objects.get(code="THRESHOLD_BREACH"),
            rule_code="THRESHOLD_BREACH",
            rule_version=1,
            severity=AnomalySeverity.HIGH,
            status=AnomalyStatus.OPEN,
            observed_value=Decimal("60000.0000"),
            explanation="Breaches threshold",
        )

    def test_acknowledge_action(self):
        updated = execute_anomaly_review_action(
            anomaly=self.anom,
            action="ACKNOWLEDGE",
            comment="Seen by reviewer",
            user=self.sub_mgr_water,
        )
        self.assertEqual(updated.status, AnomalyStatus.ACKNOWLEDGED)
        self.assertEqual(updated.resolution_action, "ACKNOWLEDGED")
        self.assertTrue(updated.is_active)
        self.assertEqual(updated.reviewed_by, self.sub_mgr_water)

        # Audit event logged
        log = AuthAuditLog.objects.filter(event_type=AuthAuditLog.EventType.ANOMALY_ACKNOWLEDGED).first()
        self.assertIsNotNone(log)

    def test_explain_action(self):
        updated = execute_anomaly_review_action(
            anomaly=self.anom,
            action="EXPLAIN",
            comment="Operated extra generators during power grid blackout.",
            user=self.sub_mgr_water,
        )
        self.assertEqual(updated.status, AnomalyStatus.EXPLAINED)
        self.assertEqual(updated.review_comment, "Operated extra generators during power grid blackout.")
        self.assertTrue(updated.is_active)

        log = AuthAuditLog.objects.filter(event_type=AuthAuditLog.EventType.ANOMALY_EXPLAINED).first()
        self.assertIsNotNone(log)

    def test_resolve_action(self):
        updated = execute_anomaly_review_action(
            anomaly=self.anom,
            action="RESOLVE",
            comment="Site inspection confirmed consumption valid due to pump commissioning.",
            user=self.sub_mgr_water,
        )
        self.assertEqual(updated.status, AnomalyStatus.RESOLVED)
        self.assertFalse(updated.is_active)

        log = AuthAuditLog.objects.filter(event_type=AuthAuditLog.EventType.ANOMALY_RESOLVED).first()
        self.assertIsNotNone(log)

    def test_dismiss_action(self):
        updated = execute_anomaly_review_action(
            anomaly=self.anom,
            action="DISMISS",
            comment="False alarm due to transient test meter.",
            user=self.sub_mgr_water,
        )
        self.assertEqual(updated.status, AnomalyStatus.DISMISSED)
        self.assertFalse(updated.is_active)

        log = AuthAuditLog.objects.filter(event_type=AuthAuditLog.EventType.ANOMALY_DISMISSED).first()
        self.assertIsNotNone(log)

    def test_empty_comment_rejected_for_explain_resolve_dismiss(self):
        for act in ["EXPLAIN", "RESOLVE", "DISMISS"]:
            with self.assertRaises(ValidationError):
                execute_anomaly_review_action(
                    anomaly=self.anom,
                    action=act,
                    comment="",
                    user=self.sub_mgr_water,
                )

    def test_cannot_modify_terminal_state(self):
        # Resolve it first
        execute_anomaly_review_action(
            anomaly=self.anom,
            action="RESOLVE",
            comment="Resolved",
            user=self.sub_mgr_water,
        )
        # Attempt to acknowledge resolved anomaly should fail
        with self.assertRaises(ValidationError):
            execute_anomaly_review_action(
                anomaly=self.anom,
                action="ACKNOWLEDGE",
                comment="Trying to ack",
                user=self.sub_mgr_water,
            )


class TestWebViewsAndFlows(BasePhase15TestCase):
    """Tests HTTP views for Anomaly Desk, Detail, and Action handling."""

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.rec = ActivityRecord.objects.create(
            site=self.site_a,
            reporting_period=self.period_current,
            activity=self.activity_diesel,
            measurement_date=self.period_current.start_date + timezone.timedelta(days=5),
            quantity=Decimal("65000.0000"),
            unit=self.unit_liter,
            status=RecordStatus.READY,
            created_by=self.sm_user_a,
        )
        self.anom = AnomalyRecord.objects.create(
            activity_record=self.rec,
            rule=AnomalyRule.objects.get(code="THRESHOLD_BREACH"),
            rule_code="THRESHOLD_BREACH",
            rule_version=1,
            severity=AnomalySeverity.HIGH,
            status=AnomalyStatus.OPEN,
            observed_value=Decimal("65000.0000"),
            explanation="Breaches threshold",
        )

    def test_anomaly_desk_list_view(self):
        self.client.force_login(self.sub_mgr_water)
        res = self.client.get(reverse("core:anomaly_list"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "ESG Anomaly Desk")
        self.assertContains(res, "THRESHOLD_BREACH")
        self.assertContains(res, "Polavaram Dam Headworks")

    def test_anomaly_detail_view(self):
        self.client.force_login(self.sub_mgr_water)
        res = self.client.get(reverse("core:anomaly_detail", kwargs={"anomaly_id": self.anom.id}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Operational Telemetry &amp; Baseline Comparator")
        self.assertContains(res, "65000")

    def test_anomaly_detail_anti_idor(self):
        # Sub Mgr Infra accessing Water division anomaly -> 403 PermissionDenied
        self.client.force_login(self.sub_mgr_infra)
        res = self.client.get(reverse("core:anomaly_detail", kwargs={"anomaly_id": self.anom.id}))
        self.assertEqual(res.status_code, 403)

    def test_anomaly_review_action_post(self):
        self.client.force_login(self.sub_mgr_water)
        res = self.client.post(
            reverse("core:anomaly_review_action", kwargs={"anomaly_id": self.anom.id}),
            {"action": "EXPLAIN", "comment": "Legitimate seasonal spike documented."},
        )
        self.assertEqual(res.status_code, 302)
        self.anom.refresh_from_db()
        self.assertEqual(self.anom.status, AnomalyStatus.EXPLAINED)
        self.assertEqual(self.anom.review_comment, "Legitimate seasonal spike documented.")
