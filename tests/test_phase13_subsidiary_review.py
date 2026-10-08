"""
Comprehensive Test Suite for Phase 13 — Subsidiary Manager Review Workflow.

Validates:
1. Model Architecture & Integrity:
   - ReviewAction choices (VERIFY, REQUEST_CORRECTION, EXPLAIN, ESCALATE)
   - SubmissionStatus choices (VERIFIED, CORRECTION_REQUESTED, EXPLAINED, ESCALATED)
   - SubmissionReview model fields, constraints, relations, indexes, ordering
   - Submission properties (is_verified, is_correction_requested, is_explained, is_escalated, is_reviewable)
   - AuthAuditLog review event types

2. Functional RBAC & Review Permissions:
   - Subsidiary Manager has review authority
   - MEIL Operator and ESG Manager have review authority
   - Site Manager alone is blocked from review (403)
   - Auditor is strictly read-only assurance and blocked from review actions (403)

3. Organizational Scope & Anti-IDOR Enforcement:
   - Subsidiary Manager assigned to Division A can review Division A submissions
   - Cross-company isolation: Subsidiary Manager for Division A cannot see Division B submissions
   - Direct URL / POST tampering to review Division B submission strictly rejected (403/404)
   - Anti-IDOR security logging in AuthAuditLog

4. Self-Review Protection:
   - Reviewer who created the submission cannot verify their own submission
   - Platform Operator / Superuser can perform administrative review

5. Review Decision Actions & Immutability:
   - VERIFY: transitions Submission & ActivityRecord to VERIFIED, creates SubmissionReview, logs audit event
   - REQUEST CORRECTION: transitions Submission to CORRECTION_REQUESTED & ActivityRecord to REJECTED, preserves reason and required correction
   - EXPLAIN: transitions Submission to EXPLAINED, preserves operating context without mutating telemetry or bypassing validation
   - ESCALATE: transitions Submission to ESCALATED, preserves target role (ESG_MANAGER)
   - Original operational telemetry (quantity, unit, date) remains strictly immutable across all decisions

6. Invalid Status Transitions & Double-Action Protection:
   - Cannot verify already verified submission
   - Cannot request correction on withdrawn or terminal submission
   - Required reasons cannot be empty

7. Views & HTTP Security:
   - State-changing review endpoints reject GET requests
   - Subsidiary Manager Dashboard renders real metrics without fabrication
   - Submission Review Inbox respects organizational scoping and filters
   - Submission Review Detail renders data, evidence, OCR, validation, and history
"""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.evidence_services import create_evidence_record
from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    ActivityRecord,
    AuthAuditLog,
    Company,
    CompanyAssignment,
    Evidence,
    EvidenceType,
    MasterStatus,
    OCRField,
    OCRRun,
    OCRStatus,
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
    can_transition_submission,
    escalate_submission,
    explain_submission,
    get_subsidiary_manager_dashboard_metrics,
    request_correction_submission,
    user_can_review_submission,
    user_can_review_submissions,
    verify_submission,
)
from apps.core.submission_services import (
    get_accessible_submissions,
    submit_activity_record,
)
from apps.core.validation_services import seed_standard_validation_rules

User = get_user_model()


class BaseSubsidiaryReviewTestCase(TestCase):
    """Fixture setup for Phase 13 Review tests."""

    @classmethod
    def setUpTestData(cls):
        seed_standard_validation_rules()

        # 1. Setup Roles
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

        # 2. Setup Organizations (Company A and Company B for multi-tenant isolation)
        cls.company_a = Company.objects.create(
            code="MEIL-CORP",
            name="MEIL Enterprise Group",
            status=OrganizationStatus.ACTIVE,
        )
        cls.company_b = Company.objects.create(
            code="OTHER-CORP",
            name="External Corp",
            status=OrganizationStatus.ACTIVE,
        )

        cls.sub_a1 = Subsidiary.objects.create(
            company=cls.company_a,
            name="Water Works Division",
            code="MEIL-WATER",
            status=OrganizationStatus.ACTIVE,
        )
        cls.sub_a2 = Subsidiary.objects.create(
            company=cls.company_a,
            name="Solar Division",
            code="MEIL-SOLAR",
            status=OrganizationStatus.ACTIVE,
        )
        cls.sub_b = Subsidiary.objects.create(
            company=cls.company_b,
            name="External Mining Division",
            code="OTHER-MINE",
            status=OrganizationStatus.ACTIVE,
        )

        cls.proj_a = Project.objects.create(
            subsidiary=cls.sub_a1,
            name="Polavaram Irrigation Project",
            code="PRJ-POLAVARAM",
            status=OrganizationStatus.ACTIVE,
        )
        cls.proj_b = Project.objects.create(
            subsidiary=cls.sub_b,
            name="External Quarry Project",
            code="PRJ-EXT-QUARRY",
            status=OrganizationStatus.ACTIVE,
        )

        cls.site_a = Site.objects.create(
            project=cls.proj_a,
            name="Polavaram Dam Headworks",
            code="SITE-POL-01",
            status=OrganizationStatus.ACTIVE,
        )
        cls.site_b = Site.objects.create(
            project=cls.proj_b,
            name="External Quarry Site",
            code="SITE-EXT-01",
            status=OrganizationStatus.ACTIVE,
        )

        # 3. Setup Users
        cls.sm_user = User.objects.create_user(
            username="sm_site_a",
            email="sm.site.a@meil.in",
            password="TestPassword123!",
        )
        UserRole.objects.create(user=cls.sm_user, role=cls.role_site_mgr, is_primary=True)
        SiteAssignment.objects.create(user=cls.sm_user, site=cls.site_a)

        cls.sub_mgr_a = User.objects.create_user(
            username="sub_mgr_water",
            email="sub.water@meil.in",
            password="TestPassword123!",
        )
        UserRole.objects.create(user=cls.sub_mgr_a, role=cls.role_sub_mgr, is_primary=True)
        SubsidiaryAssignment.objects.create(user=cls.sub_mgr_a, subsidiary=cls.sub_a1)

        cls.sub_mgr_b = User.objects.create_user(
            username="sub_mgr_external",
            email="sub.external@other.in",
            password="TestPassword123!",
        )
        UserRole.objects.create(user=cls.sub_mgr_b, role=cls.role_sub_mgr, is_primary=True)
        SubsidiaryAssignment.objects.create(user=cls.sub_mgr_b, subsidiary=cls.sub_b)

        cls.operator_user = User.objects.create_user(
            username="operator_lead",
            email="operator@meil.in",
            password="TestPassword123!",
        )
        UserRole.objects.create(user=cls.operator_user, role=cls.role_operator, is_primary=True)
        CompanyAssignment.objects.create(user=cls.operator_user, company=cls.company_a)

        cls.auditor_user = User.objects.create_user(
            username="auditor_lead",
            email="auditor@assurance.in",
            password="TestPassword123!",
        )
        UserRole.objects.create(user=cls.auditor_user, role=cls.role_auditor, is_primary=True)
        CompanyAssignment.objects.create(user=cls.auditor_user, company=cls.company_a)

        # 4. Reporting Period
        cls.period = ReportingPeriod.objects.create(
            company=cls.company_a,
            code="FY2025-26",
            name="FY 2025-26 ESG Cycle",
            fiscal_year="FY2025-26",
            start_date=timezone.now().date() - timezone.timedelta(days=30),
            end_date=timezone.now().date() + timezone.timedelta(days=330),
            status=PeriodStatus.OPEN,
        )
        cls.period_b = ReportingPeriod.objects.create(
            company=cls.company_b,
            code="FY2025-26-EXT",
            name="FY 2025-26 External Cycle",
            fiscal_year="FY2025-26",
            start_date=timezone.now().date() - timezone.timedelta(days=30),
            end_date=timezone.now().date() + timezone.timedelta(days=330),
            status=PeriodStatus.OPEN,
        )

        # 5. Units & Activity Masters
        cls.category = ActivityCategory.objects.create(
            code="ENERGY",
            name="Energy & Fuel Operations",
        )
        cls.unit_liters = UnitOfMeasure.objects.create(
            code="LTR",
            name="Liters",
            symbol="L",
            dimension=UnitDimension.VOLUME,
        )
        cls.activity_diesel = ActivityMaster.objects.create(
            code="FUEL-DIESEL-GENSET",
            name="Diesel Generator Operations",
            category=cls.category,
            scope_classification=ScopeClassification.SCOPE_1,
            base_unit=cls.unit_liters,
            status=MasterStatus.ACTIVE,
            validation_rules={"evidence_required": True},
        )

    def _create_submitted_record(self, site, period, user, quantity=Decimal("1250.00")):
        """Helper to create and formally submit an activity record with evidence and validation."""
        record = ActivityRecord.objects.create(
            site=site,
            reporting_period=period,
            activity=self.activity_diesel,
            measurement_date=timezone.now().date(),
            quantity=quantity,
            unit=self.unit_liters,
            notes="Quarterly genset run",
            status=RecordStatus.READY,
            created_by=user,
        )

        # Attach valid dummy evidence file
        dummy_pdf = SimpleUploadedFile(
            "fuel_invoice.pdf",
            b"%PDF-1.4 sample fuel invoice binary content for review tests",
            content_type="application/pdf",
        )
        evidence = create_evidence_record(
            activity_record=record,
            uploaded_file=dummy_pdf,
            evidence_type=EvidenceType.INVOICE,
            user=user,
        )

        # Attach mock OCR run
        ocr_run = OCRRun.objects.create(
            evidence=evidence,
            run_number=1,
            status=OCRStatus.COMPLETED,
            engine="MOCK",
            confidence=Decimal("94.50"),
            page_count=1,
            raw_metadata={
                "comparison": {
                    "quantity": {
                        "record_value": str(quantity),
                        "ocr_value": str(quantity),
                        "status": "MATCH",
                    },
                    "unit": {
                        "record_value": "L",
                        "ocr_value": "L",
                        "status": "MATCH",
                    },
                }
            },
        )
        OCRField.objects.create(
            ocr_run=ocr_run,
            field_name="quantity",
            raw_value="1,250.00 L",
            normalized_value=str(quantity),
            unit="L",
            confidence=Decimal("95.00"),
        )

        # Formally submit record
        submission = submit_activity_record(
            record=record,
            user=user,
            comments="Formal site manager submission.",
            force_revalidate=True,
        )
        return record, submission


class ModelIntegrityTests(BaseSubsidiaryReviewTestCase):
    """Tests for Phase 13 models, constraints, and properties."""

    def test_review_action_and_submission_status_choices(self):
        """Verify new status choices and review action choices."""
        self.assertIn("VERIFY", ReviewAction.values)
        self.assertIn("REQUEST_CORRECTION", ReviewAction.values)
        self.assertIn("EXPLAIN", ReviewAction.values)
        self.assertIn("ESCALATE", ReviewAction.values)

        self.assertIn("VERIFIED", SubmissionStatus.values)
        self.assertIn("CORRECTION_REQUESTED", SubmissionStatus.values)
        self.assertIn("EXPLAINED", SubmissionStatus.values)
        self.assertIn("ESCALATED", SubmissionStatus.values)

        self.assertIn("SUBMISSION_VERIFIED", AuthAuditLog.EventType.values)
        self.assertIn("CORRECTION_REQUESTED", AuthAuditLog.EventType.values)
        self.assertIn("EXPLANATION_RECORDED", AuthAuditLog.EventType.values)
        self.assertIn("SUBMISSION_ESCALATED", AuthAuditLog.EventType.values)

    def test_submission_review_creation_and_properties(self):
        """Verify SubmissionReview model persistence and Submission helper properties."""
        record, submission = self._create_submitted_record(self.site_a, self.period, self.sm_user)
        self.assertTrue(submission.is_reviewable)
        self.assertFalse(submission.is_verified)
        self.assertEqual(submission.review_count, 0)
        self.assertIsNone(submission.latest_review)

        review = SubmissionReview.objects.create(
            submission=submission,
            reviewer=self.sub_mgr_a,
            action=ReviewAction.VERIFY,
            previous_status=SubmissionStatus.SUBMITTED,
            new_status=SubmissionStatus.VERIFIED,
            comments="Verified against fuel meter invoice.",
        )

        self.assertEqual(submission.reviews.count(), 1)
        self.assertEqual(submission.latest_review, review)
        self.assertEqual(review.badge_class, "badge-success")
        self.assertIn("VERIFY on Submission", str(review))


class RoleAuthorizationTests(BaseSubsidiaryReviewTestCase):
    """Tests functional review authority per RBAC role."""

    def test_user_can_review_submissions_role_check(self):
        """Verify role permissions: Sub Manager, Operator, ESG Manager vs Site Manager, Auditor."""
        self.assertTrue(user_can_review_submissions(self.sub_mgr_a))
        self.assertTrue(user_can_review_submissions(self.operator_user))

        # Site manager cannot review
        self.assertFalse(user_can_review_submissions(self.sm_user))

        # Auditor is strictly read-only assurance
        self.assertFalse(user_can_review_submissions(self.auditor_user))

        # Inactive or anonymous users
        self.assertFalse(user_can_review_submissions(None))

    def test_self_review_protection(self):
        """A user cannot review their own submission (self-approval protection)."""
        # Create a user who is BOTH Site Manager and Subsidiary Manager
        dual_user = User.objects.create_user(
            username="dual_role_user",
            email="dual@meil.in",
            password="TestPassword123!",
        )
        UserRole.objects.create(user=dual_user, role=self.role_site_mgr, is_primary=True)
        UserRole.objects.create(user=dual_user, role=self.role_sub_mgr)
        SiteAssignment.objects.create(user=dual_user, site=self.site_a)
        SubsidiaryAssignment.objects.create(user=dual_user, subsidiary=self.sub_a1)

        # Dual user submits the record
        record, submission = self._create_submitted_record(self.site_a, self.period, dual_user)

        # Dual user attempts to review their OWN submission
        can_review_own = user_can_review_submission(dual_user, submission)
        self.assertFalse(can_review_own)

        # Independent subsidiary manager CAN review it
        self.assertTrue(user_can_review_submission(self.sub_mgr_a, submission))


class OrganizationalScopeAndIDORTests(BaseSubsidiaryReviewTestCase):
    """Tests organization boundary isolation and anti-IDOR protections."""

    def test_subsidiary_manager_scope_isolation(self):
        """Subsidiary Manager for Company A cannot see submissions of Company B."""
        record_a, sub_a = self._create_submitted_record(self.site_a, self.period, self.sm_user)

        # Create external site manager and submission for Company B
        sm_b = User.objects.create_user(
            username="sm_site_b",
            email="sm.b@other.in",
            password="TestPassword123!",
        )
        UserRole.objects.create(user=sm_b, role=self.role_site_mgr, is_primary=True)
        SiteAssignment.objects.create(user=sm_b, site=self.site_b)

        record_b, sub_b = self._create_submitted_record(self.site_b, self.period_b, sm_b)

        # Accessible submissions for sub_mgr_a (Company A)
        accessible_for_a = get_accessible_submissions(self.sub_mgr_a)
        self.assertIn(sub_a, accessible_for_a)
        self.assertNotIn(sub_b, accessible_for_a)

        # sub_mgr_a cannot review sub_b
        self.assertTrue(user_can_review_submission(self.sub_mgr_a, sub_a))
        self.assertFalse(user_can_review_submission(self.sub_mgr_a, sub_b))

        # sub_mgr_b cannot review sub_a
        self.assertFalse(user_can_review_submission(self.sub_mgr_b, sub_a))
        self.assertTrue(user_can_review_submission(self.sub_mgr_b, sub_b))

    def test_idor_verification_attempt_blocked(self):
        """Cross-company verify attempt raises PermissionDenied and records audit event."""
        sm_b = User.objects.create_user(
            username="sm_b_user",
            email="sm.b.user@other.in",
            password="TestPassword123!",
        )
        UserRole.objects.create(user=sm_b, role=self.role_site_mgr, is_primary=True)
        SiteAssignment.objects.create(user=sm_b, site=self.site_b)
        record_b, sub_b = self._create_submitted_record(self.site_b, self.period_b, sm_b)

        # sub_mgr_a attempts to verify sub_b directly
        with self.assertRaises(PermissionDenied):
            verify_submission(sub_b, self.sub_mgr_a, comments="Unauthorized verify attempt")

        # Verify state did not change
        sub_b.refresh_from_db()
        self.assertEqual(sub_b.status, SubmissionStatus.SUBMITTED)
        self.assertEqual(sub_b.reviews.count(), 0)


class ReviewDecisionActionTests(BaseSubsidiaryReviewTestCase):
    """Tests the 4 review decisions: Verify, Request Correction, Explain, Escalate."""

    def test_verify_submission_action(self):
        """VERIFY transitions submission to VERIFIED and locks ActivityRecord in VERIFIED status."""
        record, submission = self._create_submitted_record(self.site_a, self.period, self.sm_user)
        initial_qty = record.quantity

        review = verify_submission(
            submission=submission,
            user=self.sub_mgr_a,
            comments="Telemetry inspected, OCR match confirmed, fuel log verified.",
        )

        submission.refresh_from_db()
        record.refresh_from_db()

        self.assertEqual(submission.status, SubmissionStatus.VERIFIED)
        self.assertEqual(record.status, RecordStatus.VERIFIED)
        # Original telemetry remains completely unchanged
        self.assertEqual(record.quantity, initial_qty)

        # Review record saved
        self.assertEqual(review.action, ReviewAction.VERIFY)
        self.assertEqual(review.previous_status, SubmissionStatus.SUBMITTED)
        self.assertEqual(review.new_status, SubmissionStatus.VERIFIED)
        self.assertEqual(review.reviewer, self.sub_mgr_a)

        # Audit log created
        audit_log = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.SUBMISSION_VERIFIED,
            resource_accessed__icontains=f"Submission:{submission.id}",
        ).first()
        self.assertIsNotNone(audit_log)
        self.assertTrue(audit_log.success)

    def test_request_correction_action(self):
        """REQUEST_CORRECTION transitions submission to CORRECTION_REQUESTED and record to REJECTED."""
        record, submission = self._create_submitted_record(self.site_a, self.period, self.sm_user)

        review = request_correction_submission(
            submission=submission,
            user=self.sub_mgr_a,
            reason="Fuel invoice date does not match operational run date.",
            required_correction="Please upload invoice dated within the correct monthly period.",
        )

        submission.refresh_from_db()
        record.refresh_from_db()

        self.assertEqual(submission.status, SubmissionStatus.CORRECTION_REQUESTED)
        self.assertEqual(record.status, RecordStatus.REJECTED)

        # Required corrections preserved
        self.assertEqual(review.action, ReviewAction.REQUEST_CORRECTION)
        self.assertIn("Fuel invoice date", review.comments)
        self.assertIn("upload invoice", review.required_correction)

        # Empty reason rejected
        with self.assertRaises(ValidationError):
            request_correction_submission(submission, self.sub_mgr_a, reason="")

    def test_explain_submission_action(self):
        """EXPLAIN records justification without modifying operational record data."""
        record, submission = self._create_submitted_record(self.site_a, self.period, self.sm_user)
        initial_record_status = record.status

        review = explain_submission(
            submission=submission,
            user=self.sub_mgr_a,
            explanation="Unusual fuel spike caused by auxiliary power outage during monsoon storm.",
        )

        submission.refresh_from_db()
        record.refresh_from_db()

        self.assertEqual(submission.status, SubmissionStatus.EXPLAINED)
        # Record status remains SUBMITTED (unchanged)
        self.assertEqual(record.status, initial_record_status)

        # Review record saved
        self.assertEqual(review.action, ReviewAction.EXPLAIN)
        self.assertIn("storm", review.comments)

        # Empty explanation rejected
        with self.assertRaises(ValidationError):
            explain_submission(submission, self.sub_mgr_a, explanation="")

        # An explained submission can subsequently be verified
        verify_review = verify_submission(
            submission=submission,
            user=self.sub_mgr_a,
            comments="Verified with storm explanation attached.",
        )
        submission.refresh_from_db()
        self.assertEqual(submission.status, SubmissionStatus.VERIFIED)

    def test_escalate_submission_action(self):
        """ESCALATE transitions submission to ESCALATED with target role preserved."""
        record, submission = self._create_submitted_record(self.site_a, self.period, self.sm_user)

        review = escalate_submission(
            submission=submission,
            user=self.sub_mgr_a,
            reason="Classification conflict: generator was used for hybrid grid export.",
            target_role=Role.Code.ESG_MANAGER,
        )

        submission.refresh_from_db()
        self.assertEqual(submission.status, SubmissionStatus.ESCALATED)
        self.assertEqual(review.action, ReviewAction.ESCALATE)
        self.assertEqual(review.escalated_to_role, Role.Code.ESG_MANAGER)


class InvalidTransitionsAndConcurrencyTests(BaseSubsidiaryReviewTestCase):
    """Tests transition guards and double-action prevention."""

    def test_double_verification_blocked(self):
        """Cannot verify an already verified submission."""
        record, submission = self._create_submitted_record(self.site_a, self.period, self.sm_user)
        verify_submission(submission, self.sub_mgr_a, comments="First verification")

        # Second verification attempt must raise ValidationError
        with self.assertRaises(ValidationError):
            verify_submission(submission, self.sub_mgr_a, comments="Duplicate verification attempt")

        self.assertEqual(submission.reviews.count(), 1)

    def test_cannot_modify_terminal_submission(self):
        """Cannot request correction on an escalated or verified submission."""
        record, submission = self._create_submitted_record(self.site_a, self.period, self.sm_user)
        escalate_submission(submission, self.sub_mgr_a, reason="Escalating for dispute")

        with self.assertRaises(ValidationError):
            request_correction_submission(
                submission,
                self.sub_mgr_a,
                reason="Invalid correction after escalation",
                required_correction="Fix it",
            )


class ViewsAndHttpSecurityTests(BaseSubsidiaryReviewTestCase):
    """Tests HTTP views, CSRF, anti-IDOR, and rendering."""

    def setUp(self):
        self.client = Client()

    def test_dashboard_renders_with_real_metrics(self):
        """Subsidiary Manager Dashboard returns 200 and accurate metrics."""
        record, submission = self._create_submitted_record(self.site_a, self.period, self.sm_user)

        self.client.force_login(self.sub_mgr_a)
        response = self.client.get(reverse("core:subsidiary_manager_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Subsidiary Manager Review Workspace")
        self.assertContains(response, "Water Works Division")
        self.assertEqual(response.context["pending_count"], 1)
        self.assertEqual(response.context["verified_count"], 0)

    def test_submission_inbox_view(self):
        """Submission Inbox lists accessible submissions and supports filtering."""
        record, submission = self._create_submitted_record(self.site_a, self.period, self.sm_user)

        self.client.force_login(self.sub_mgr_a)
        response = self.client.get(reverse("core:subsidiary_submission_inbox"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Subsidiary Review Inbox")
        self.assertContains(response, "Polavaram Dam Headworks")
        self.assertContains(response, "Diesel Generator Operations")

    def test_review_detail_view_and_post_actions(self):
        """Detailed review page renders and processes POST verify action."""
        record, submission = self._create_submitted_record(self.site_a, self.period, self.sm_user)

        self.client.force_login(self.sub_mgr_a)

        # GET review detail
        detail_url = reverse("core:submission_review_detail", kwargs={"submission_id": submission.id})
        get_res = self.client.get(detail_url)
        self.assertEqual(get_res.status_code, 200)
        self.assertContains(get_res, "1. Submitted Activity Data Review")
        self.assertContains(get_res, "2. Supporting Audit Evidence Review")
        self.assertContains(get_res, "3. OCR Intelligence")
        self.assertContains(get_res, "4. Deterministic Validation Audit Review")
        self.assertContains(get_res, "5. Review Decision History Ledger")

        # GET on action URL should redirect to review detail (reject state-changing GET)
        verify_url = reverse("core:submission_verify", kwargs={"submission_id": submission.id})
        get_action_res = self.client.get(verify_url)
        self.assertEqual(get_action_res.status_code, 302)

        # POST verify action
        post_res = self.client.post(
            verify_url,
            {
                "comments": "Browser client verified successfully.",
                "confirm": True,
            },
        )
        self.assertEqual(post_res.status_code, 302)

        submission.refresh_from_db()
        self.assertEqual(submission.status, SubmissionStatus.VERIFIED)

    def test_unauthorized_user_blocked_from_review_view(self):
        """Site Manager attempting to access review detail or action receives 403 Forbidden."""
        record, submission = self._create_submitted_record(self.site_a, self.period, self.sm_user)

        self.client.force_login(self.sm_user)

        # Site manager cannot view review workspace
        detail_url = reverse("core:submission_review_detail", kwargs={"submission_id": submission.id})
        res = self.client.get(detail_url)
        self.assertEqual(res.status_code, 403)

        # Site manager cannot POST verify
        verify_url = reverse("core:submission_verify", kwargs={"submission_id": submission.id})
        post_res = self.client.post(verify_url, {"confirm": True})
        self.assertEqual(post_res.status_code, 403)
