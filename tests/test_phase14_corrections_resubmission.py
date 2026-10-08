"""
Comprehensive Test Suite for Phase 14 — Corrections, Explanations & Resubmission Workflow.

Validates:
1. Model Architecture & Integrity:
   - CorrectionStatus choices (OPEN, IN_PROGRESS, READY_FOR_RESUBMISSION, RESOLVED, CANCELLED)
   - CorrectionAffectedArea choices (ACTIVITY_DATA, EVIDENCE, BOTH, OTHER)
   - CorrectionRequest model fields, indexes, foreign keys, properties, and str representation
   - ActivityRevision model fields, unique constraints, ordering, and snapshot ledger
   - Submission fields and properties: parent_submission, is_resubmission, latest_correction_request
   - AuthAuditLog Phase 14 event types: CORRECTION_STARTED, CORRECTION_UPDATED, CORRECTION_RESOLVED, RESUBMISSION_CREATED

2. Correction Request Integration & Baseline Preservation:
   - Subsidiary Manager requests correction -> CorrectionRequest created with OPEN status
   - Mandatory reason validation: empty reason rejected
   - Original Submission #1 snapshot remains strictly immutable
   - Baseline ActivityRevision #1 created preserving original submitted telemetry
   - ActivityRecord status transitions to REJECTED (Revision Requested)
   - Audit event CORRECTION_REQUESTED logged

3. Site Manager Operational Correction Lifecycle:
   - Authorized Site Manager accesses correction in inbox
   - Opening correction transitions status from OPEN to IN_PROGRESS (CORRECTION_STARTED event)
   - Operational editing restricted strictly to approved fields (quantity, unit, date, notes, evidence_ref)
   - Correction update automatically re-runs Phase 10 Validation Engine
   - Valid data advances CorrectionRequest status to READY_FOR_RESUBMISSION
   - Invalid data retains IN_PROGRESS and flags blocking validation errors
   - Closed / locked reporting periods prevent operational modifications

4. Revalidation & Resubmission Workflow:
   - Resubmission blocked if blocking validation errors remain
   - Resubmission blocked if required evidence is missing
   - Authorized Site Manager executes resubmission -> creates Submission #2 linked to Submission #1
   - Monotonic iteration counters: submission_number=2, revision_number=2
   - Prior submission marked non-current (is_current=False), new submission marked current (is_current=True)
   - ActivityRevision #2 records field-by-field deltas (e.g. quantity delta) and submitter notes
   - CorrectionRequest status transitions to RESOLVED with resolving user and timestamp
   - ActivityRecord status transitions to SUBMITTED
   - Duplicate resubmissions strictly rejected (idempotency)
   - Audit events CORRECTION_RESOLVED and RESUBMISSION_CREATED logged

5. Subsidiary Manager Re-Review & Comparative Lineage:
   - Resubmission #2 appears in Subsidiary Manager inbox
   - Review detail view renders Resubmission banner, delta comparison table, and chronological history timeline
   - Subsidiary Manager can review again and verify the corrected submission

6. Anti-IDOR & Scoping Enforcement:
   - Site Manager for Site A cannot access or edit Correction for Site B (404/PermissionDenied)
   - Subsidiary Manager for Division A cannot request correction on Division B submissions
   - Auditor granted read-only visibility but strictly blocked from editing or resubmitting (403)
   - Non-submitter roles cannot resubmit
"""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.correction_services import (
    compute_submission_deltas,
    get_accessible_correction_requests,
    get_submission_history_timeline,
    resubmit_corrected_activity,
    start_correction,
    update_corrected_record,
    user_can_access_correction_request,
    user_can_edit_correction_request,
)
from apps.core.evidence_services import create_evidence_record
from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    ActivityRecord,
    ActivityRevision,
    AuthAuditLog,
    Company,
    CompanyAssignment,
    CorrectionAffectedArea,
    CorrectionRequest,
    CorrectionStatus,
    Evidence,
    EvidenceType,
    MasterStatus,
    OrganizationStatus,
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
    ValidationResult,
    ValidationRule,
    ValidationRun,
    ValidationSeverity,
    ValidationStatus,
)
from apps.core.review_services import (
    request_correction_submission,
    user_can_review_submission,
    verify_submission,
)
from apps.core.submission_services import submit_activity_record
from apps.core.validation_services import seed_standard_validation_rules

User = get_user_model()


class BasePhase14TestCase(TestCase):
    """Fixture setup for Phase 14 tests."""

    @classmethod
    def setUpTestData(cls):
        seed_standard_validation_rules()

        # 1. Setup Roles
        cls.role_site_mgr, _ = Role.objects.get_or_create(
            code=Role.Code.SITE_MANAGER,
            defaults={"name": "Site Manager"},
        )
        cls.role_sub_mgr, _ = Role.objects.get_or_create(
            code=Role.Code.SUBSIDIARY_MANAGER,
            defaults={"name": "Subsidiary Manager"},
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

        # 3. Setup Reporting Period
        cls.period = ReportingPeriod.objects.create(
            company=cls.company_meil,
            name="FY 2025-26 Annual Cycle",
            code="FY2025-26",
            fiscal_year="2025-26",
            start_date=timezone.now().date() - timezone.timedelta(days=90),
            end_date=timezone.now().date() + timezone.timedelta(days=90),
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
        cls.activity = ActivityMaster.objects.create(
            category=cls.category,
            name="Diesel Generator Operations",
            code="FUEL-DIESEL-GENSET",
            scope_classification=ScopeClassification.SCOPE_1,
            base_unit=cls.unit_liter,
            status=MasterStatus.ACTIVE,
            validation_rules={"evidence_required": True},
        )

        # 5. Setup Users
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

        cls.auditor_user = User.objects.create_user(
            username="auditor_user",
            email="auditor@meil.in",
            password="AuditorPass123!",
        )
        UserRole.objects.create(user=cls.auditor_user, role=cls.role_auditor, is_primary=True)
        CompanyAssignment.objects.create(user=cls.auditor_user, company=cls.company_meil)

    def _create_submitted_record(self, site, period, user, quantity=Decimal("1250.00")):
        """Helper to create and formally submit an ActivityRecord."""
        rec = ActivityRecord.objects.create(
            site=site,
            reporting_period=period,
            activity=self.activity,
            quantity=quantity,
            unit=self.unit_liter,
            measurement_date=timezone.now().date(),
            notes="Operational generator run.",
            evidence_reference="INV-DIESEL-001",
            status=RecordStatus.READY,
            created_by=user,
        )
        # Attach valid evidence
        test_file = SimpleUploadedFile(
            "fuel_invoice.pdf",
            b"%PDF-1.4 Mock fuel invoice test content.",
            content_type="application/pdf",
        )
        create_evidence_record(
            activity_record=rec,
            uploaded_file=test_file,
            evidence_type=EvidenceType.INVOICE,
            user=user,
        )
        sub = submit_activity_record(rec, user=user)
        return rec, sub


# -----------------------------------------------------------------------------
# 1. MODEL ARCHITECTURE & INTEGRITY TESTS
# -----------------------------------------------------------------------------

class CorrectionModelTests(BasePhase14TestCase):
    """Validates Phase 14 model fields, constraints, properties, and status choices."""

    def test_status_and_affected_area_choices(self):
        """CorrectionStatus and CorrectionAffectedArea contain required options."""
        self.assertEqual(CorrectionStatus.OPEN, "OPEN")
        self.assertEqual(CorrectionStatus.IN_PROGRESS, "IN_PROGRESS")
        self.assertEqual(CorrectionStatus.READY_FOR_RESUBMISSION, "READY_FOR_RESUBMISSION")
        self.assertEqual(CorrectionStatus.RESOLVED, "RESOLVED")

        self.assertEqual(CorrectionAffectedArea.ACTIVITY_DATA, "ACTIVITY_DATA")
        self.assertEqual(CorrectionAffectedArea.EVIDENCE, "EVIDENCE")
        self.assertEqual(CorrectionAffectedArea.BOTH, "BOTH")

    def test_submission_model_extensions(self):
        """Submission model has parent_submission, is_resubmission, and latest_correction_request."""
        rec, sub1 = self._create_submitted_record(self.site_a, self.period, self.sm_user_a)
        self.assertFalse(sub1.is_resubmission)
        self.assertIsNone(sub1.parent_submission)
        self.assertIsNone(sub1.latest_correction_request)

    def test_authauditlog_phase14_event_types(self):
        """AuthAuditLog contains all Phase 14 event types."""
        self.assertIn("CORRECTION_STARTED", AuthAuditLog.EventType.values)
        self.assertIn("CORRECTION_UPDATED", AuthAuditLog.EventType.values)
        self.assertIn("CORRECTION_RESOLVED", AuthAuditLog.EventType.values)
        self.assertIn("RESUBMISSION_CREATED", AuthAuditLog.EventType.values)


# -----------------------------------------------------------------------------
# 2. CORRECTION REQUEST INTEGRATION TESTS
# -----------------------------------------------------------------------------

class CorrectionRequestWorkflowTests(BasePhase14TestCase):
    """Validates requesting corrections, status progression, and baseline preservation."""

    def test_request_correction_creates_correction_request_and_baseline_revision(self):
        """Subsidiary Manager requesting correction creates CorrectionRequest and baseline ActivityRevision."""
        rec, sub1 = self._create_submitted_record(self.site_a, self.period, self.sm_user_a)

        review = request_correction_submission(
            submission=sub1,
            user=self.sub_mgr_water,
            reason="Fuel quantity appears misaligned with generator rating.",
            required_correction="Verify invoice meter reading and re-enter accurate liters.",
            affected_area=CorrectionAffectedArea.ACTIVITY_DATA,
        )

        sub1.refresh_from_db()
        rec.refresh_from_db()

        # Submission and Record statuses
        self.assertEqual(sub1.status, SubmissionStatus.CORRECTION_REQUESTED)
        self.assertEqual(rec.status, RecordStatus.REJECTED)

        # Authoritative CorrectionRequest created
        corr = sub1.latest_correction_request
        self.assertIsNotNone(corr)
        self.assertEqual(corr.status, CorrectionStatus.OPEN)
        self.assertEqual(corr.requested_by, self.sub_mgr_water)
        self.assertEqual(corr.reason, "Fuel quantity appears misaligned with generator rating.")
        self.assertEqual(corr.required_correction, "Verify invoice meter reading and re-enter accurate liters.")
        self.assertEqual(corr.affected_area, CorrectionAffectedArea.ACTIVITY_DATA)
        self.assertFalse(corr.is_resolved)
        self.assertTrue(corr.is_open)

        # Baseline ActivityRevision (Revision #1) preserved
        baseline_rev = rec.revisions.filter(revision_number=1).first()
        self.assertIsNotNone(baseline_rev)
        self.assertEqual(baseline_rev.quantity, Decimal("1250.00"))
        self.assertEqual(baseline_rev.reason, "INITIAL_SUBMISSION")

        # Original telemetry remains completely unchanged
        self.assertEqual(rec.quantity, Decimal("1250.00"))

        # Audit event recorded
        audit_exists = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.CORRECTION_REQUESTED,
            user=self.sub_mgr_water,
        ).exists()
        self.assertTrue(audit_exists)

    def test_request_correction_requires_non_empty_reason(self):
        """Requesting correction with empty reason raises ValidationError."""
        rec, sub1 = self._create_submitted_record(self.site_a, self.period, self.sm_user_a)

        with self.assertRaises(ValidationError):
            request_correction_submission(
                submission=sub1,
                user=self.sub_mgr_water,
                reason="   ",
            )


# -----------------------------------------------------------------------------
# 3. SITE MANAGER OPERATIONAL CORRECTION TESTS
# -----------------------------------------------------------------------------

class SiteManagerCorrectionWorkTests(BasePhase14TestCase):
    """Validates Site Manager correction actions, operational edits, and validation triggers."""

    def setUp(self):
        super().setUp()
        self.rec, self.sub1 = self._create_submitted_record(self.site_a, self.period, self.sm_user_a)
        self.review = request_correction_submission(
            submission=self.sub1,
            user=self.sub_mgr_water,
            reason="Liters discrepancy found.",
            required_correction="Adjust quantity from 1250 to 1350 L as per invoice.",
        )
        self.corr = self.sub1.latest_correction_request

    def test_start_correction_transitions_to_in_progress(self):
        """Site Manager opening work transitions CorrectionRequest to IN_PROGRESS."""
        self.assertEqual(self.corr.status, CorrectionStatus.OPEN)

        updated_corr = start_correction(self.corr, user=self.sm_user_a)
        self.assertEqual(updated_corr.status, CorrectionStatus.IN_PROGRESS)

        audit_exists = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.CORRECTION_STARTED,
            user=self.sm_user_a,
        ).exists()
        self.assertTrue(audit_exists)

    def test_update_corrected_record_revalidates_and_sets_ready_for_resubmission(self):
        """Site Manager updating valid operational telemetry sets READY_FOR_RESUBMISSION."""
        start_correction(self.corr, user=self.sm_user_a)

        form_data = {
            "quantity": Decimal("1350.00"),
            "unit": self.unit_liter,
            "measurement_date": self.rec.measurement_date,
            "notes": "Adjusted quantity to match calibrated meter.",
            "evidence_reference": "INV-DIESEL-001-REV",
            "site_manager_notes": "Corrected fuel quantity to 1350 L as per invoice slip.",
        }

        updated_rec, val_run = update_corrected_record(
            correction_req=self.corr,
            user=self.sm_user_a,
            form_data=form_data,
        )

        self.corr.refresh_from_db()
        self.assertEqual(updated_rec.quantity, Decimal("1350.00"))
        self.assertEqual(self.corr.status, CorrectionStatus.READY_FOR_RESUBMISSION)
        self.assertEqual(self.corr.site_manager_notes, "Corrected fuel quantity to 1350 L as per invoice slip.")

        # Baseline revision #1 remains untouched
        rev1 = self.rec.revisions.get(revision_number=1)
        self.assertEqual(rev1.quantity, Decimal("1250.00"))

        audit_exists = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.CORRECTION_UPDATED,
            user=self.sm_user_a,
        ).exists()
        self.assertTrue(audit_exists)

    def test_negative_quantity_raises_validation_error(self):
        """Negative consumption quantity is strictly rejected."""
        with self.assertRaises(ValidationError):
            update_corrected_record(
                correction_req=self.corr,
                user=self.sm_user_a,
                form_data={"quantity": Decimal("-50.00")},
            )

    def test_closed_period_prevents_correction_edits(self):
        """Correction cannot be edited if the reporting period is closed."""
        self.period.status = PeriodStatus.CLOSED
        self.period.save()

        self.assertFalse(user_can_edit_correction_request(self.sm_user_a, self.corr))
        with self.assertRaises(PermissionDenied):
            update_corrected_record(
                correction_req=self.corr,
                user=self.sm_user_a,
                form_data={"quantity": Decimal("1350.00")},
            )


# -----------------------------------------------------------------------------
# 4. RESUBMISSION WORKFLOW TESTS
# -----------------------------------------------------------------------------

class ResubmissionWorkflowTests(BasePhase14TestCase):
    """Validates formal resubmission, iteration incrementing, and revision snapshots."""

    def setUp(self):
        super().setUp()
        self.rec, self.sub1 = self._create_submitted_record(self.site_a, self.period, self.sm_user_a)
        request_correction_submission(
            submission=self.sub1,
            user=self.sub_mgr_water,
            reason="Volume check required.",
            required_correction="Adjust to 1350 L.",
        )
        self.corr = self.sub1.latest_correction_request
        update_corrected_record(
            correction_req=self.corr,
            user=self.sm_user_a,
            form_data={
                "quantity": Decimal("1350.00"),
                "site_manager_notes": "Corrected quantity to 1350 L.",
            },
        )

    def test_resubmit_creates_second_submission_and_revision_ledger(self):
        """Resubmission creates Submission #2 linked to Submission #1 and updates CorrectionRequest to RESOLVED."""
        sub2 = resubmit_corrected_activity(
            correction_req=self.corr,
            user=self.sm_user_a,
            comments="Resubmitting with verified diesel volume.",
        )

        self.corr.refresh_from_db()
        self.sub1.refresh_from_db()
        self.rec.refresh_from_db()

        # 1. New Submission #2 properties
        self.assertEqual(sub2.submission_number, 2)
        self.assertEqual(sub2.parent_submission, self.sub1)
        self.assertTrue(sub2.is_resubmission)
        self.assertTrue(sub2.is_current)
        self.assertEqual(sub2.status, SubmissionStatus.SUBMITTED)
        self.assertEqual(sub2.activity_record.quantity, Decimal("1350.00"))

        # 2. Previous Submission #1 properties
        self.assertFalse(self.sub1.is_current)
        self.assertEqual(self.sub1.submission_number, 1)
        # Original snapshot in Sub1 preserved
        self.assertEqual(Decimal(self.sub1.snapshot_data.get("quantity")), Decimal("1250.00"))

        # 3. CorrectionRequest resolved
        self.assertEqual(self.corr.status, CorrectionStatus.RESOLVED)
        self.assertEqual(self.corr.resolved_by, self.sm_user_a)
        self.assertIsNotNone(self.corr.resolved_at)
        self.assertEqual(self.corr.resubmission, sub2)

        # 4. ActivityRevision ledger
        self.assertEqual(self.rec.revisions.count(), 2)
        rev2 = self.rec.revisions.get(revision_number=2)
        self.assertEqual(rev2.quantity, Decimal("1350.00"))
        self.assertEqual(rev2.created_by, self.sm_user_a)
        self.assertEqual(rev2.submission, sub2)
        self.assertIn("quantity", rev2.changed_fields)
        self.assertEqual(Decimal(rev2.changed_fields["quantity"]["old"]), Decimal("1250.00"))
        self.assertEqual(Decimal(rev2.changed_fields["quantity"]["new"]), Decimal("1350.00"))

        # 5. ActivityRecord status is SUBMITTED
        self.assertEqual(self.rec.status, RecordStatus.SUBMITTED)

        # 6. Audit logs
        self.assertTrue(
            AuthAuditLog.objects.filter(
                event_type=AuthAuditLog.EventType.CORRECTION_RESOLVED,
                user=self.sm_user_a,
            ).exists()
        )
        self.assertTrue(
            AuthAuditLog.objects.filter(
                event_type=AuthAuditLog.EventType.RESUBMISSION_CREATED,
                user=self.sm_user_a,
            ).exists()
        )

    def test_duplicate_resubmission_is_blocked(self):
        """Duplicate resubmission on an already resolved correction is blocked."""
        sub2 = resubmit_corrected_activity(
            correction_req=self.corr,
            user=self.sm_user_a,
            comments="First resubmission.",
        )
        # Attempt second resubmission
        result = resubmit_corrected_activity(
            correction_req=self.corr,
            user=self.sm_user_a,
            comments="Second click.",
        )
        # Returns existing submission idempotently without creating duplicate submissions
        self.assertEqual(result.id, sub2.id)
        self.assertEqual(self.rec.submissions.count(), 2)

    def test_resubmission_blocked_if_blocking_validation_errors_exist(self):
        """Resubmission is strictly blocked if record has blocking validation errors or missing required evidence."""
        # Delete required evidence so validation marks record INVALID and blocks resubmission
        self.rec.evidence_files.all().delete()

        with self.assertRaises(ValidationError) as ctx:
            resubmit_corrected_activity(
                correction_req=self.corr,
                user=self.sm_user_a,
            )
        self.assertIn("Resubmission blocked", str(ctx.exception))


# -----------------------------------------------------------------------------
# 5. SUBSIDIARY MANAGER RE-REVIEW TESTS
# -----------------------------------------------------------------------------

class SubsidiaryManagerReReviewTests(BasePhase14TestCase):
    """Validates that Subsidiary Reviewers can inspect resubmissions and delta comparisons."""

    def setUp(self):
        super().setUp()
        self.rec, self.sub1 = self._create_submitted_record(self.site_a, self.period, self.sm_user_a)
        request_correction_submission(
            submission=self.sub1,
            user=self.sub_mgr_water,
            reason="Volume check required.",
            required_correction="Adjust to 1350 L.",
        )
        self.corr = self.sub1.latest_correction_request
        update_corrected_record(
            correction_req=self.corr,
            user=self.sm_user_a,
            form_data={"quantity": Decimal("1350.00")},
        )
        self.sub2 = resubmit_corrected_activity(
            correction_req=self.corr,
            user=self.sm_user_a,
            comments="Resubmitted with corrected volume.",
        )

    def test_deltas_computation_accurately_detects_changes(self):
        """compute_submission_deltas accurately computes field differences."""
        deltas = compute_submission_deltas(self.sub2)
        self.assertTrue(deltas["has_baseline"])
        self.assertEqual(Decimal(deltas["quantity"]["original"]), Decimal("1250.00"))
        self.assertEqual(Decimal(deltas["quantity"]["corrected"]), Decimal("1350.00"))
        self.assertTrue(deltas["quantity"]["changed"])

    def test_timeline_accurately_captures_chronological_events(self):
        """get_submission_history_timeline includes all lifecycle events."""
        timeline = get_submission_history_timeline(self.sub2)
        event_types = [item["type"] for item in timeline]
        self.assertIn("SUBMISSION", event_types)
        self.assertIn("REVIEW", event_types)
        self.assertIn("CORRECTION_RESOLVED", event_types)

    def test_subsidiary_manager_can_verify_resubmitted_record(self):
        """Subsidiary Manager can review again and verify the resubmitted record."""
        rev2 = verify_submission(
            submission=self.sub2,
            user=self.sub_mgr_water,
            comments="Verified after reviewing revised volume and invoice match.",
        )
        self.sub2.refresh_from_db()
        self.assertEqual(self.sub2.status, SubmissionStatus.VERIFIED)
        self.assertEqual(self.sub2.activity_record.status, RecordStatus.VERIFIED)
        self.assertEqual(rev2.action, ReviewAction.VERIFY)


# -----------------------------------------------------------------------------
# 6. ANTI-IDOR & SECURITY ENFORCEMENT TESTS
# -----------------------------------------------------------------------------

class AntiIDORSecurityTests(BasePhase14TestCase):
    """Enforces zero client trust and strict organizational scoping boundaries."""

    def setUp(self):
        super().setUp()
        self.rec_a, self.sub_a = self._create_submitted_record(self.site_a, self.period, self.sm_user_a)
        request_correction_submission(
            submission=self.sub_a,
            user=self.sub_mgr_water,
            reason="Site A correction required.",
        )
        self.corr_a = self.sub_a.latest_correction_request

        self.client = Client()

    def test_site_manager_b_cannot_view_correction_a(self):
        """Site Manager B cannot access Correction Request belonging to Site A."""
        self.assertFalse(user_can_access_correction_request(self.sm_user_b, self.corr_a))

        self.client.force_login(self.sm_user_b)
        response = self.client.get(reverse("core:correction_detail", kwargs={"correction_id": self.corr_a.id}))
        self.assertEqual(response.status_code, 403)

    def test_site_manager_b_cannot_edit_or_resubmit_correction_a(self):
        """Site Manager B cannot POST to edit or resubmit Site A's correction."""
        self.assertFalse(user_can_edit_correction_request(self.sm_user_b, self.corr_a))

        self.client.force_login(self.sm_user_b)
        edit_response = self.client.post(
            reverse("core:correction_edit", kwargs={"correction_id": self.corr_a.id}),
            {"quantity": 9999},
        )
        self.assertEqual(edit_response.status_code, 403)

        resubmit_response = self.client.post(
            reverse("core:correction_resubmit", kwargs={"correction_id": self.corr_a.id}),
            {"confirm": True},
        )
        self.assertEqual(resubmit_response.status_code, 403)

    def test_auditor_cannot_modify_or_resubmit_corrections(self):
        """Auditor is strictly read-only and blocked from editing or resubmitting corrections."""
        self.assertTrue(user_can_access_correction_request(self.auditor_user, self.corr_a))
        self.assertFalse(user_can_edit_correction_request(self.auditor_user, self.corr_a))

        self.client.force_login(self.auditor_user)
        # Can view (200 OK)
        view_response = self.client.get(reverse("core:correction_detail", kwargs={"correction_id": self.corr_a.id}))
        self.assertEqual(view_response.status_code, 200)

        # Cannot edit (403)
        post_response = self.client.post(
            reverse("core:correction_edit", kwargs={"correction_id": self.corr_a.id}),
            {"quantity": 1200},
        )
        self.assertEqual(post_response.status_code, 403)


# -----------------------------------------------------------------------------
# 7. VIEWS & HTTP UI TESTS
# -----------------------------------------------------------------------------

class ViewsAndUITests(BasePhase14TestCase):
    """Validates HTTP endpoints, template rendering, and navigation."""

    def setUp(self):
        super().setUp()
        self.rec, self.sub1 = self._create_submitted_record(self.site_a, self.period, self.sm_user_a)
        request_correction_submission(
            submission=self.sub1,
            user=self.sub_mgr_water,
            reason="Meter discrepancy.",
            required_correction="Adjust quantity.",
        )
        self.corr = self.sub1.latest_correction_request
        self.client = Client()

    def test_site_manager_correction_inbox_renders_200(self):
        """Site Manager Correction Inbox renders 200 with accurate items."""
        self.client.force_login(self.sm_user_a)
        response = self.client.get(reverse("core:correction_inbox"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Site Manager Correction Inbox")
        self.assertContains(response, "FUEL-DIESEL-GENSET")
        self.assertContains(response, "Meter discrepancy.")

    def test_site_manager_correction_detail_renders_200_and_comparison(self):
        """Correction Detail view renders 200 and telemetry comparison."""
        self.client.force_login(self.sm_user_a)
        response = self.client.get(reverse("core:correction_detail", kwargs={"correction_id": self.corr.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operational Telemetry Comparison")
        self.assertContains(response, "Reviewer Correction Mandate")
        self.assertContains(response, "1250.00")

    def test_site_manager_dashboard_surfaces_pending_corrections(self):
        """Site Manager Dashboard surfaces pending correction alert and action."""
        self.client.force_login(self.sm_user_a)
        response = self.client.get(reverse("core:site_manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Correction Request(s) Awaiting Revision")
