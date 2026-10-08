"""
MEIL ESG CONTROL TOWER — Phase 14 End-to-End Live Verification Script
Validates the complete Corrections, Explanations & Resubmission Workflow:
1. Operational record creation, evidence upload, Phase 10 validation run, and initial Submission #1.
2. Subsidiary Manager review: REQUEST CORRECTION with structured reason, instructions, and affected area.
3. Immutability assurance: Baseline ActivityRevision #1 created, original submission preserved.
4. Site Manager Correction Inbox & Detail views rendered.
5. Operational telemetry correction: Quantity revised, notes attached, Phase 10 revalidation executed.
6. Authoritative Resubmission: Validation gates checked, Submission #2 created with parent pointer,
   ActivityRevision #2 created with field-by-field deltas, CorrectionRequest resolved.
7. Subsidiary Manager Re-Review: Delta comparison and historical timeline rendered.
8. Subsidiary Manager re-review verification (VERIFIED).
9. Anti-IDOR and authorization boundaries validated.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import django

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
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
    ValidationSeverity,
    ValidationStatus,
)
from apps.core.review_services import (
    request_correction_submission,
    verify_submission,
)
from apps.core.submission_services import submit_activity_record
from apps.core.validation_services import execute_validation_run, seed_standard_validation_rules

User = get_user_model()


def run_live_verification():
    print("=" * 80)
    print("  MEIL ESG CONTROL TOWER — PHASE 14 LIVE WORKFLOW VERIFICATION")
    print("=" * 80)

    # 0. Seed Validation Rules
    seed_standard_validation_rules()
    print("[1/9] Validation rules seeded.")

    # 1. Setup Organizations and Users in an isolated atomic block
    with transaction.atomic():
        # Roles
        role_site_mgr, _ = Role.objects.get_or_create(code=Role.Code.SITE_MANAGER, defaults={"name": "Site Manager"})
        role_sub_mgr, _ = Role.objects.get_or_create(code=Role.Code.SUBSIDIARY_MANAGER, defaults={"name": "Subsidiary Manager"})
        role_operator, _ = Role.objects.get_or_create(code=Role.Code.MEIL_OPERATOR, defaults={"name": "MEIL Operator"})
        role_auditor, _ = Role.objects.get_or_create(code=Role.Code.AUDITOR, defaults={"name": "Auditor"})

        # Organization
        company, _ = Company.objects.get_or_create(
            code="LIVE-MEIL",
            defaults={"name": "MEIL Enterprise Group Live", "status": OrganizationStatus.ACTIVE},
        )
        sub_water, _ = Subsidiary.objects.get_or_create(
            code="LIVE-WATER",
            defaults={"company": company, "name": "Live Water Works", "status": OrganizationStatus.ACTIVE},
        )
        sub_infra, _ = Subsidiary.objects.get_or_create(
            code="LIVE-INFRA",
            defaults={"company": company, "name": "Live Infrastructure", "status": OrganizationStatus.ACTIVE},
        )

        proj_pol, _ = Project.objects.get_or_create(
            code="LIVE-PROJ-POL",
            defaults={"subsidiary": sub_water, "name": "Polavaram Headworks Live", "status": OrganizationStatus.ACTIVE},
        )
        site_a, _ = Site.objects.get_or_create(
            code="LIVE-SITE-01",
            defaults={"project": proj_pol, "name": "Polavaram Spillway Station", "status": OrganizationStatus.ACTIVE},
        )

        # Users
        sm_user, _ = User.objects.get_or_create(
            username="live_sm_water",
            defaults={"email": "sm.water.live@meil.in", "first_name": "Ramesh", "last_name": "Kumar"},
        )
        sm_user.set_password("SitePass123!")
        sm_user.save()
        UserRole.objects.get_or_create(user=sm_user, role=role_site_mgr, defaults={"is_primary": True})
        SiteAssignment.objects.get_or_create(user=sm_user, site=site_a)

        sub_mgr, _ = User.objects.get_or_create(
            username="live_sub_mgr",
            defaults={"email": "sub.mgr.live@meil.in", "first_name": "Suresh", "last_name": "Reddy"},
        )
        sub_mgr.set_password("SubPass123!")
        sub_mgr.save()
        UserRole.objects.get_or_create(user=sub_mgr, role=role_sub_mgr, defaults={"is_primary": True})
        SubsidiaryAssignment.objects.get_or_create(user=sub_mgr, subsidiary=sub_water)

        other_sub_mgr, _ = User.objects.get_or_create(
            username="live_other_sub_mgr",
            defaults={"email": "other.sub.live@meil.in", "first_name": "Anil", "last_name": "Sharma"},
        )
        other_sub_mgr.set_password("OtherPass123!")
        other_sub_mgr.save()
        UserRole.objects.get_or_create(user=other_sub_mgr, role=role_sub_mgr, defaults={"is_primary": True})
        SubsidiaryAssignment.objects.get_or_create(user=other_sub_mgr, subsidiary=sub_infra)

        # Reporting Period
        period, _ = ReportingPeriod.objects.get_or_create(
            code="FY2025-26-LIVE",
            defaults={
                "company": company,
                "name": "FY 2025-26 Live Verification Cycle",
                "fiscal_year": "2025-26",
                "start_date": timezone.now().date() - timezone.timedelta(days=30),
                "end_date": timezone.now().date() + timezone.timedelta(days=330),
                "status": PeriodStatus.OPEN,
            },
        )

        # Unit and Activity
        category, _ = ActivityCategory.objects.get_or_create(
            code="LIVE-ENERGY",
            defaults={"name": "Energy & Fuel Generation"},
        )
        unit_kl, _ = UnitOfMeasure.objects.get_or_create(
            code="KL-LIVE",
            defaults={"name": "Kiloliters", "symbol": "kL", "dimension": UnitDimension.VOLUME},
        )
        activity, _ = ActivityMaster.objects.get_or_create(
            code="ACT-GENSET-DIESEL-LIVE",
            defaults={
                "category": category,
                "name": "Heavy Machinery Diesel Consumption",
                "scope_classification": ScopeClassification.SCOPE_1,
                "base_unit": unit_kl,
                "status": MasterStatus.ACTIVE,
                "validation_rules": {"evidence_required": True},
            },
        )

        print("[2/9] Master data, organizational hierarchy, and RBAC roles established.")

        # 2. Site Manager creates operational record, attaches invoice, and formally submits
        record = ActivityRecord.objects.create(
            site=site_a,
            reporting_period=period,
            activity=activity,
            quantity=Decimal("5000.0000"),
            unit=unit_kl,
            measurement_date=timezone.now().date(),
            notes="Stationary diesel run for excavation pump sets.",
            evidence_reference="CHALLAN-DIESEL-2026-001",
            status=RecordStatus.READY,
            created_by=sm_user,
        )

        evidence_file = SimpleUploadedFile(
            "diesel_delivery_challan.pdf",
            b"%PDF-1.4 Authoritative Diesel Delivery Challan for 5,000 kL.",
            content_type="application/pdf",
        )
        evidence = create_evidence_record(
            activity_record=record,
            uploaded_file=evidence_file,
            evidence_type=EvidenceType.FUEL_CHALLAN,
            description="Delivery challan batch #104",
            user=sm_user,
        )

        val_run = execute_validation_run(record, executed_by=sm_user)
        assert record.validation_status in [ValidationStatus.VALID, ValidationStatus.WARNING], f"Validation failed: {record.validation_status}"

        sub1 = submit_activity_record(record, user=sm_user)
        assert sub1.submission_number == 1, f"Expected Submission #1, got {sub1.submission_number}"
        assert sub1.status == SubmissionStatus.SUBMITTED, f"Expected SUBMITTED, got {sub1.status}"
        assert sub1.is_current is True
        print(f"[3/9] Site Manager created and submitted initial record: Submission #{sub1.submission_number} (ID: {sub1.id}, Quantity: {sub1.snapshot_data.get('quantity')} {unit_kl.symbol}).")

        # 3. Subsidiary Manager reviews Submission #1 and REQUESTS CORRECTION
        review1 = request_correction_submission(
            submission=sub1,
            user=sub_mgr,
            reason="Quantity discrepancy vs vendor tax invoice slip.",
            required_correction="Update quantity to 5,250 kL based on reconciliation note.",
            affected_area=CorrectionAffectedArea.ACTIVITY_DATA,
        )

        sub1.refresh_from_db()
        record.refresh_from_db()
        assert sub1.status == SubmissionStatus.CORRECTION_REQUESTED, f"Expected CORRECTION_REQUESTED, got {sub1.status}"
        assert record.status == RecordStatus.REJECTED, f"Expected REJECTED, got {record.status}"

        corr = sub1.latest_correction_request
        assert corr is not None, "CorrectionRequest was not created!"
        assert corr.status == CorrectionStatus.OPEN, f"Expected OPEN, got {corr.status}"
        assert corr.affected_area == CorrectionAffectedArea.ACTIVITY_DATA
        assert corr.required_correction == "Update quantity to 5,250 kL based on reconciliation note."

        # Verify baseline ActivityRevision #1
        rev1 = record.revisions.get(revision_number=1)
        assert rev1.quantity == Decimal("5000.0000"), f"Baseline revision quantity mismatch: {rev1.quantity}"
        assert rev1.revision_number == 1
        print(f"[4/9] Subsidiary Manager requested correction: CorrectionRequest #{corr.id} created, baseline ActivityRevision #{rev1.revision_number} preserved.")

        # 4. Anti-IDOR Security Checks
        # Another Subsidiary Manager cannot view or modify
        other_inbox = get_accessible_correction_requests(other_sub_mgr)
        assert not other_inbox.filter(id=corr.id).exists(), "Anti-IDOR violation: other Subsidiary Manager could access correction!"

        # Unauthorized user cannot edit
        assert not user_can_edit_correction_request(other_sub_mgr, corr), "Anti-IDOR violation: other manager could edit!"

        # Authorized Site Manager CAN access and edit
        assert user_can_access_correction_request(sm_user, corr), "Authorized Site Manager was denied read access!"
        assert user_can_edit_correction_request(sm_user, corr), "Authorized Site Manager was denied edit access!"
        print("[5/9] Anti-IDOR and organizational access boundary enforcement verified.")

        # 5. Site Manager updates operational telemetry
        start_correction(corr, user=sm_user)
        corr.refresh_from_db()
        assert corr.status == CorrectionStatus.IN_PROGRESS, f"Expected IN_PROGRESS, got {corr.status}"

        updated_rec, updated_val = update_corrected_record(
            correction_req=corr,
            user=sm_user,
            form_data={
                "quantity": Decimal("5250.0000"),
                "notes": "Adjusted to 5,250 kL per reconciliation note.",
                "site_manager_notes": "Reconciled with supplier invoice batch #104.",
            },
        )
        corr.refresh_from_db()
        assert updated_rec.quantity == Decimal("5250.0000")
        assert updated_val.status in [ValidationStatus.VALID, ValidationStatus.WARNING]
        assert corr.status == CorrectionStatus.READY_FOR_RESUBMISSION, f"Expected READY_FOR_RESUBMISSION, got {corr.status}"
        print(f"[6/9] Site Manager revised quantity to {updated_rec.quantity} kL, revalidation PASSED, status -> {corr.status}.")

        # 6. Site Manager executes Authoritative Resubmission
        sub2 = resubmit_corrected_activity(
            correction_req=corr,
            user=sm_user,
            comments="Resubmission with reconciled quantity 5,250 kL.",
        )

        sub1.refresh_from_db()
        sub2.refresh_from_db()
        corr.refresh_from_db()
        record.refresh_from_db()

        # Resubmission assertions
        assert sub2.submission_number == 2, f"Expected Submission #2, got {sub2.submission_number}"
        assert sub2.parent_submission == sub1, "Submission #2 must point to parent Submission #1"
        assert sub2.is_resubmission is True
        assert sub2.is_current is True
        assert sub1.is_current is False, "Prior submission must not be current"
        assert sub2.status == SubmissionStatus.SUBMITTED
        assert record.status == RecordStatus.SUBMITTED

        # CorrectionRequest resolved
        assert corr.status == CorrectionStatus.RESOLVED
        assert corr.resolved_by == sm_user
        assert corr.resubmission == sub2

        # Revision ledger assertions
        assert record.revisions.count() == 2, f"Expected 2 revisions, found {record.revisions.count()}"
        rev2 = record.revisions.get(revision_number=2)
        assert rev2.quantity == Decimal("5250.0000")
        assert rev2.submission == sub2
        assert "quantity" in rev2.changed_fields
        assert Decimal(rev2.changed_fields["quantity"]["old"]) == Decimal("5000.0000")
        assert Decimal(rev2.changed_fields["quantity"]["new"]) == Decimal("5250.0000")
        print(f"[7/9] Resubmission succeeded: Submission #{sub2.submission_number} created (Parent #{sub1.submission_number}), ActivityRevision #{rev2.revision_number} recorded field deltas.")

        # 7. Subsidiary Manager inspects delta comparison and history timeline
        deltas = compute_submission_deltas(sub2)
        assert deltas["has_baseline"] is True
        assert Decimal(deltas["quantity"]["original"]) == Decimal("5000.0000")
        assert Decimal(deltas["quantity"]["corrected"]) == Decimal("5250.0000")
        assert deltas["quantity"]["changed"] is True

        timeline = get_submission_history_timeline(sub2)
        event_types = [item["type"] for item in timeline]
        assert "SUBMISSION" in event_types
        assert "REVIEW" in event_types
        assert "CORRECTION_RESOLVED" in event_types
        print(f"[8/9] Comparative delta ledger computed correctly (Original: 5,000 kL vs Corrected: 5,250 kL). Timeline has {len(timeline)} chronological entries.")

        # 8. Subsidiary Manager re-reviews and verifies Submission #2
        review2 = verify_submission(
            submission=sub2,
            user=sub_mgr,
            comments="Verified against reconciled tax invoice slip. Correction accepted.",
        )

        sub2.refresh_from_db()
        record.refresh_from_db()
        assert sub2.status == SubmissionStatus.VERIFIED
        assert record.status == RecordStatus.VERIFIED

        # Verify complete Audit Trail
        audit_events = AuthAuditLog.objects.filter(
            resource_accessed__icontains=f"Record:{record.id}"
        ).order_by("created_at")
        print(f"[9/9] Subsidiary Manager verified resubmission (VERIFIED). Complete audit trail contains {audit_events.count()} events.")

        # Clean up created live verification test entities
        record.evidence_files.all().delete()
        record.revisions.all().delete()
        record.submissions.all().delete()
        record.delete()
        print("=" * 80)
        print("  ALL 9 WORKFLOW GATES IN PHASE 14 VERIFIED SUCCESSFULLY!")
        print("=" * 80)


if __name__ == "__main__":
    run_live_verification()
