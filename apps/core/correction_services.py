"""
Correction, Explanation, Revision & Resubmission Workflow Services for MEIL ESG CONTROL TOWER.

Fulfills Phase 14 Requirements:
- Authoritative Correction Request Lifecycle Management (OPEN -> IN_PROGRESS -> READY_FOR_RESUBMISSION -> RESOLVED)
- Scoped Queryset Access & Object-Level Authorization (Zero client trust, anti-IDOR)
- Permanent Historical Preservation: Original submission snapshot, review decision, and telemetry are never overwritten
- Authoritative ActivityRevision Ledger preserving field deltas, comments, and state snapshots
- Mandatory Revalidation via Phase 10 Validation Engine before Resubmission
- Controlled Resubmission Cycle creating new versioned Submission linked to parent submission
- Subsidiary Manager Historical Review & Comparison Diff Engine
- Atomic Transactions, Concurrency & Row-Level Locking
- Audited Compliance Lineage Logging (AuthAuditLog events)
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.core.auth_services import log_auth_event
from apps.core.data_entry_services import user_can_access_activity_record
from apps.core.models import (
    ActivityRecord,
    ActivityRevision,
    AuthAuditLog,
    CorrectionAffectedArea,
    CorrectionRequest,
    CorrectionStatus,
    EvidenceStatus,
    MasterStatus,
    OrganizationStatus,
    PeriodStatus,
    RecordStatus,
    ReviewAction,
    Role,
    Submission,
    SubmissionReview,
    SubmissionStatus,
    UnitOfMeasure,
    ValidationRun,
    ValidationStatus,
)
from apps.core.scope_services import (
    get_accessible_companies,
    get_accessible_sites,
    get_accessible_subsidiaries,
    user_can_access_site,
)
from apps.core.validation_services import execute_validation_run

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. SCOPED CORRECTION REQUEST QUERYSETS & AUTHORIZATION
# -----------------------------------------------------------------------------

def get_accessible_correction_requests(user):
    """
    Returns QuerySet of CorrectionRequest instances accessible to the user based on RBAC scope.

    Strict organizational boundaries:
    - SITE_MANAGER: Confined exclusively to correction requests for assigned operational sites.
    - SUBSIDIARY_MANAGER: Confined to correction requests under child sites of assigned subsidiaries.
    - MEIL_OPERATOR / ESG_MANAGER / AUDITOR / Superuser: Confined to enterprise scope.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return CorrectionRequest.objects.none()

    base_qs = CorrectionRequest.objects.select_related(
        "activity_record",
        "activity_record__activity",
        "activity_record__activity__category",
        "activity_record__unit",
        "activity_record__site",
        "activity_record__site__project",
        "activity_record__site__project__subsidiary",
        "activity_record__site__project__subsidiary__company",
        "activity_record__reporting_period",
        "submission",
        "review",
        "requested_by",
        "resolved_by",
        "resubmission",
    ).prefetch_related(
        "activity_record__evidence_files",
    )

    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        accessible_companies = get_accessible_companies(user)
        return base_qs.filter(
            activity_record__site__project__subsidiary__company__in=accessible_companies
        ).order_by("-created_at")

    if user.has_role(Role.Code.SUBSIDIARY_MANAGER):
        accessible_subs = get_accessible_subsidiaries(user)
        return base_qs.filter(
            activity_record__site__project__subsidiary__in=accessible_subs
        ).order_by("-created_at")

    if user.has_role(Role.Code.SITE_MANAGER):
        accessible_sites = get_accessible_sites(user)
        return base_qs.filter(
            activity_record__site__in=accessible_sites
        ).order_by("-created_at")

    return CorrectionRequest.objects.none()


def user_can_access_correction_request(user, correction_req: CorrectionRequest) -> bool:
    """
    Evaluates whether a user has read authorization for a specific CorrectionRequest.
    """
    if not user or not user.is_authenticated or not user.is_active or not correction_req:
        return False

    return get_accessible_correction_requests(user).filter(id=correction_req.id).exists()


def user_can_edit_correction_request(
    user,
    correction_req: CorrectionRequest,
    allow_resolved: bool = False,
) -> bool:
    """
    Evaluates whether a user has authorization to edit/correct operational data
    for a given CorrectionRequest.

    Rules:
    - User must have SITE_MANAGER, MEIL_OPERATOR, ESG_MANAGER role (or superuser).
    - AUDITOR: Strictly prohibited (read-only assurance).
    - SUBSIDIARY_MANAGER alone cannot edit site operational data.
    - Site must belong to user's assigned sites.
    - CorrectionRequest must be in an editable status (OPEN, IN_PROGRESS, READY_FOR_RESUBMISSION).
    - Reporting Period must be OPEN and allow data modification.
    """
    if not user or not user.is_authenticated or not user.is_active or not correction_req:
        return False

    if user.has_role(Role.Code.AUDITOR) and not (
        user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR)
    ):
        return False

    if user.has_role(Role.Code.SUBSIDIARY_MANAGER) and not (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.SITE_MANAGER)
    ):
        return False

    has_permitted_role = (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.SITE_MANAGER)
        or user.has_role(Role.Code.ESG_MANAGER)
    )
    if not has_permitted_role:
        return False

    record = correction_req.activity_record
    if not user_can_access_site(user, record.site):
        return False

    if not user_can_access_activity_record(user, record):
        return False

    # Status check: Resolved or cancelled correction requests cannot be edited
    valid_statuses = [
        CorrectionStatus.OPEN,
        CorrectionStatus.IN_PROGRESS,
        CorrectionStatus.READY_FOR_RESUBMISSION,
    ]
    if allow_resolved:
        valid_statuses.append(CorrectionStatus.RESOLVED)

    if correction_req.status not in valid_statuses:
        return False

    # Reporting period boundary check
    period = record.reporting_period
    if not period or period.status != PeriodStatus.OPEN or not period.allows_data_modification:
        return False

    return True


# -----------------------------------------------------------------------------
# 2. REVISION LEDGER & BASELINE SNAPSHOT CREATION
# -----------------------------------------------------------------------------

def ensure_initial_activity_revision(
    record: ActivityRecord,
    submission: Optional[Submission] = None,
    created_by=None,
) -> ActivityRevision:
    """
    Ensures an immutable baseline ActivityRevision (Revision #1) exists for an ActivityRecord.
    Preserves the initial submission state before any subsequent correction cycles take place.
    """
    existing_initial = record.revisions.filter(revision_number=1).first()
    if existing_initial:
        return existing_initial

    creator = created_by or (submission.submitted_by if submission else record.created_by)
    snapshot = submission.snapshot_data if submission and submission.snapshot_data else {}

    revision = ActivityRevision.objects.create(
        activity_record=record,
        revision_number=1,
        submission=submission,
        created_by=creator,
        reason="INITIAL_SUBMISSION",
        comments="Initial activity record submission baseline.",
        quantity=record.quantity,
        unit=record.unit,
        measurement_date=record.measurement_date,
        notes=record.notes or "",
        evidence_reference=record.evidence_reference or "",
        validation_status=record.validation_status,
        changed_fields={},
        snapshot_data=snapshot,
    )
    return revision


# -----------------------------------------------------------------------------
# 3. CORRECTION REQUEST CREATION (INTEGRATED WITH PHASE 13 REVIEW)
# -----------------------------------------------------------------------------

@transaction.atomic
def create_correction_request(
    submission: Submission,
    review: SubmissionReview,
    user,
    reason: str,
    required_correction: str = "",
    affected_area: str = CorrectionAffectedArea.ACTIVITY_DATA,
) -> CorrectionRequest:
    """
    Creates an authoritative CorrectionRequest linked to a Submission and Review decision.
    Also ensures the initial ActivityRevision is preserved before any modifications occur.
    """
    record = submission.activity_record

    # 1. Permanently preserve baseline revision #1
    ensure_initial_activity_revision(
        record=record,
        submission=submission,
        created_by=submission.submitted_by,
    )

    # 2. Create authoritative CorrectionRequest
    correction_req = CorrectionRequest.objects.create(
        submission=submission,
        review=review,
        activity_record=record,
        requested_by=user,
        reason=reason.strip(),
        required_correction=(required_correction or "").strip(),
        affected_area=affected_area,
        status=CorrectionStatus.OPEN,
    )

    logger.info(
        "CorrectionRequest #%d created for Submission #%d (Record #%d) by %s.",
        correction_req.id,
        submission.id,
        record.id,
        user.username,
    )
    return correction_req


# -----------------------------------------------------------------------------
# 4. SITE MANAGER CORRECTION LIFECYCLE ACTIONS
# -----------------------------------------------------------------------------

@transaction.atomic
def start_correction(
    correction_req: CorrectionRequest,
    user,
    request=None,
) -> CorrectionRequest:
    """
    Transitions a CorrectionRequest from OPEN to IN_PROGRESS when a Site Manager begins work.
    """
    locked_corr = CorrectionRequest.objects.select_for_update().get(pk=correction_req.pk)

    if not user_can_edit_correction_request(user, locked_corr):
        raise PermissionDenied("You do not have authorization to work on this correction request.")

    if locked_corr.status == CorrectionStatus.OPEN:
        locked_corr.status = CorrectionStatus.IN_PROGRESS
        locked_corr.save(update_fields=["status", "updated_at"])

        log_auth_event(
            event_type=AuthAuditLog.EventType.CORRECTION_STARTED,
            user=user,
            resource_accessed=f"CorrectionRequest:{locked_corr.id}",
            details=(
                f"Correction work started on Record #{locked_corr.activity_record_id} "
                f"(Submission #{locked_corr.submission.submission_number}) by {user.username}."
            ),
            success=True,
            request=request,
        )

    return locked_corr


@transaction.atomic
def update_corrected_record(
    correction_req: CorrectionRequest,
    user,
    form_data: Dict[str, Any],
    request=None,
) -> Tuple[ActivityRecord, ValidationRun]:
    """
    Updates operational data on the ActivityRecord in response to a correction request.
    Enforces server-side field restrictions, runs revalidation, and updates correction status.

    Permitted fields to update:
    - quantity (Decimal)
    - unit (UnitOfMeasure)
    - measurement_date (Date)
    - notes (str)
    - evidence_reference (str)
    - site_manager_notes (str on CorrectionRequest)
    """
    locked_corr = CorrectionRequest.objects.select_for_update().get(pk=correction_req.pk)
    locked_rec = ActivityRecord.objects.select_for_update().get(pk=locked_corr.activity_record_id)

    # 1. Authorization
    if not user_can_edit_correction_request(user, locked_corr):
        raise PermissionDenied("You do not have authorization to modify data for this correction request.")

    # 2. Update editable fields only
    if "quantity" in form_data and form_data["quantity"] is not None:
        try:
            qty = Decimal(str(form_data["quantity"]))
            if qty < 0:
                raise ValidationError("Consumption quantity must be a non-negative number.")
            locked_rec.quantity = qty
        except (ValueError, TypeError):
            raise ValidationError("Invalid numeric quantity provided.")

    if "unit" in form_data and form_data["unit"]:
        unit = form_data["unit"]
        if isinstance(unit, UnitOfMeasure):
            locked_rec.unit = unit
        else:
            locked_rec.unit = UnitOfMeasure.objects.get(pk=unit)

    if "measurement_date" in form_data and form_data["measurement_date"]:
        locked_rec.measurement_date = form_data["measurement_date"]

    if "notes" in form_data:
        locked_rec.notes = form_data["notes"]

    if "evidence_reference" in form_data:
        locked_rec.evidence_reference = form_data["evidence_reference"]

    locked_rec.updated_by = user
    locked_rec.save()

    # 3. Update Site Manager explanatory notes
    site_notes = form_data.get("site_manager_notes", "").strip()
    if site_notes:
        locked_corr.site_manager_notes = site_notes

    # 4. Mandatory Reprocessing: Refresh OCR Comparisons, Validation & Anomaly Intelligence
    from apps.core.ocr_services import compare_ocr_with_activity_record
    for ev in locked_rec.evidence_files.filter(status=EvidenceStatus.ACTIVE):
        latest_ocr = ev.ocr_runs.order_by("-created_at").first()
        if latest_ocr:
            comp = compare_ocr_with_activity_record(latest_ocr)
            latest_ocr.raw_metadata["comparison"] = comp
            latest_ocr.save(update_fields=["raw_metadata"])

    val_run = execute_validation_run(locked_rec, executed_by=user, request=request)
    locked_rec.refresh_from_db()

    # Refresh anomaly intelligence scan with updated telemetry
    from apps.core.anomaly_services import detect_anomalies_for_record
    detect_anomalies_for_record(locked_rec, user=user)

    # 5. Advance correction state based on validation outcome
    if locked_rec.validation_status in [ValidationStatus.VALID, ValidationStatus.WARNING]:
        locked_corr.status = CorrectionStatus.READY_FOR_RESUBMISSION
    else:
        locked_corr.status = CorrectionStatus.IN_PROGRESS

    locked_corr.save(update_fields=["status", "site_manager_notes", "updated_at"])

    # 6. Audit Logging
    log_auth_event(
        event_type=AuthAuditLog.EventType.CORRECTION_UPDATED,
        user=user,
        resource_accessed=f"CorrectionRequest:{locked_corr.id}:Record:{locked_rec.id}",
        details=(
            f"Operational telemetry updated for Record #{locked_rec.id} (Correction #{locked_corr.id}) by {user.username}. "
            f"New Quantity: {locked_rec.quantity} {locked_rec.unit.symbol if locked_rec.unit else ''}. "
            f"Validation Status: {locked_rec.validation_status}."
        ),
        success=True,
        request=request,
    )

    logger.info(
        "Record #%d updated under CorrectionRequest #%d by %s (Validation: %s).",
        locked_rec.id,
        locked_corr.id,
        user.username,
        locked_rec.validation_status,
    )

    return locked_rec, val_run


# -----------------------------------------------------------------------------
# 5. AUTHORITATIVE RESUBMISSION SERVICE
# -----------------------------------------------------------------------------

@transaction.atomic
def resubmit_corrected_activity(
    correction_req: CorrectionRequest,
    user,
    comments: str = "",
    request=None,
) -> Submission:
    """
    Executes the authoritative Resubmission of a corrected ActivityRecord.

    Guarantees:
    - Atomicity & row-level locking on Record, CorrectionRequest, and previous Submission.
    - Server-side authorization check (Site Manager for assigned site).
    - Prevents duplicate resubmission (idempotency check).
    - Reporting period governance: period must be OPEN and allow modifications.
    - Phase 10 Validation Engine: MUST pass with VALID or WARNING. Blocking errors STRICTLY prevent resubmission!
    - Evidence requirements re-evaluation: active evidence must exist if required by activity master.
    - Creates immutable ActivityRevision preserving detailed field-by-field deltas from previous submission.
    - Updates CorrectionRequest status -> RESOLVED with resolving user and timestamp.
    - Creates new versioned Submission (#2, #3, ...) linked via parent_submission.
    - Marks prior submissions as non-current (is_current=False).
    - Transitions ActivityRecord.status -> SUBMITTED.
    - Emits AuthAuditLog events: CORRECTION_RESOLVED and RESUBMISSION_CREATED.
    """
    locked_corr = (
        CorrectionRequest.objects.select_for_update()
        .select_related("activity_record", "submission")
        .get(pk=correction_req.pk)
    )
    locked_rec = ActivityRecord.objects.select_for_update().get(pk=locked_corr.activity_record_id)
    prev_sub = (
        Submission.objects.select_for_update()
        .get(pk=locked_corr.submission_id)
    )

    # 1. Authorization
    if not user_can_edit_correction_request(user, locked_corr, allow_resolved=True):
        raise PermissionDenied("You do not have authorization to resubmit this corrected activity record.")

    # 2. Idempotency & Lifecycle State Check
    if locked_corr.status == CorrectionStatus.RESOLVED:
        if locked_corr.resubmission_id:
            logger.warning(
                "Duplicate resubmit blocked: CorrectionRequest #%d is already resolved (Submission #%d).",
                locked_corr.id,
                locked_corr.resubmission_id,
            )
            return locked_corr.resubmission
        raise ValidationError("This correction request has already been resolved and resubmitted.")

    if locked_rec.status == RecordStatus.SUBMITTED:
        active_sub = locked_rec.submissions.filter(is_current=True, status=SubmissionStatus.SUBMITTED).first()
        if active_sub:
            logger.warning(
                "Idempotent resubmission: Record #%d is already in SUBMITTED state (Submission #%d).",
                locked_rec.id,
                active_sub.submission_number,
            )
            return active_sub

    # 3. Reporting Period Boundary Check
    period = locked_rec.reporting_period
    if not period or period.status != PeriodStatus.OPEN or not period.allows_data_modification:
        raise ValidationError(
            f"Reporting period '{period.code if period else 'None'}' does not allow resubmissions."
        )

    # 4. Mandatory Validation Execution (Zero client trust)
    val_run = execute_validation_run(locked_rec, executed_by=user, request=request)
    locked_rec.refresh_from_db()

    if locked_rec.validation_status == ValidationStatus.INVALID:
        summary = val_run.summary_message if val_run else "Validation errors present."
        raise ValidationError(
            f"Resubmission blocked: Record failed validation checks with blocking errors. {summary}"
        )

    # 5. Evidence Requirements Check
    activity = locked_rec.activity
    if activity and activity.requires_evidence and not locked_rec.has_evidence:
        raise ValidationError(
            f"Resubmission blocked: Activity '{activity.name}' requires supporting evidence, but no active evidence files are attached."
        )

    # 6. Compute Field-by-Field Deltas compared to previous submission snapshot
    prev_snapshot = prev_sub.snapshot_data or {}
    old_qty_str = str(prev_snapshot.get("quantity", locked_rec.quantity))
    new_qty_str = str(locked_rec.quantity)
    try:
        qty_delta = Decimal(new_qty_str) - Decimal(old_qty_str)
    except Exception:
        qty_delta = Decimal("0.00")

    old_unit = prev_snapshot.get("unit_symbol", locked_rec.unit.symbol if locked_rec.unit else "")
    new_unit = locked_rec.unit.symbol if locked_rec.unit else ""

    old_date = prev_snapshot.get("measurement_date", "")
    new_date = locked_rec.measurement_date.isoformat() if locked_rec.measurement_date else ""

    changed_fields = {}
    if old_qty_str != new_qty_str:
        changed_fields["quantity"] = {
            "old": old_qty_str,
            "new": new_qty_str,
            "delta": f"{qty_delta:+f}",
        }
    if old_unit != new_unit:
        changed_fields["unit"] = {"old": old_unit, "new": new_unit}
    if old_date != new_date:
        changed_fields["measurement_date"] = {"old": old_date, "new": new_date}
    if (prev_snapshot.get("notes") or "") != (locked_rec.notes or ""):
        changed_fields["notes"] = {
            "old": prev_snapshot.get("notes", ""),
            "new": locked_rec.notes or "",
        }

    # 7. Build New Telemetry Snapshot
    evidence_items = []
    for ev in locked_rec.evidence_files.all():
        ocr_latest = ev.latest_ocr_run if hasattr(ev, "latest_ocr_run") else None
        evidence_items.append({
            "id": ev.id,
            "filename": ev.original_filename,
            "type": ev.evidence_type,
            "size": ev.file_size,
            "hash": ev.file_hash,
            "status": ev.status,
            "ocr_status": ocr_latest.status if ocr_latest else "NOT_PROCESSED",
        })

    new_snapshot = {
        "record_id": locked_rec.id,
        "site_id": locked_rec.site_id,
        "site_code": locked_rec.site.code,
        "site_name": locked_rec.site.name,
        "project_name": locked_rec.site.project.name,
        "subsidiary_name": locked_rec.site.project.subsidiary.name,
        "company_name": locked_rec.site.project.subsidiary.company.name,
        "reporting_period_id": locked_rec.reporting_period_id,
        "period_code": locked_rec.reporting_period.code,
        "period_fiscal_year": locked_rec.reporting_period.fiscal_year,
        "activity_code": locked_rec.activity.code,
        "activity_name": locked_rec.activity.name,
        "activity_category": locked_rec.activity.category.name if locked_rec.activity.category else "",
        "quantity": str(locked_rec.quantity),
        "unit_symbol": locked_rec.unit.symbol if locked_rec.unit else "",
        "unit_name": locked_rec.unit.name if locked_rec.unit else "",
        "measurement_date": locked_rec.measurement_date.isoformat() if locked_rec.measurement_date else "",
        "notes": locked_rec.notes,
        "evidence_reference": locked_rec.evidence_reference,
        "evidence_count": locked_rec.evidence_count,
        "evidence_files": evidence_items,
        "validation_run_id": val_run.id if val_run else None,
        "validation_run_number": val_run.run_number if val_run else None,
        "validation_status": locked_rec.validation_status,
        "validation_summary": val_run.summary_message if val_run else "",
        "validation_rules_evaluated": val_run.total_rules_evaluated if val_run else 0,
        "validation_warning_count": val_run.warning_count if val_run else 0,
        "submitted_by_username": user.username if user else "system",
        "submitted_at_iso": timezone.now().isoformat(),
        "is_resubmission": True,
        "parent_submission_number": prev_sub.submission_number,
        "correction_request_id": locked_corr.id,
        "correction_reason": locked_corr.reason,
        "correction_instructions": locked_corr.required_correction,
        "site_manager_notes": comments or locked_corr.site_manager_notes,
    }

    # 8. Determine Monotonic Revision and Submission Counter
    next_rev_num = locked_rec.revisions.count() + 1
    next_sub_num = prev_sub.submission_number + 1

    # 9. Mark prior submissions non-current
    locked_rec.submissions.filter(is_current=True).update(is_current=False)

    # 10. Create new Submission instance
    final_comments = comments.strip() if comments else locked_corr.site_manager_notes
    new_submission = Submission.objects.create(
        activity_record=locked_rec,
        submission_number=next_sub_num,
        parent_submission=prev_sub,
        site=locked_rec.site,
        reporting_period=locked_rec.reporting_period,
        submitted_by=user,
        status=SubmissionStatus.SUBMITTED,
        validation_run=val_run,
        validation_status=locked_rec.validation_status,
        comments=final_comments,
        snapshot_data=new_snapshot,
        is_current=True,
    )

    # 11. Create immutable ActivityRevision ledger entry
    ActivityRevision.objects.create(
        activity_record=locked_rec,
        revision_number=next_rev_num,
        submission=new_submission,
        correction_request=locked_corr,
        created_by=user,
        reason="CORRECTION_RESUBMISSION",
        comments=final_comments,
        quantity=locked_rec.quantity,
        unit=locked_rec.unit,
        measurement_date=locked_rec.measurement_date,
        notes=locked_rec.notes or "",
        evidence_reference=locked_rec.evidence_reference or "",
        validation_status=locked_rec.validation_status,
        changed_fields=changed_fields,
        snapshot_data=new_snapshot,
    )

    # 12. Update CorrectionRequest state -> RESOLVED
    locked_corr.status = CorrectionStatus.RESOLVED
    locked_corr.resolved_by = user
    locked_corr.resolved_at = timezone.now()
    locked_corr.resubmission = new_submission
    if final_comments:
        locked_corr.site_manager_notes = final_comments
    locked_corr.save(update_fields=["status", "resolved_by", "resolved_at", "resubmission", "site_manager_notes", "updated_at"])

    # 13. Transition ActivityRecord.status -> SUBMITTED
    locked_rec.status = RecordStatus.SUBMITTED
    locked_rec.updated_by = user
    locked_rec.save(update_fields=["status", "updated_by", "updated_at"])

    # 14. Audit Logging
    log_auth_event(
        event_type=AuthAuditLog.EventType.CORRECTION_RESOLVED,
        user=user,
        resource_accessed=f"CorrectionRequest:{locked_corr.id}",
        details=(
            f"Correction Request #{locked_corr.id} RESOLVED for Record #{locked_rec.id} by {user.username}. "
            f"Resubmitted as Submission #{next_sub_num}."
        ),
        success=True,
        request=request,
    )

    log_auth_event(
        event_type=AuthAuditLog.EventType.RESUBMISSION_CREATED,
        user=user,
        resource_accessed=f"Submission:{new_submission.id}:Parent:{prev_sub.id}",
        details=(
            f"Resubmission #{next_sub_num} created for Record #{locked_rec.id} (Parent #{prev_sub.submission_number}) by {user.username}. "
            f"Quantity: {locked_rec.quantity} {locked_rec.unit.symbol if locked_rec.unit else ''}. "
            f"Validation Status: {locked_rec.validation_status}."
        ),
        success=True,
        request=request,
    )

    logger.info(
        "Record #%d successfully resubmitted as Submission #%d (Parent #%d) by %s.",
        locked_rec.id,
        new_submission.submission_number,
        prev_sub.submission_number,
        user.username,
    )

    # Trigger automated anomaly re-evaluation for corrected record
    try:
        from apps.core.anomaly_services import detect_anomalies_for_record
        detect_anomalies_for_record(
            record=locked_rec,
            user=user,
            submission=new_submission,
            request=request,
        )
    except Exception as anom_err:
        logger.warning("Anomaly re-evaluation failed on resubmission #%d: %s", new_submission.id, anom_err)

    return new_submission


# -----------------------------------------------------------------------------
# 6. HISTORICAL LINEAGE TIMELINE & COMPARISON DIFF ENGINES
# -----------------------------------------------------------------------------

def get_submission_history_timeline(submission: Submission) -> List[Dict[str, Any]]:
    """
    Builds a complete, chronological audit and governance timeline for an ActivityRecord
    and its submissions, reviews, corrections, and revisions.
    """
    if not submission:
        return []

    record = submission.activity_record
    timeline: List[Dict[str, Any]] = []

    # 1. Gather all submissions for this record
    all_submissions = record.submissions.select_related(
        "submitted_by", "validation_run"
    ).order_by("submitted_at")

    for sub in all_submissions:
        timeline.append({
            "type": "SUBMISSION",
            "timestamp": sub.submitted_at,
            "title": f"Submission #{sub.submission_number} Created",
            "badge_class": "badge-primary",
            "actor": sub.submitted_by.username if sub.submitted_by else "System",
            "role": "Site Manager",
            "details": f"Quantity: {sub.snapshot_data.get('quantity', '—')} {sub.snapshot_data.get('unit_symbol', '')}. Validation: {sub.validation_status}.",
            "comments": sub.comments,
            "submission_id": sub.id,
            "is_resubmission": sub.is_resubmission,
        })

    # 2. Gather all reviews
    all_reviews = SubmissionReview.objects.filter(
        submission__activity_record=record
    ).select_related("reviewer", "submission").order_by("created_at")

    for rev in all_reviews:
        action_titles = {
            ReviewAction.VERIFY: "Governance Decision: Verified",
            ReviewAction.REQUEST_CORRECTION: "Governance Decision: Correction Requested",
            ReviewAction.EXPLAIN: "Operating Context: Explanation Recorded",
            ReviewAction.ESCALATE: f"Governance Escalation to {rev.escalated_to_role}",
        }
        timeline.append({
            "type": "REVIEW",
            "timestamp": rev.created_at,
            "title": action_titles.get(rev.action, f"Review: {rev.get_action_display()}"),
            "badge_class": rev.badge_class,
            "actor": rev.reviewer.username if rev.reviewer else "Governance Reviewer",
            "role": "Subsidiary Manager",
            "details": rev.comments,
            "required_correction": rev.required_correction,
            "submission_id": rev.submission_id,
            "review_id": rev.id,
        })

    # 3. Gather all corrections resolved
    all_corrections = CorrectionRequest.objects.filter(
        activity_record=record,
        status=CorrectionStatus.RESOLVED,
    ).select_related("resolved_by", "resubmission").order_by("resolved_at")

    for corr in all_corrections:
        if corr.resolved_at:
            timeline.append({
                "type": "CORRECTION_RESOLVED",
                "timestamp": corr.resolved_at,
                "title": f"Correction #{corr.id} Resolved by Site Manager",
                "badge_class": "badge-success",
                "actor": corr.resolved_by.username if corr.resolved_by else "Site Manager",
                "role": "Site Manager",
                "details": corr.site_manager_notes or "Operational correction completed.",
                "correction_id": corr.id,
            })

    # Sort timeline chronologically
    timeline.sort(key=lambda x: x["timestamp"])
    return timeline


def compute_submission_deltas(
    current_submission: Submission,
    baseline_submission: Optional[Submission] = None,
) -> Dict[str, Any]:
    """
    Computes side-by-side comparative differences between the latest/current submission
    and the baseline or previous submission it supersedes.
    """
    if not current_submission:
        return {}

    baseline = baseline_submission or current_submission.parent_submission
    if not baseline:
        # Fall back to first submission if different
        first_sub = current_submission.activity_record.submissions.order_by("submission_number").first()
        if first_sub and first_sub.id != current_submission.id:
            baseline = first_sub

    curr_snap = current_submission.snapshot_data or {}
    base_snap = (baseline.snapshot_data if baseline else {}) or {}

    curr_qty = curr_snap.get("quantity", str(current_submission.quantity))
    base_qty = base_snap.get("quantity", curr_qty)
    qty_changed = curr_qty != base_qty

    qty_delta_str = ""
    if qty_changed:
        try:
            delta = Decimal(curr_qty) - Decimal(base_qty)
            qty_delta_str = f"{delta:+f}"
        except Exception:
            qty_delta_str = ""

    curr_unit = curr_snap.get("unit_symbol", current_submission.unit.symbol if current_submission.unit else "")
    base_unit = base_snap.get("unit_symbol", curr_unit)

    curr_date = curr_snap.get("measurement_date", str(current_submission.measurement_date or ""))
    base_date = base_snap.get("measurement_date", curr_date)

    curr_notes = curr_snap.get("notes", current_submission.activity_record.notes or "")
    base_notes = base_snap.get("notes", curr_notes)

    # Evidence comparison
    curr_ev_files = curr_snap.get("evidence_files", [])
    base_ev_files = base_snap.get("evidence_files", [])

    base_ev_ids = {ev.get("id") for ev in base_ev_files if ev.get("id")}
    curr_ev_ids = {ev.get("id") for ev in curr_ev_files if ev.get("id")}

    added_evidence = [ev for ev in curr_ev_files if ev.get("id") not in base_ev_ids]
    retained_evidence = [ev for ev in curr_ev_files if ev.get("id") in base_ev_ids]

    # Validation comparison
    base_val_status = base_snap.get("validation_status", "VALID")
    curr_val_status = curr_snap.get("validation_status", current_submission.validation_status)

    return {
        "has_baseline": baseline is not None,
        "baseline_submission_number": baseline.submission_number if baseline else None,
        "baseline_submitted_at": baseline.submitted_at if baseline else None,
        "current_submission_number": current_submission.submission_number,
        "current_submitted_at": current_submission.submitted_at,
        "quantity": {
            "original": base_qty,
            "corrected": curr_qty,
            "delta": qty_delta_str,
            "changed": qty_changed,
        },
        "unit": {
            "original": base_unit,
            "corrected": curr_unit,
            "changed": base_unit != curr_unit,
        },
        "measurement_date": {
            "original": base_date,
            "corrected": curr_date,
            "changed": base_date != curr_date,
        },
        "notes": {
            "original": base_notes,
            "corrected": curr_notes,
            "changed": base_notes != curr_notes,
        },
        "evidence": {
            "original_count": len(base_ev_files),
            "corrected_count": len(curr_ev_files),
            "added": added_evidence,
            "retained": retained_evidence,
            "changed": len(added_evidence) > 0 or len(base_ev_files) != len(curr_ev_files),
        },
        "validation": {
            "original": base_val_status,
            "corrected": curr_val_status,
            "changed": base_val_status != curr_val_status,
        },
        "correction_reason": curr_snap.get("correction_reason", ""),
        "correction_instructions": curr_snap.get("correction_instructions", ""),
        "site_manager_notes": curr_snap.get("site_manager_notes", current_submission.comments or ""),
    }
