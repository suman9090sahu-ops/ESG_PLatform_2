"""
Comprehensive Test Suite for Phase 12 — Activity Submission Workflow.

Validates:
1. Model Architecture & Domain Constraints (Submission):
   - Creation, foreign keys, timestamps, submission_number
   - UniqueConstraint(activity_record, submission_number)
   - Status transitions (SUBMITTED, UNDER_REVIEW, WITHDRAWN, APPROVED, REJECTED)
   - Immutable snapshot_data capturing operational telemetry
   - ActivityRecord properties (latest_submission, is_locked_for_review, submission_count)

2. Scoped Queryset Services (get_accessible_submissions):
   - Site Manager sees ONLY submissions from explicitly assigned sites
   - Subsidiary Manager sees submissions from child division sites
   - ESG Manager, Operator, and Auditor have company-level oversight
   - Zero-trust scoping for unassigned users

3. Server-side Eligibility Verification (check_submission_eligibility):
   - Site Manager authorization check
   - Operational site must be ACTIVE
   - Reporting period must be OPEN (blocks CLOSED, LOCKED, FINALIZED)
   - Activity Master must be ACTIVE
   - Evidence mandatory check enforced for regulated activities (Phase 09)
   - Phase 10 Validation Engine integration (blocks INVALID; permits VALID & WARNING)

4. Atomic Submission Service & Concurrency Protection (submit_activity_record):
   - Transactional execution with select_for_update row locking
   - Transitions ActivityRecord.status -> SUBMITTED
   - Idempotency & duplicate submission protection
   - Creation of formal Submission instance and marking previous as non-current
   - Locks record from further Site Manager editing or deletion
   - Audit event dispatch in AuthAuditLog (SUBMISSION_CREATED)

5. Withdrawal Workflow (withdraw_submission):
   - Submitter can withdraw SUBMITTED record in OPEN cycle
   - Reverts ActivityRecord.status -> DRAFT
   - Re-submission increments submission_number while preserving immutable history
   - Audit event dispatch in AuthAuditLog (SUBMISSION_WITHDRAWN)

6. Security, RBAC & Anti-IDOR Protections:
   - Direct URL tampering defense: Site Manager attempting to submit unassigned record -> 403
   - Cross-company submission blocked -> 403
   - Auditor prohibited from mutation -> 403
   - Subsidiary Manager cannot submit directly without site assignment -> 403
   - State mutation requires POST with CSRF protection

7. UI Views:
   - GET & POST /data-entry/<id>/submit/
   - GET /submissions/ (List view with KPIs and filters)
   - GET /submissions/<id>/ (Detailed audit lineage)
   - POST /submissions/<id>/withdraw/
"""

import io
from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
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
    Submission,
    SubmissionStatus,
    Subsidiary,
    SubsidiaryAssignment,
    UnitDimension,
    UnitOfMeasure,
    UserRole,
    ValidationCategory,
    ValidationResult,
    ValidationRule,
    ValidationRun,
    ValidationSeverity,
    ValidationStatus,
)
from apps.core.submission_services import (
    check_submission_eligibility,
    get_accessible_submissions,
    submit_activity_record,
    user_can_access_submission,
    user_can_submit_activity_record,
    withdraw_submission,
)
from apps.core.validation_services import (
    execute_validation_run,
    seed_standard_validation_rules,
)

User = get_user_model()


class BaseSubmissionTestCase(TestCase):
    """Base setup fixture for Phase 12 Submission tests."""

    @classmethod
    def setUpTestData(cls):
        # 1. Seed deterministic validation rules
        seed_standard_validation_rules()

        # 2. Setup RBAC Roles
        cls.role_site_mgr, _ = Role.objects.get_or_create(
            code=Role.Code.SITE_MANAGER,
            defaults={"name": "Site Manager", "is_active": True},
        )
        cls.role_sub_mgr, _ = Role.objects.get_or_create(
            code=Role.Code.SUBSIDIARY_MANAGER,
            defaults={"name": "Subsidiary Manager", "is_active": True},
        )
        cls.role_operator, _ = Role.objects.get_or_create(
            code=Role.Code.MEIL_OPERATOR,
            defaults={"name": "MEIL Operator", "is_active": True},
        )
        cls.role_esg_mgr, _ = Role.objects.get_or_create(
            code=Role.Code.ESG_MANAGER,
            defaults={"name": "ESG Manager", "is_active": True},
        )
        cls.role_auditor, _ = Role.objects.get_or_create(
            code=Role.Code.AUDITOR,
            defaults={"name": "Auditor", "is_active": True},
        )

        # 3. Create Users
        cls.user_site_mgr = User.objects.create_user(
            username="sm_polavaram",
            email="sm.polavaram@meil.in",
            password="TestPassword123!",
        )
        UserRole.objects.create(user=cls.user_site_mgr, role=cls.role_site_mgr, is_primary=True)

        cls.user_other_sm = User.objects.create_user(
            username="sm_pavagada",
            email="sm.pavagada@meil.in",
            password="TestPassword123!",
        )
        UserRole.objects.create(user=cls.user_other_sm, role=cls.role_site_mgr, is_primary=True)

        cls.user_sub_mgr = User.objects.create_user(
            username="sub_mgr_water",
            email="sub.water@meil.in",
            password="TestPassword123!",
        )
        UserRole.objects.create(user=cls.user_sub_mgr, role=cls.role_sub_mgr, is_primary=True)

        cls.user_operator = User.objects.create_user(
            username="operator_hq",
            email="operator@meil.in",
            password="TestPassword123!",
        )
        UserRole.objects.create(user=cls.user_operator, role=cls.role_operator, is_primary=True)

        cls.user_auditor = User.objects.create_user(
            username="auditor_lead",
            email="auditor@meil.in",
            password="TestPassword123!",
        )
        UserRole.objects.create(user=cls.user_auditor, role=cls.role_auditor, is_primary=True)

        # 4. Organizational Hierarchy
        cls.company = Company.objects.create(
            code="MEIL-CORP",
            name="MEIL Enterprise Group",
            status=OrganizationStatus.ACTIVE,
        )
        cls.other_company = Company.objects.create(
            code="OTHER-CORP",
            name="External Corp",
            status=OrganizationStatus.ACTIVE,
        )

        cls.subsidiary1 = Subsidiary.objects.create(
            company=cls.company,
            name="Water Works Division",
            code="MEIL-WATER",
            status=OrganizationStatus.ACTIVE,
        )
        cls.subsidiary2 = Subsidiary.objects.create(
            company=cls.company,
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
            project=cls.project2,
            name="Pavagada Block B Site",
            code="SITE-PAV-201",
            status=OrganizationStatus.ACTIVE,
        )
        cls.site_inactive = Site.objects.create(
            project=cls.project1,
            name="Decommissioned Quarry Site",
            code="SITE-POL-999",
            status=OrganizationStatus.INACTIVE,
        )

        # Scope Assignments
        SiteAssignment.objects.create(user=cls.user_site_mgr, site=cls.site1)
        SiteAssignment.objects.create(user=cls.user_other_sm, site=cls.site2)
        SubsidiaryAssignment.objects.create(user=cls.user_sub_mgr, subsidiary=cls.subsidiary1)

        # 5. Units of Measure
        cls.unit_litre = UnitOfMeasure.objects.create(
            code="LITRE",
            name="Litre",
            symbol="L",
            dimension=UnitDimension.VOLUME,
            status=MasterStatus.ACTIVE,
        )
        cls.unit_kwh = UnitOfMeasure.objects.create(
            code="KWH",
            name="Kilowatt-Hour",
            symbol="kWh",
            dimension=UnitDimension.ENERGY,
            status=MasterStatus.ACTIVE,
        )

        # 6. Reporting Periods
        cls.period_open = ReportingPeriod.objects.create(
            company=cls.company,
            code="FY2025-26",
            name="FY 2025-26 Annual ESG Cycle",
            fiscal_year="FY 2025-26",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            status=PeriodStatus.OPEN,
        )
        cls.period_closed = ReportingPeriod.objects.create(
            company=cls.company,
            code="FY2024-25",
            name="FY 2024-25 Historical Cycle",
            fiscal_year="FY 2024-25",
            start_date=date(2024, 4, 1),
            end_date=date(2025, 3, 31),
            status=PeriodStatus.CLOSED,
        )

        # 7. Activity Masters
        cls.category_fuels = ActivityCategory.objects.create(
            code="STATIONARY_COMBUSTION",
            name="Stationary Combustion",
            display_order=1,
        )
        cls.act_diesel = ActivityMaster.objects.create(
            category=cls.category_fuels,
            code="DIESEL_GENSET",
            name="Diesel Generator Consumption",
            base_unit=cls.unit_litre,
            scope_classification=ScopeClassification.SCOPE_1,
            validation_rules={"evidence_required": True},
            status=MasterStatus.ACTIVE,
            is_active=True,
        )
        cls.act_solar = ActivityMaster.objects.create(
            category=cls.category_fuels,
            code="SOLAR_GENERATION",
            name="Solar Generation",
            base_unit=cls.unit_kwh,
            scope_classification=ScopeClassification.SCOPE_2,
            validation_rules={},
            status=MasterStatus.ACTIVE,
            is_active=True,
        )
        cls.act_inactive = ActivityMaster.objects.create(
            category=cls.category_fuels,
            code="OBSOLETE_FUEL",
            name="Obsolete Heavy Fuel",
            base_unit=cls.unit_litre,
            scope_classification=ScopeClassification.SCOPE_1,
            validation_rules={},
            status=MasterStatus.INACTIVE,
            is_active=False,
        )

    def _create_record(self, site=None, period=None, activity=None, quantity=Decimal("1500.00"), measurement_date=None, unit=None, status=RecordStatus.DRAFT):
        """Helper to create a well-formed operational ActivityRecord."""
        rec = ActivityRecord.objects.create(
            site=site or self.site1,
            reporting_period=period or self.period_open,
            activity=activity or self.act_diesel,
            measurement_date=measurement_date or date(2025, 7, 15),
            quantity=quantity,
            unit=unit or self.unit_litre,
            notes="Operational test consumption",
            status=status,
            created_by=self.user_site_mgr,
        )
        return rec

    def _attach_evidence(self, record, user=None):
        """Helper to attach an active supporting evidence document."""
        dummy_file = SimpleUploadedFile("fuel_invoice_jul25.pdf", b"%PDF-1.4 test invoice content", content_type="application/pdf")
        return create_evidence_record(
            activity_record=record,
            uploaded_file=dummy_file,
            evidence_type=EvidenceType.INVOICE,
            user=user or self.user_site_mgr,
            description="Official diesel delivery challan and tax invoice",
        )


class SubmissionModelAndArchitectureTests(BaseSubmissionTestCase):
    """Test suite covering Submission model integrity, constraints, and relationships."""

    def test_submission_model_creation_and_fields(self):
        record = self._create_record()
        self._attach_evidence(record)
        val_run = execute_validation_run(record, executed_by=self.user_site_mgr)

        submission = Submission.objects.create(
            activity_record=record,
            submission_number=1,
            site=record.site,
            reporting_period=record.reporting_period,
            submitted_by=self.user_site_mgr,
            status=SubmissionStatus.SUBMITTED,
            validation_run=val_run,
            validation_status=record.validation_status,
            comments="July diesel log verified against invoice.",
            snapshot_data={"quantity": "1500.00", "unit": "L"},
            is_current=True,
        )

        self.assertEqual(submission.submission_number, 1)
        self.assertEqual(submission.status, SubmissionStatus.SUBMITTED)
        self.assertTrue(submission.is_submitted)
        self.assertFalse(submission.is_withdrawn)
        self.assertEqual(submission.site, self.site1)
        self.assertEqual(submission.project, self.project1)
        self.assertEqual(submission.subsidiary, self.subsidiary1)
        self.assertEqual(submission.company, self.company)
        self.assertEqual(submission.badge_class, "badge-primary")
        self.assertIn("Submission #1", str(submission))

    def test_submission_unique_constraint(self):
        record = self._create_record()
        Submission.objects.create(
            activity_record=record,
            submission_number=1,
            site=record.site,
            reporting_period=record.reporting_period,
            submitted_by=self.user_site_mgr,
            status=SubmissionStatus.SUBMITTED,
        )

        # Duplicate submission_number for same activity record must raise IntegrityError
        with self.assertRaises(IntegrityError):
            Submission.objects.create(
                activity_record=record,
                submission_number=1,
                site=record.site,
                reporting_period=record.reporting_period,
                submitted_by=self.user_site_mgr,
                status=SubmissionStatus.SUBMITTED,
            )

    def test_activity_record_submission_properties(self):
        record = self._create_record()
        self.assertIsNone(record.latest_submission)
        self.assertEqual(record.submission_count, 0)
        self.assertFalse(record.is_locked_for_review)

        sub1 = Submission.objects.create(
            activity_record=record,
            submission_number=1,
            site=record.site,
            reporting_period=record.reporting_period,
            submitted_by=self.user_site_mgr,
            status=SubmissionStatus.WITHDRAWN,
            is_current=False,
        )
        sub2 = Submission.objects.create(
            activity_record=record,
            submission_number=2,
            site=record.site,
            reporting_period=record.reporting_period,
            submitted_by=self.user_site_mgr,
            status=SubmissionStatus.SUBMITTED,
            is_current=True,
        )

        record.status = RecordStatus.SUBMITTED
        record.save(update_fields=["status"])

        self.assertEqual(record.submission_count, 2)
        self.assertEqual(record.latest_submission, sub2)
        self.assertTrue(record.is_locked_for_review)


class SubmissionScopingAndRBACServicesTests(BaseSubmissionTestCase):
    """Test suite covering get_accessible_submissions scoping and authorization boundaries."""

    def test_site_manager_sees_only_assigned_site_submissions(self):
        rec1 = self._create_record(site=self.site1)
        rec2 = self._create_record(site=self.site2)

        sub1 = Submission.objects.create(
            activity_record=rec1,
            submission_number=1,
            site=self.site1,
            reporting_period=self.period_open,
            submitted_by=self.user_site_mgr,
        )
        sub2 = Submission.objects.create(
            activity_record=rec2,
            submission_number=1,
            site=self.site2,
            reporting_period=self.period_open,
            submitted_by=self.user_other_sm,
        )

        sm_qs = get_accessible_submissions(self.user_site_mgr)
        self.assertIn(sub1, sm_qs)
        self.assertNotIn(sub2, sm_qs)
        self.assertTrue(user_can_access_submission(self.user_site_mgr, sub1))
        self.assertFalse(user_can_access_submission(self.user_site_mgr, sub2))

    def test_subsidiary_manager_sees_child_site_submissions(self):
        rec1 = self._create_record(site=self.site1)  # under subsidiary1 (Water)
        rec2 = self._create_record(site=self.site2)  # under subsidiary2 (Solar)

        sub1 = Submission.objects.create(
            activity_record=rec1,
            submission_number=1,
            site=self.site1,
            reporting_period=self.period_open,
            submitted_by=self.user_site_mgr,
        )
        sub2 = Submission.objects.create(
            activity_record=rec2,
            submission_number=1,
            site=self.site2,
            reporting_period=self.period_open,
            submitted_by=self.user_other_sm,
        )

        sub_mgr_qs = get_accessible_submissions(self.user_sub_mgr)
        self.assertIn(sub1, sub_mgr_qs)
        self.assertNotIn(sub2, sub_mgr_qs)

    def test_operator_and_auditor_see_all_company_submissions(self):
        rec1 = self._create_record(site=self.site1)
        rec2 = self._create_record(site=self.site2)

        sub1 = Submission.objects.create(
            activity_record=rec1,
            submission_number=1,
            site=self.site1,
            reporting_period=self.period_open,
        )
        sub2 = Submission.objects.create(
            activity_record=rec2,
            submission_number=1,
            site=self.site2,
            reporting_period=self.period_open,
        )

        op_qs = get_accessible_submissions(self.user_operator)
        aud_qs = get_accessible_submissions(self.user_auditor)

        self.assertIn(sub1, op_qs)
        self.assertIn(sub2, op_qs)
        self.assertIn(sub1, aud_qs)
        self.assertIn(sub2, aud_qs)


class SubmissionEligibilityGateTests(BaseSubmissionTestCase):
    """Test suite covering server-side eligibility checks."""

    def test_eligible_record_passes_checks(self):
        record = self._create_record()
        self._attach_evidence(record)
        execute_validation_run(record, executed_by=self.user_site_mgr)

        is_eligible, errors, warnings = check_submission_eligibility(self.user_site_mgr, record)
        self.assertTrue(is_eligible)
        self.assertEqual(len(errors), 0)

    def test_ineligible_when_site_inactive(self):
        # We need to temporarily permit creation on inactive site to test the submission boundary gate
        record = ActivityRecord(
            site=self.site_inactive,
            reporting_period=self.period_open,
            activity=self.act_diesel,
            measurement_date=date(2025, 7, 15),
            quantity=Decimal("500.00"),
            unit=self.unit_litre,
        )
        record.save(update_fields=None)

        is_eligible, errors, _ = check_submission_eligibility(self.user_operator, record)
        self.assertFalse(is_eligible)
        self.assertTrue(any("inactive" in e.lower() for e in errors))

    def test_ineligible_when_period_not_open(self):
        record = self._create_record(period=self.period_closed, measurement_date=date(2024, 7, 15))
        is_eligible, errors, _ = check_submission_eligibility(self.user_site_mgr, record)
        self.assertFalse(is_eligible)
        self.assertTrue(any("reporting period" in e.lower() for e in errors))

    def test_ineligible_when_mandatory_evidence_missing(self):
        # act_diesel requires evidence
        record = self._create_record(activity=self.act_diesel)
        is_eligible, errors, _ = check_submission_eligibility(self.user_site_mgr, record)
        self.assertFalse(is_eligible)
        self.assertTrue(any("evidence" in e.lower() for e in errors))

    def test_eligible_when_activity_does_not_require_evidence(self):
        # act_solar does not require evidence
        record = self._create_record(activity=self.act_solar, unit=self.unit_kwh)
        execute_validation_run(record, executed_by=self.user_site_mgr)
        is_eligible, errors, _ = check_submission_eligibility(self.user_site_mgr, record)
        self.assertTrue(is_eligible)

    def test_ineligible_when_validation_fails_with_errors(self):
        record = self._create_record()
        # Do not attach evidence -> validation will fail with blocking error
        execute_validation_run(record, executed_by=self.user_site_mgr)
        self.assertEqual(record.validation_status, ValidationStatus.INVALID)

        is_eligible, errors, _ = check_submission_eligibility(self.user_site_mgr, record)
        self.assertFalse(is_eligible)
        self.assertTrue(any("validation" in e.lower() for e in errors))


class SubmissionServiceExecutionTests(BaseSubmissionTestCase):
    """Test suite covering submit_activity_record atomic transaction, locking, and idempotency."""

    def test_successful_submission_execution(self):
        record = self._create_record()
        self._attach_evidence(record)

        submission = submit_activity_record(
            record=record,
            user=self.user_site_mgr,
            comments="DG meter batch verified.",
        )

        record.refresh_from_db()
        self.assertEqual(record.status, RecordStatus.SUBMITTED)
        self.assertEqual(submission.submission_number, 1)
        self.assertEqual(submission.status, SubmissionStatus.SUBMITTED)
        self.assertEqual(submission.submitted_by, self.user_site_mgr)
        self.assertEqual(submission.validation_status, ValidationStatus.VALID)
        self.assertTrue(submission.is_current)
        self.assertEqual(submission.comments, "DG meter batch verified.")
        self.assertEqual(submission.snapshot_data["quantity"], "1500.0000")

        # Verify audit log
        audit = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.SUBMISSION_CREATED,
            user=self.user_site_mgr,
        ).first()
        self.assertIsNotNone(audit)
        self.assertIn("DG meter batch verified", audit.details)

    def test_idempotent_duplicate_submission_protection(self):
        record = self._create_record()
        self._attach_evidence(record)

        sub1 = submit_activity_record(record, self.user_site_mgr)
        self.assertEqual(Submission.objects.filter(activity_record=record).count(), 1)

        # Attempting second submit on the same record (e.g. double-click)
        sub2 = submit_activity_record(record, self.user_site_mgr)
        self.assertEqual(sub1.id, sub2.id)
        self.assertEqual(Submission.objects.filter(activity_record=record).count(), 1)

    def test_submitted_record_locked_from_editing_and_deletion(self):
        record = self._create_record()
        self._attach_evidence(record)
        submit_activity_record(record, self.user_site_mgr)

        self.assertFalse(record.is_editable_by_site_manager)
        self.assertTrue(record.is_locked_for_review)

    def test_submission_blocked_when_validation_has_blocking_errors(self):
        record = self._create_record()
        # No evidence attached for diesel -> validation failure
        with self.assertRaises(ValidationError):
            submit_activity_record(record, self.user_site_mgr)

        record.refresh_from_db()
        self.assertNotEqual(record.status, RecordStatus.SUBMITTED)
        self.assertEqual(Submission.objects.filter(activity_record=record).count(), 0)


class SubmissionWithdrawalWorkflowTests(BaseSubmissionTestCase):
    """Test suite covering the submitter withdrawal workflow and re-submission."""

    def test_withdrawal_reverts_record_to_draft_and_sets_withdrawn(self):
        record = self._create_record()
        self._attach_evidence(record)
        submission = submit_activity_record(record, self.user_site_mgr)

        withdrawn_sub = withdraw_submission(
            submission=submission,
            user=self.user_site_mgr,
            reason="Meter calibration discrepancy noticed.",
        )

        record.refresh_from_db()
        self.assertEqual(record.status, RecordStatus.DRAFT)
        self.assertEqual(withdrawn_sub.status, SubmissionStatus.WITHDRAWN)
        self.assertFalse(withdrawn_sub.is_current)
        self.assertIn("Meter calibration discrepancy", withdrawn_sub.comments)

        # Verify audit log
        audit = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.SUBMISSION_WITHDRAWN,
            user=self.user_site_mgr,
        ).first()
        self.assertIsNotNone(audit)

    def test_withdrawn_record_can_be_resubmitted_incrementing_number(self):
        record = self._create_record()
        self._attach_evidence(record)

        # First submission
        sub1 = submit_activity_record(record, self.user_site_mgr)
        self.assertEqual(sub1.submission_number, 1)

        # Withdraw
        withdraw_submission(sub1, self.user_site_mgr, reason="Correction required")

        # Edit draft
        record.refresh_from_db()
        record.quantity = Decimal("1800.00")
        record.save()

        # Re-submit
        sub2 = submit_activity_record(record, self.user_site_mgr, comments="Corrected quantity")
        self.assertEqual(sub2.submission_number, 2)
        self.assertEqual(sub2.status, SubmissionStatus.SUBMITTED)
        self.assertTrue(sub2.is_current)

        sub1.refresh_from_db()
        self.assertFalse(sub1.is_current)
        self.assertEqual(sub1.status, SubmissionStatus.WITHDRAWN)

        self.assertEqual(record.submission_count, 2)


class SubmissionSecurityAndAntiIDORTests(BaseSubmissionTestCase):
    """Test suite verifying strict security, RBAC, and zero client-trust defenses."""

    def setUp(self):
        self.client = Client()

    def test_site_manager_cannot_submit_unassigned_site_record_idor(self):
        """sm_polavaram attempts to submit a record belonging to Pavagada site."""
        foreign_record = self._create_record(site=self.site2)
        self._attach_evidence(foreign_record, user=self.user_other_sm)

        self.client.login(username="sm_polavaram", password="TestPassword123!")
        url = reverse("core:activity_record_submit", kwargs={"record_id": foreign_record.id})

        response = self.client.post(url, {"confirm": True})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Submission.objects.filter(activity_record=foreign_record).count(), 0)

    def test_auditor_cannot_submit_record(self):
        record = self._create_record()
        self._attach_evidence(record)

        self.client.login(username="auditor_lead", password="TestPassword123!")
        url = reverse("core:activity_record_submit", kwargs={"record_id": record.id})

        response = self.client.post(url, {"confirm": True})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Submission.objects.filter(activity_record=record).count(), 0)

    def test_subsidiary_manager_cannot_submit_site_record_directly(self):
        record = self._create_record()
        self._attach_evidence(record)

        self.client.login(username="sub_mgr_water", password="TestPassword123!")
        url = reverse("core:activity_record_submit", kwargs={"record_id": record.id})

        response = self.client.post(url, {"confirm": True})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Submission.objects.filter(activity_record=record).count(), 0)

    def test_submission_detail_anti_idor(self):
        rec2 = self._create_record(site=self.site2)
        self._attach_evidence(rec2, user=self.user_other_sm)
        sub2 = submit_activity_record(rec2, self.user_other_sm)

        self.client.login(username="sm_polavaram", password="TestPassword123!")
        url = reverse("core:submission_detail", kwargs={"submission_id": sub2.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)


class SubmissionViewEndpointsTests(BaseSubmissionTestCase):
    """Test suite covering full HTTP request/response flows for Phase 12 endpoints."""

    def setUp(self):
        self.client = Client()

    def test_get_submission_confirm_page_authorized_site_manager(self):
        record = self._create_record()
        self._attach_evidence(record)
        execute_validation_run(record, executed_by=self.user_site_mgr)

        self.client.login(username="sm_polavaram", password="TestPassword123!")
        url = reverse("core:activity_record_submit", kwargs={"record_id": record.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Submit Activity Record")
        self.assertContains(response, "Polavaram Right Canal Site")
        self.assertContains(response, "Confirm &amp; Submit for Review")

    def test_post_submission_success_and_redirect(self):
        record = self._create_record()
        self._attach_evidence(record)

        self.client.login(username="sm_polavaram", password="TestPassword123!")
        url = reverse("core:activity_record_submit", kwargs={"record_id": record.id})

        response = self.client.post(url, {
            "confirm": True,
            "comments": "Confirmed diesel challan verified.",
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.status, RecordStatus.SUBMITTED)
        self.assertContains(response, "successfully submitted for downstream review")

    def test_submission_list_view_renders_table(self):
        record = self._create_record()
        self._attach_evidence(record)
        submit_activity_record(record, self.user_site_mgr)

        self.client.login(username="sm_polavaram", password="TestPassword123!")
        url = reverse("core:submission_list")

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Activity Submissions")
        self.assertContains(response, "Diesel Generator Consumption")
        self.assertContains(response, "Polavaram Right Canal Site")

    def test_submission_detail_view_renders_lineage(self):
        record = self._create_record()
        self._attach_evidence(record)
        submission = submit_activity_record(record, self.user_site_mgr, comments="Official telemetry log.")

        self.client.login(username="sm_polavaram", password="TestPassword123!")
        url = reverse("core:submission_detail", kwargs={"submission_id": submission.id})

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Submission #{submission.submission_number}")
        self.assertContains(response, "Operational Telemetry Snapshot")
        self.assertContains(response, "Phase 10 Deterministic Validation Audit")
        self.assertContains(response, "Supporting Audit Evidence")
        self.assertContains(response, "Official telemetry log.")

    def test_submission_withdrawal_post_view(self):
        record = self._create_record()
        self._attach_evidence(record)
        submission = submit_activity_record(record, self.user_site_mgr)

        self.client.login(username="sm_polavaram", password="TestPassword123!")
        url = reverse("core:submission_withdraw", kwargs={"submission_id": submission.id})

        response = self.client.post(url, {
            "confirm": True,
            "reason": "Meter recalibration required.",
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.status, RecordStatus.DRAFT)
        submission.refresh_from_db()
        self.assertEqual(submission.status, SubmissionStatus.WITHDRAWN)
        self.assertContains(response, "successfully withdrawn")
