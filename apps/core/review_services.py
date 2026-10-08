"""
Subsidiary Manager Review and ESG Governance Workflow Services for MEIL ESG CONTROL TOWER.

Fulfills Phase 13 Requirements:
- First-line ESG Review Workspace for Subsidiary Managers
- Scoped Queryset Access & Object-Level Authorization (Zero client trust, anti-IDOR)
- Self-Approval Protection (reviewers cannot verify their own submissions)
- Controlled Lifecycle Progression:
    SUBMITTED / UNDER_REVIEW -> VERIFIED
    SUBMITTED / UNDER_REVIEW -> CORRECTION_REQUESTED
    SUBMITTED / UNDER_REVIEW -> EXPLAINED
    SUBMITTED / UNDER_REVIEW / EXPLAINED -> ESCALATED
- Immutable Operational Telemetry (ActivityRecord quantities and measurements are untouched)
- Historical Decision Trail Preservation via SubmissionReview records
- Atomic Transactions and Row-Level Concurrency Protection
- Audited Compliance Lineage Logging (AuthAuditLog events)
- Real Metrics Aggregation for Subsidiary Manager Dashboard
"""

import logging
from typing import Dict, List, Optional, Tuple

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.core.auth_services import log_auth_event
from apps.core.models import (
    ActivityRecord,
    AuthAuditLog,
    RecordStatus,
    ReviewAction,
    Role,
    Submission,
    SubmissionReview,
    SubmissionStatus,
    ValidationStatus,
)
from apps.core.scope_services import (
    get_accessible_companies,
    get_accessible_projects,
    get_accessible_sites,
    get_accessible_subsidiaries,
)
from apps.core.submission_services import (
    get_accessible_submissions,
    user_can_access_submission,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. REVIEW ROLE & OBJECT-LEVEL AUTHORIZATION
# -----------------------------------------------------------------------------

def user_can_review_submissions(user) -> bool:
    """
    Evaluates whether a user has functional authority to review submissions.

    Permitted roles:
    - SUBSIDIARY_MANAGER (primary first-line reviewer)
    - MEIL_OPERATOR (system-wide operational review authority)
    - ESG_MANAGER (corporate governance oversight)
    - Superuser

    Strictly prohibited:
    - SITE_MANAGER (cannot review or verify submissions)
    - AUDITOR (read-only assurance; prohibited from executing review mutations)
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False

    if user.is_superuser:
        return True

    # Auditor is strictly read-only assurance
    if user.has_role(Role.Code.AUDITOR) and not user.has_role(Role.Code.MEIL_OPERATOR):
        return False

    # Site manager alone cannot review submissions
    if user.has_role(Role.Code.SITE_MANAGER) and not (
        user.has_role(Role.Code.SUBSIDIARY_MANAGER)
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
    ):
        return False

    return (
        user.has_role(Role.Code.SUBSIDIARY_MANAGER)
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
    )


def user_can_review_submission(user, submission: Submission) -> bool:
    """
    Evaluates whether a user has object-level authorization to review a specific Submission.

    Enforces:
    1. Functional reviewer role check.
    2. Organizational scope boundary: Submission must belong to user's accessible scope.
    3. Self-Approval Protection: A reviewer cannot review a submission they personally created,
       unless they are a superuser or platform operator.
    """
    if not user or not user.is_authenticated or not user.is_active or not submission:
        return False

    if not user_can_review_submissions(user):
        return False

    # Object-level organizational scoping check
    if not user_can_access_submission(user, submission):
        return False

    # Self-Approval Protection
    if submission.submitted_by_id == user.id:
        if not (user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR)):
            logger.warning(
                "Self-review prevented: User '%s' attempted to review their own Submission #%d.",
                user.username,
                submission.id,
            )
            return False

    return True


# -----------------------------------------------------------------------------
# 2. STATUS TRANSITION VALIDATION RULES
# -----------------------------------------------------------------------------

VALID_TRANSITIONS: Dict[str, List[str]] = {
    SubmissionStatus.SUBMITTED: [
        ReviewAction.VERIFY,
        ReviewAction.REQUEST_CORRECTION,
        ReviewAction.EXPLAIN,
        ReviewAction.ESCALATE,
    ],
    SubmissionStatus.UNDER_REVIEW: [
        ReviewAction.VERIFY,
        ReviewAction.REQUEST_CORRECTION,
        ReviewAction.EXPLAIN,
        ReviewAction.ESCALATE,
    ],
    SubmissionStatus.EXPLAINED: [
        ReviewAction.VERIFY,
        ReviewAction.REQUEST_CORRECTION,
        ReviewAction.ESCALATE,
    ],
    SubmissionStatus.VERIFIED: [],  # Terminal stage for subsidiary review
    SubmissionStatus.CORRECTION_REQUESTED: [],  # Awaiting site manager revision
    SubmissionStatus.ESCALATED: [],  # Transferred to ESG Governance
    SubmissionStatus.WITHDRAWN: [],  # Withdrawn by submitter
    SubmissionStatus.APPROVED: [],  # Final corporate approved
    SubmissionStatus.REJECTED: [],  # Revision requested
}


def can_transition_submission(submission: Submission, action: str) -> Tuple[bool, str]:
    """
    Validates server-side whether a Submission in its current state can execute the target action.

    Returns:
        (is_valid: bool, error_message: str)
    """
    if not submission:
        return False, "Submission does not exist."

    current_status = submission.status
    allowed_actions = VALID_TRANSITIONS.get(current_status, [])

    if action not in allowed_actions:
        status_display = submission.get_status_display()
        if current_status in [SubmissionStatus.VERIFIED, SubmissionStatus.APPROVED]:
            return False, f"Submission is already {status_display} and cannot be modified."
        if current_status in [SubmissionStatus.CORRECTION_REQUESTED, SubmissionStatus.REJECTED]:
            return False, "Submission has a pending correction request and is awaiting revision by the Site Manager."
        if current_status == SubmissionStatus.ESCALATED:
            return False, "Submission has been escalated to corporate ESG Governance."
        if current_status == SubmissionStatus.WITHDRAWN:
            return False, "Submission was withdrawn by the submitter and cannot be reviewed."

        return False, f"Action '{action}' is not permitted for submissions in '{status_display}' status."

    return True, ""


# -----------------------------------------------------------------------------
# 3. ATOMIC REVIEW ACTION DECISIONS
# -----------------------------------------------------------------------------

@transaction.atomic
def verify_submission(
    submission: Submission,
    user,
    comments: str = "",
    request=None,
) -> SubmissionReview:
    """
    Executes the Subsidiary Manager's VERIFY decision.

    Guarantees:
    - Atomicity & row-level locking on Submission and ActivityRecord.
    - Server-side authorization and self-review protection.
    - Valid state transition verification.
    - ActivityRecord operational telemetry is untouched.
    - Status transitions:
        Submission.status -> VERIFIED
        ActivityRecord.status -> VERIFIED
    - Creates historical SubmissionReview record.
    - Emits AuthAuditLog SUBMISSION_VERIFIED compliance event.
    """
    locked_sub = Submission.objects.select_for_update().select_related("activity_record", "site").get(pk=submission.pk)
    locked_rec = ActivityRecord.objects.select_for_update().get(pk=locked_sub.activity_record_id)

    # 1. Authorization Check
    if not user_can_review_submission(user, locked_sub):
        raise PermissionDenied("You do not have authorization to verify this submission.")

    # 2. Transition Check
    is_valid, err_msg = can_transition_submission(locked_sub, ReviewAction.VERIFY)
    if not is_valid:
        raise ValidationError(err_msg)

    previous_status = locked_sub.status

    # 3. Mutate Lifecycle State
    locked_sub.status = SubmissionStatus.VERIFIED
    locked_sub.save(update_fields=["status", "updated_at"])

    locked_rec.status = RecordStatus.VERIFIED
    locked_rec.updated_by = user
    locked_rec.save(update_fields=["status", "updated_by", "updated_at"])

    # 4. Create Immutable Review Record
    review = SubmissionReview.objects.create(
        submission=locked_sub,
        reviewer=user,
        action=ReviewAction.VERIFY,
        previous_status=previous_status,
        new_status=SubmissionStatus.VERIFIED,
        comments=comments.strip(),
        metadata={
            "quantity": str(locked_rec.quantity),
            "unit": locked_rec.unit.symbol if locked_rec.unit else "",
            "validation_status": locked_rec.validation_status,
            "evidence_count": locked_rec.evidence_count,
            "verified_by_username": user.username,
            "timestamp": timezone.now().isoformat(),
        },
    )

    # 5. Audit Logging
    log_auth_event(
        event_type=AuthAuditLog.EventType.SUBMISSION_VERIFIED,
        user=user,
        resource_accessed=f"Submission:{locked_sub.id}:Review:{review.id}",
        details=(
            f"Submission #{locked_sub.submission_number} for Record #{locked_rec.id} VERIFIED by {user.username}. "
            f"Site: {locked_sub.site.code}. Quantity: {locked_rec.quantity} {locked_rec.unit.symbol if locked_rec.unit else ''}. "
            f"Comments: {comments[:150] if comments else 'None'}"
        ),
        success=True,
        request=request,
    )

    logger.info(
        "Submission #%d for Record #%d VERIFIED by %s (Review #%d).",
        locked_sub.id,
        locked_rec.id,
        user.username,
        review.id,
    )

    return review


@transaction.atomic
def request_correction_submission(
    submission: Submission,
    user,
    reason: str,
    required_correction: str = "",
    affected_area: str = "ACTIVITY_DATA",
    request=None,
) -> SubmissionReview:
    """
    Executes the Subsidiary Manager's REQUEST CORRECTION decision.

    Guarantees:
    - Atomicity & row-level locking.
    - Non-empty reason validation.
    - Server-side authorization and self-review protection.
    - Valid state transition verification.
    - Status transitions:
        Submission.status -> CORRECTION_REQUESTED
        ActivityRecord.status -> REJECTED (Revision Requested)
    - ActivityRecord original telemetry remains unchanged.
    - Creates historical SubmissionReview record containing detailed correction instructions.
    - Creates formal CorrectionRequest and ensures baseline ActivityRevision is preserved.
    - Emits AuthAuditLog CORRECTION_REQUESTED compliance event.
    """
    reason_clean = (reason or "").strip()
    required_correction_clean = (required_correction or "").strip()

    if not reason_clean:
        raise ValidationError("A reason for requesting correction is required.")

    locked_sub = Submission.objects.select_for_update().select_related("activity_record", "site").get(pk=submission.pk)
    locked_rec = ActivityRecord.objects.select_for_update().get(pk=locked_sub.activity_record_id)

    # 1. Authorization Check
    if not user_can_review_submission(user, locked_sub):
        raise PermissionDenied("You do not have authorization to request correction on this submission.")

    # 2. Transition Check
    is_valid, err_msg = can_transition_submission(locked_sub, ReviewAction.REQUEST_CORRECTION)
    if not is_valid:
        raise ValidationError(err_msg)

    previous_status = locked_sub.status

    # 3. Mutate Lifecycle State
    locked_sub.status = SubmissionStatus.CORRECTION_REQUESTED
    locked_sub.save(update_fields=["status", "updated_at"])

    locked_rec.status = RecordStatus.REJECTED
    locked_rec.updated_by = user
    locked_rec.save(update_fields=["status", "updated_by", "updated_at"])

    # 4. Create Immutable Review Record
    review = SubmissionReview.objects.create(
        submission=locked_sub,
        reviewer=user,
        action=ReviewAction.REQUEST_CORRECTION,
        previous_status=previous_status,
        new_status=SubmissionStatus.CORRECTION_REQUESTED,
        comments=reason_clean,
        required_correction=required_correction_clean,
        metadata={
            "quantity": str(locked_rec.quantity),
            "unit": locked_rec.unit.symbol if locked_rec.unit else "",
            "validation_status": locked_rec.validation_status,
            "evidence_count": locked_rec.evidence_count,
            "affected_area": affected_area,
            "reviewer_username": user.username,
            "timestamp": timezone.now().isoformat(),
        },
    )

    # 5. Create Phase 14 CorrectionRequest & Preserve Baseline Revision
    from apps.core.correction_services import create_correction_request
    create_correction_request(
        submission=locked_sub,
        review=review,
        user=user,
        reason=reason_clean,
        required_correction=required_correction_clean,
        affected_area=affected_area,
    )

    # 6. Audit Logging
    log_auth_event(
        event_type=AuthAuditLog.EventType.CORRECTION_REQUESTED,
        user=user,
        resource_accessed=f"Submission:{locked_sub.id}:Review:{review.id}",
        details=(
            f"Correction requested for Submission #{locked_sub.submission_number} (Record #{locked_rec.id}) by {user.username}. "
            f"Reason: {reason_clean[:120]}. "
            f"Correction Instructions: {required_correction_clean[:120] if required_correction_clean else 'None'}"
        ),
        success=True,
        request=request,
    )

    logger.info(
        "Submission #%d for Record #%d: CORRECTION REQUESTED by %s (Review #%d).",
        locked_sub.id,
        locked_rec.id,
        user.username,
        review.id,
    )

    return review


@transaction.atomic
def explain_submission(
    submission: Submission,
    user,
    explanation: str,
    request=None,
) -> SubmissionReview:
    """
    Executes the Subsidiary Manager's EXPLAIN decision.

    Records contextual explanation / justification for unusual operational readings
    without altering the underlying telemetry or bypassing validation rules.

    Guarantees:
    - Atomicity & row-level locking.
    - Non-empty explanation validation.
    - Server-side authorization and self-review protection.
    - Does NOT convert invalid validation states into valid.
    - ActivityRecord operational telemetry is untouched.
    - Status transitions:
        Submission.status -> EXPLAINED
    - Creates historical SubmissionReview record.
    - Emits AuthAuditLog EXPLANATION_RECORDED compliance event.
    """
    explanation_clean = (explanation or "").strip()
    if not explanation_clean:
        raise ValidationError("An explanation rationale or operating context is required.")

    locked_sub = Submission.objects.select_for_update().select_related("activity_record", "site").get(pk=submission.pk)
    locked_rec = ActivityRecord.objects.select_for_update().get(pk=locked_sub.activity_record_id)

    # 1. Authorization Check
    if not user_can_review_submission(user, locked_sub):
        raise PermissionDenied("You do not have authorization to record explanations for this submission.")

    # 2. Transition Check
    is_valid, err_msg = can_transition_submission(locked_sub, ReviewAction.EXPLAIN)
    if not is_valid:
        raise ValidationError(err_msg)

    previous_status = locked_sub.status

    # 3. Mutate Submission State
    locked_sub.status = SubmissionStatus.EXPLAINED
    locked_sub.save(update_fields=["status", "updated_at"])

    # 4. Create Immutable Review Record
    review = SubmissionReview.objects.create(
        submission=locked_sub,
        reviewer=user,
        action=ReviewAction.EXPLAIN,
        previous_status=previous_status,
        new_status=SubmissionStatus.EXPLAINED,
        comments=explanation_clean,
        metadata={
            "quantity": str(locked_rec.quantity),
            "unit": locked_rec.unit.symbol if locked_rec.unit else "",
            "validation_status": locked_rec.validation_status,
            "evidence_count": locked_rec.evidence_count,
            "reviewer_username": user.username,
            "timestamp": timezone.now().isoformat(),
        },
    )

    # 5. Audit Logging
    log_auth_event(
        event_type=AuthAuditLog.EventType.EXPLANATION_RECORDED,
        user=user,
        resource_accessed=f"Submission:{locked_sub.id}:Review:{review.id}",
        details=(
            f"Explanation recorded for Submission #{locked_sub.submission_number} (Record #{locked_rec.id}) by {user.username}. "
            f"Context: {explanation_clean[:150]}"
        ),
        success=True,
        request=request,
    )

    logger.info(
        "Submission #%d for Record #%d: EXPLANATION RECORDED by %s (Review #%d).",
        locked_sub.id,
        locked_rec.id,
        user.username,
        review.id,
    )

    return review


@transaction.atomic
def escalate_submission(
    submission: Submission,
    user,
    reason: str,
    target_role: str = Role.Code.ESG_MANAGER,
    request=None,
) -> SubmissionReview:
    """
    Executes the Subsidiary Manager's ESCALATE decision.

    Transfers governance jurisdiction to a higher-level governance authority (e.g. ESG_MANAGER).

    Guarantees:
    - Atomicity & row-level locking.
    - Non-empty escalation reason validation.
    - Server-side authorization and self-review protection.
    - ActivityRecord operational telemetry is untouched.
    - Status transitions:
        Submission.status -> ESCALATED
    - Creates historical SubmissionReview record targeting ESG Governance authority.
    - Emits AuthAuditLog SUBMISSION_ESCALATED compliance event.
    """
    reason_clean = (reason or "").strip()
    if not reason_clean:
        raise ValidationError("A reason for escalation is required.")

    locked_sub = Submission.objects.select_for_update().select_related("activity_record", "site").get(pk=submission.pk)
    locked_rec = ActivityRecord.objects.select_for_update().get(pk=locked_sub.activity_record_id)

    # 1. Authorization Check
    if not user_can_review_submission(user, locked_sub):
        raise PermissionDenied("You do not have authorization to escalate this submission.")

    # 2. Transition Check
    is_valid, err_msg = can_transition_submission(locked_sub, ReviewAction.ESCALATE)
    if not is_valid:
        raise ValidationError(err_msg)

    previous_status = locked_sub.status

    # 3. Mutate Submission State
    locked_sub.status = SubmissionStatus.ESCALATED
    locked_sub.save(update_fields=["status", "updated_at"])

    # 4. Create Immutable Review Record
    review = SubmissionReview.objects.create(
        submission=locked_sub,
        reviewer=user,
        action=ReviewAction.ESCALATE,
        previous_status=previous_status,
        new_status=SubmissionStatus.ESCALATED,
        comments=reason_clean,
        escalated_to_role=target_role,
        metadata={
            "quantity": str(locked_rec.quantity),
            "unit": locked_rec.unit.symbol if locked_rec.unit else "",
            "validation_status": locked_rec.validation_status,
            "evidence_count": locked_rec.evidence_count,
            "escalated_by_username": user.username,
            "target_role": target_role,
            "timestamp": timezone.now().isoformat(),
        },
    )

    # 5. Audit Logging
    log_auth_event(
        event_type=AuthAuditLog.EventType.SUBMISSION_ESCALATED,
        user=user,
        resource_accessed=f"Submission:{locked_sub.id}:Review:{review.id}",
        details=(
            f"Submission #{locked_sub.submission_number} (Record #{locked_rec.id}) ESCALATED to {target_role} by {user.username}. "
            f"Reason: {reason_clean[:150]}"
        ),
        success=True,
        request=request,
    )

    logger.info(
        "Submission #%d for Record #%d: ESCALATED to %s by %s (Review #%d).",
        locked_sub.id,
        locked_rec.id,
        target_role,
        user.username,
        review.id,
    )

    return review


# -----------------------------------------------------------------------------
# 4. SUBSIDIARY MANAGER DASHBOARD METRICS AGGREGATION
# -----------------------------------------------------------------------------

def get_subsidiary_manager_dashboard_metrics(user) -> Dict:
    """
    Aggregates authoritative operational review metrics for the Subsidiary Manager.

    Strictly scopes queries to the user's authorized organizational boundaries.
    Does NOT fabricate counts or use hardcoded figures.
    """
    if not user or not user.is_authenticated or not user.is_active:
        raise PermissionDenied("User is not authenticated or account is inactive.")

    assigned_subsidiaries = get_accessible_subsidiaries(user)
    accessible_sites = get_accessible_sites(user)
    accessible_projects = get_accessible_projects(user)
    accessible_subs = get_accessible_submissions(user)

    # Submission status aggregations
    total_submissions = accessible_subs.count()
    pending_count = accessible_subs.filter(status=SubmissionStatus.SUBMITTED).count()
    under_review_count = accessible_subs.filter(status=SubmissionStatus.UNDER_REVIEW).count()
    verified_count = accessible_subs.filter(status__in=[SubmissionStatus.VERIFIED, SubmissionStatus.APPROVED]).count()
    correction_requested_count = accessible_subs.filter(
        status__in=[SubmissionStatus.CORRECTION_REQUESTED, SubmissionStatus.REJECTED]
    ).count()
    explained_count = accessible_subs.filter(status=SubmissionStatus.EXPLAINED).count()
    escalated_count = accessible_subs.filter(status=SubmissionStatus.ESCALATED).count()

    # Validation anomaly count (records with validation warnings or errors in accessible submissions)
    validation_anomalies_count = accessible_subs.filter(
        validation_status__in=[ValidationStatus.WARNING, ValidationStatus.INVALID]
    ).count()

    # Real ESG Anomaly Engine open anomalies count
    try:
        from apps.core.anomaly_services import get_accessible_anomalies
        from apps.core.models import AnomalyStatus
        open_anomalies_count = get_accessible_anomalies(user).filter(
            status__in=[AnomalyStatus.OPEN, AnomalyStatus.ACKNOWLEDGED]
        ).count()
    except Exception:
        open_anomalies_count = 0

    # Recent reviews executed within user's accessible scope
    recent_reviews = (
        SubmissionReview.objects.filter(submission__in=accessible_subs)
        .select_related(
            "submission",
            "submission__activity_record",
            "submission__activity_record__activity",
            "submission__site",
            "submission__reporting_period",
            "reviewer",
        )
        .order_by("-created_at")[:8]
    )

    # Submissions awaiting immediate review
    actionable_inbox = (
        accessible_subs.filter(
            status__in=[SubmissionStatus.SUBMITTED, SubmissionStatus.UNDER_REVIEW, SubmissionStatus.EXPLAINED]
        )
        .select_related(
            "activity_record",
            "activity_record__activity",
            "activity_record__activity__category",
            "site",
            "reporting_period",
            "submitted_by",
            "validation_run",
        )
        .order_by("-submitted_at")[:10]
    )

    return {
        "assigned_subsidiaries": assigned_subsidiaries,
        "subsidiaries_count": assigned_subsidiaries.count(),
        "accessible_sites_count": accessible_sites.count(),
        "accessible_projects_count": accessible_projects.count(),
        "total_submissions_count": total_submissions,
        "pending_count": pending_count,
        "under_review_count": under_review_count,
        "verified_count": verified_count,
        "correction_requested_count": correction_requested_count,
        "explained_count": explained_count,
        "escalated_count": escalated_count,
        "validation_anomalies_count": validation_anomalies_count,
        "open_anomalies_count": open_anomalies_count,
        "recent_reviews": recent_reviews,
        "actionable_inbox": actionable_inbox,
    }
