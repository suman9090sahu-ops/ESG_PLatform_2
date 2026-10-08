"""
Activity Submission and Governance Workflow Services for MEIL ESG CONTROL TOWER.

Fulfills Phase 12 Requirements:
- Authoritative Handover Boundary: Site Manager Operational Layer -> Subsidiary Review Workflow
- Scoped Queryset Retrieval (get_accessible_submissions)
- Server-side Eligibility Verification (check_submission_eligibility)
- Idempotent & Atomic Submission Creation (submit_activity_record)
- Phase 10 Validation Engine Integration (Zero client trust, blocking error gate)
- Phase 09 Evidence Requirements Integration
- Temporal Boundary & Reporting Period Governance Enforcement
- Controlled Lifecycle Progression (DRAFT/READY -> SUBMITTED) and Immutability Locking
- Safe Submitter Withdrawal (withdraw_submission)
- Audited Compliance Lineage Logging (AuthAuditLog)
"""

import logging
from typing import List, Tuple

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.core.auth_services import log_auth_event
from apps.core.data_entry_services import (
    get_accessible_activity_records,
    user_can_access_activity_record,
)
from apps.core.models import (
    ActivityMaster,
    ActivityRecord,
    AuthAuditLog,
    MasterStatus,
    OrganizationStatus,
    PeriodStatus,
    RecordStatus,
    ReportingPeriod,
    Role,
    Site,
    Submission,
    SubmissionStatus,
    ValidationRun,
    ValidationStatus,
)
from apps.core.period_services import can_user_modify_data
from apps.core.scope_services import (
    get_accessible_companies,
    get_accessible_sites,
    get_accessible_subsidiaries,
    user_can_access_site,
)
from apps.core.validation_services import execute_validation_run

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. SCOPED SUBMISSION QUERYSET RETRIEVAL
# -----------------------------------------------------------------------------

def get_accessible_submissions(user):
    """
    Returns QuerySet of Submission instances accessible to the user based on RBAC scope.

    Strict organizational boundaries:
    - SITE_MANAGER: Confined exclusively to submissions from explicitly assigned sites.
    - SUBSIDIARY_MANAGER: Confined to submissions from child sites under assigned subsidiaries/companies.
    - MEIL_OPERATOR / ESG_MANAGER / AUDITOR / Superuser: Confined to submissions under accessible enterprise companies.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return Submission.objects.none()

    base_qs = Submission.objects.select_related(
        "activity_record",
        "activity_record__activity",
        "activity_record__activity__category",
        "activity_record__activity__base_unit",
        "activity_record__unit",
        "site",
        "site__project",
        "site__project__subsidiary",
        "site__project__subsidiary__company",
        "reporting_period",
        "submitted_by",
        "validation_run",
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
        return base_qs.filter(site__project__subsidiary__company__in=accessible_companies).order_by(
            "-submitted_at"
        )

    if user.has_role(Role.Code.SUBSIDIARY_MANAGER):
        accessible_subs = get_accessible_subsidiaries(user)
        return base_qs.filter(site__project__subsidiary__in=accessible_subs).order_by(
            "-submitted_at"
        )

    if user.has_role(Role.Code.SITE_MANAGER):
        accessible_sites = get_accessible_sites(user)
        return base_qs.filter(site__in=accessible_sites).order_by(
            "-submitted_at"
        )

    return Submission.objects.none()


def user_can_access_submission(user, submission) -> bool:
    """
    Evaluates whether a user has read authorization for a specific Submission instance.
    """
    if not user or not user.is_authenticated or not user.is_active or not submission:
        return False

    return get_accessible_submissions(user).filter(id=submission.id).exists()


# -----------------------------------------------------------------------------
# 2. SUBMISSION ELIGIBILITY & AUTHORIZATION
# -----------------------------------------------------------------------------

def user_can_submit_activity_record(user, record: ActivityRecord) -> bool:
    """
    Evaluates whether a user has functional authority to formally submit an ActivityRecord.

    Rules:
    - Permitted roles: SITE_MANAGER, MEIL_OPERATOR, ESG_MANAGER
    - AUDITOR: Strictly prohibited (read-only assurance)
    - SUBSIDIARY_MANAGER: Read & review only; cannot create site-level submissions unless also assigned as SITE_MANAGER
    - User must have explicit object-level access to the ActivityRecord and the associated Site.
    """
    if not user or not user.is_authenticated or not user.is_active or not record:
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

    has_allowed_role = (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.SITE_MANAGER)
        or user.has_role(Role.Code.ESG_MANAGER)
    )
    if not has_allowed_role:
        return False

    # Check object-level record and site scoping
    if not user_can_access_activity_record(user, record):
        return False

    if not user_can_access_site(user, record.site):
        return False

    return True


def check_submission_eligibility(
    user, record: ActivityRecord
) -> Tuple[bool, List[str], List[str]]:
    """
    Performs comprehensive server-side eligibility checks prior to formal submission.

    Returns:
        (is_eligible: bool, blocking_errors: list[str], warnings: list[str])
    """
    blocking_errors = []
    warnings = []

    if not record:
        return False, ["Activity record does not exist."], []

    # 1. Authorization
    if not user_can_submit_activity_record(user, record):
        blocking_errors.append(
            "You do not have authorization to submit activity data for this operational site."
        )

    # 2. Site Status
    if record.site.status != OrganizationStatus.ACTIVE:
        blocking_errors.append(
            f"Operational site '{record.site.name}' is currently {record.site.get_status_display()} and cannot submit data."
        )

    # 3. Reporting Period Lifecycle
    period = record.reporting_period
    if not period:
        blocking_errors.append("Activity record is not linked to a governing reporting period.")
    else:
        if period.status != PeriodStatus.OPEN:
            blocking_errors.append(
                f"Reporting period '{period.name}' ({period.code}) is {period.get_status_display()}. Submissions are permitted only for OPEN reporting periods."
            )
        elif not period.allows_data_modification:
            blocking_errors.append(
                f"Reporting period '{period.code}' does not allow data modifications."
            )

    # 4. Activity Master Status
    activity = record.activity
    if not activity:
        blocking_errors.append("Activity record has no associated Activity Master item.")
    else:
        if activity.status != MasterStatus.ACTIVE or not activity.is_active:
            blocking_errors.append(
                f"Activity master item '{activity.name}' is inactive and cannot be submitted."
            )

    # 5. Record Lifecycle State
    allowed_statuses = [RecordStatus.DRAFT, RecordStatus.READY, RecordStatus.REJECTED]
    if record.status not in allowed_statuses:
        if record.status == RecordStatus.SUBMITTED:
            blocking_errors.append(
                f"Record #{record.id} is already in SUBMITTED status and awaiting review."
            )
        elif record.status in [RecordStatus.VERIFIED, RecordStatus.APPROVED]:
            blocking_errors.append(
                f"Record #{record.id} is already {record.get_status_display()} and cannot be re-submitted."
            )
        else:
            blocking_errors.append(
                f"Record #{record.id} status is '{record.get_status_display()}' and cannot be submitted."
            )

    # 6. Physical Data Requirements
    if record.quantity is None or record.quantity < 0:
        blocking_errors.append("Operational consumption quantity must be a non-negative number.")
    if not record.unit_id:
        blocking_errors.append("Unit of measure is required.")
    if not record.measurement_date:
        blocking_errors.append("Measurement date is required.")

    # 7. Evidence Requirements (Phase 09)
    if activity and activity.requires_evidence:
        if not record.has_evidence:
            blocking_errors.append(
                f"Activity '{activity.name}' requires supporting evidence (e.g. invoice, challan, meter log). No active evidence documents are currently attached."
            )

    # 8. Phase 10 Validation Status
    if record.validation_status == ValidationStatus.UNVALIDATED:
        warnings.append(
            "Record has not yet been validated by the Phase 10 Validation Engine. Automated validation will execute upon submission."
        )
    elif record.validation_status == ValidationStatus.INVALID:
        blocking_errors.append(
            "Record failed deterministic validation checks with blocking errors. Please resolve all validation errors before submitting."
        )
    elif record.validation_status == ValidationStatus.WARNING:
        warnings.append(
            "Record passed validation with non-blocking advisory warnings. Downstream reviewers will be alerted to these warnings."
        )

    is_eligible = len(blocking_errors) == 0
    return is_eligible, blocking_errors, warnings


# -----------------------------------------------------------------------------
# 3. SUBMISSION TRANSACTION & IDEMPOTENCY
# -----------------------------------------------------------------------------

@transaction.atomic
def submit_activity_record(
    record: ActivityRecord,
    user,
    comments: str = "",
    request=None,
    force_revalidate: bool = True,
) -> Submission:
    """
    Formally submits an ActivityRecord into the downstream review process.

    Executes in a database transaction with concurrency locking:
    1. Locks the ActivityRecord row with select_for_update().
    2. Detects and protects against duplicate concurrent submissions (idempotency).
    3. Enforces full server-side eligibility checks.
    4. Executes Phase 10 Validation Engine (rejects if blocking errors detected).
    5. Calculates sequential submission_number.
    6. Generates immutable telemetry snapshot data.
    7. Creates formal Submission entity and marks previous submissions as non-current.
    8. Transitions ActivityRecord.status -> SUBMITTED (locking Site Manager edit).
    9. Logs security and compliance audit event in AuthAuditLog.
    """
    # 1. Row-level concurrency lock
    locked_record = ActivityRecord.objects.select_for_update().get(pk=record.pk)

    # 2. Idempotency & Duplicate Submission Protection
    if locked_record.status == RecordStatus.SUBMITTED:
        existing_current = locked_record.submissions.filter(
            is_current=True,
            status=SubmissionStatus.SUBMITTED,
        ).first()
        if existing_current:
            logger.warning(
                "Idempotent submission: Record #%d is already SUBMITTED (Submission #%d).",
                locked_record.id,
                existing_current.submission_number,
            )
            return existing_current

    # 3. Server-side eligibility evaluation
    is_eligible, errors, _ = check_submission_eligibility(user, locked_record)
    if not is_eligible:
        err_msg = "; ".join(errors)
        logger.warning(
            "Submission rejected for Record #%d by user %s: %s",
            locked_record.id,
            user.username if user else "Unknown",
            err_msg,
        )
        raise ValidationError(f"Submission rejected: {err_msg}")

    # 4. Phase 10 Validation Engine Execution
    val_run = None
    if force_revalidate or locked_record.validation_status == ValidationStatus.UNVALIDATED:
        val_run = execute_validation_run(locked_record, executed_by=user, request=request)
        locked_record.refresh_from_db()
    else:
        val_run = locked_record.latest_validation_run

    if locked_record.validation_status == ValidationStatus.INVALID:
        summary = val_run.summary_message if val_run else "Validation errors present."
        logger.warning(
            "Submission blocked by Validation Engine for Record #%d: %s",
            locked_record.id,
            summary,
        )
        raise ValidationError(f"Validation Engine blocked submission: {summary}")

    # 5. Determine sequential submission number
    last_submission = locked_record.submissions.order_by("-submission_number").first()
    submission_number = (last_submission.submission_number + 1) if last_submission else 1

    # 6. Mark any prior submissions as non-current
    locked_record.submissions.filter(is_current=True).update(is_current=False)

    # 7. Build structured telemetry snapshot
    active_evidence = locked_record.evidence_files.filter(status=OrganizationStatus.ACTIVE) if hasattr(OrganizationStatus, "ACTIVE") else locked_record.evidence_files.all()
    evidence_items = []
    for ev in locked_record.evidence_files.all():
        ocr_latest = ev.latest_ocr_run if hasattr(ev, "latest_ocr_run") else None
        evidence_items.append({
            "id": ev.id,
            "filename": ev.original_filename,
            "type": ev.evidence_type,
            "size": ev.file_size,
            "hash": ev.file_hash,
            "ocr_status": ocr_latest.status if ocr_latest else "NOT_PROCESSED",
        })

    snapshot = {
        "record_id": locked_record.id,
        "site_id": locked_record.site_id,
        "site_code": locked_record.site.code,
        "site_name": locked_record.site.name,
        "project_name": locked_record.site.project.name,
        "subsidiary_name": locked_record.site.project.subsidiary.name,
        "company_name": locked_record.site.project.subsidiary.company.name,
        "reporting_period_id": locked_record.reporting_period_id,
        "period_code": locked_record.reporting_period.code,
        "period_fiscal_year": locked_record.reporting_period.fiscal_year,
        "activity_code": locked_record.activity.code,
        "activity_name": locked_record.activity.name,
        "activity_category": locked_record.activity.category.name if locked_record.activity.category else "",
        "quantity": str(locked_record.quantity),
        "unit_symbol": locked_record.unit.symbol if locked_record.unit else "",
        "unit_name": locked_record.unit.name if locked_record.unit else "",
        "measurement_date": locked_record.measurement_date.isoformat() if locked_record.measurement_date else "",
        "notes": locked_record.notes,
        "evidence_reference": locked_record.evidence_reference,
        "evidence_count": locked_record.evidence_count,
        "evidence_files": evidence_items,
        "validation_run_id": val_run.id if val_run else None,
        "validation_run_number": val_run.run_number if val_run else None,
        "validation_status": locked_record.validation_status,
        "validation_summary": val_run.summary_message if val_run else "",
        "validation_rules_evaluated": val_run.total_rules_evaluated if val_run else 0,
        "validation_warning_count": val_run.warning_count if val_run else 0,
        "submitted_by_username": user.username if user else "system",
        "submitted_at_iso": timezone.now().isoformat(),
    }

    # 8. Create formal Submission entity
    submission = Submission.objects.create(
        activity_record=locked_record,
        submission_number=submission_number,
        site=locked_record.site,
        reporting_period=locked_record.reporting_period,
        submitted_by=user,
        status=SubmissionStatus.SUBMITTED,
        validation_run=val_run,
        validation_status=locked_record.validation_status,
        comments=comments or "",
        snapshot_data=snapshot,
        is_current=True,
    )

    # 9. Transition ActivityRecord.status -> SUBMITTED
    locked_record.status = RecordStatus.SUBMITTED
    locked_record.updated_by = user
    locked_record.save(update_fields=["status", "updated_by", "updated_at"])
    record.status = RecordStatus.SUBMITTED

    # 10. Log security and compliance audit event
    log_auth_event(
        event_type=AuthAuditLog.EventType.SUBMISSION_CREATED,
        user=user,
        resource_accessed=f"ActivityRecord:{locked_record.id}:Submission:{submission.id}",
        details=(
            f"Formal submission #{submission_number} recorded for Record #{locked_record.id} "
            f"({locked_record.activity.code} @ {locked_record.site.code}). "
            f"Quantity: {locked_record.quantity} {locked_record.unit.symbol if locked_record.unit else ''}. "
            f"Validation: {locked_record.validation_status}. "
            f"Comments: {comments[:150] if comments else 'None'}"
        ),
        success=True,
        request=request,
    )

    logger.info(
        "Formal submission #%d created for Record #%d (Submission ID: %d) by %s",
        submission_number,
        locked_record.id,
        submission.id,
        user.username if user else "System",
    )

    # 11. Trigger automated anomaly detection telemetry
    try:
        from apps.core.anomaly_services import detect_anomalies_for_record
        detect_anomalies_for_record(
            record=locked_record,
            user=user,
            submission=submission,
            request=request,
        )
    except Exception as anom_err:
        logger.warning("Anomaly detection telemetry failed on submission #%d: %s", submission.id, anom_err)

    return submission


@transaction.atomic
def withdraw_submission(
    submission: Submission,
    user,
    reason: str = "",
    request=None,
) -> Submission:
    """
    Allows a Site Manager or authorized submitter to withdraw an active submission
    prior to downstream review, reverting the ActivityRecord to DRAFT for revision.

    Rules:
    - User must have authority to submit for this site.
    - Submission must be currently in SUBMITTED state (cannot withdraw once reviewed/approved).
    - Reporting period must still be OPEN.
    """
    if not submission:
        raise ValidationError("Submission does not exist.")

    # Authorization
    if not user_can_submit_activity_record(user, submission.activity_record):
        raise PermissionDenied("You do not have authorization to withdraw this submission.")

    if submission.status != SubmissionStatus.SUBMITTED:
        raise ValidationError(
            f"Submission #{submission.submission_number} cannot be withdrawn because its status is {submission.get_status_display()}."
        )

    # Period check
    if not can_user_modify_data(user, submission.reporting_period):
        raise ValidationError(
            f"Reporting period '{submission.reporting_period.code}' is closed and does not allow modifications."
        )

    # 1. Update submission state
    submission.status = SubmissionStatus.WITHDRAWN
    submission.is_current = False
    submission.comments = f"{submission.comments}\n[WITHDRAWN by {user.username}: {reason}]".strip()
    submission.save(update_fields=["status", "is_current", "comments", "updated_at"])

    # 2. Revert ActivityRecord to DRAFT
    record = submission.activity_record
    record.status = RecordStatus.DRAFT
    record.updated_by = user
    record.save(update_fields=["status", "updated_by", "updated_at"])

    # 3. Log audit event
    log_auth_event(
        event_type=AuthAuditLog.EventType.SUBMISSION_WITHDRAWN,
        user=user,
        resource_accessed=f"ActivityRecord:{record.id}:Submission:{submission.id}",
        details=(
            f"Submission #{submission.submission_number} for Record #{record.id} withdrawn by {user.username}. "
            f"Record reverted to DRAFT. Reason: {reason[:150] if reason else 'Submitter withdrawal'}"
        ),
        success=True,
        request=request,
    )

    logger.info(
        "Submission #%d for Record #%d withdrawn by %s",
        submission.submission_number,
        record.id,
        user.username,
    )

    return submission
