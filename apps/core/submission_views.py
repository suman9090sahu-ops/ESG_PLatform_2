"""
Views for Activity Record Submissions and Downstream Review Handover.

Fulfills Phase 12 Requirements:
- Formal Submission Confirmation & Trigger View (activity_record_submit_view)
- Scoped Submissions Ledger & Telemetry View (submission_list_view)
- Multi-tier Lineage Submission Detail View (submission_detail_view)
- Safe Submitter Withdrawal View (submission_withdraw_view)
- Anti-IDOR Object-Level Access Enforcement
- Full CSRF & POST Security
"""

import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.core.auth_services import log_auth_event, role_required
from apps.core.data_entry_services import (
    get_accessible_activity_records,
    user_can_access_activity_record,
)
from apps.core.models import (
    ActivityRecord,
    AuthAuditLog,
    OrganizationStatus,
    PeriodStatus,
    RecordStatus,
    Role,
    Site,
    Submission,
    SubmissionStatus,
    ValidationStatus,
)
from apps.core.scope_services import (
    get_accessible_sites,
    user_can_access_site,
)
from apps.core.period_services import get_accessible_reporting_periods
from apps.core.submission_forms import (
    ActivityRecordSubmitForm,
    SubmissionWithdrawForm,
)
from apps.core.review_services import user_can_review_submission
from apps.core.submission_services import (
    check_submission_eligibility,
    get_accessible_submissions,
    submit_activity_record,
    user_can_access_submission,
    user_can_submit_activity_record,
    withdraw_submission,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. FORMAL SUBMISSION TRIGGER & CONFIRMATION
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.SITE_MANAGER,
    Role.Code.MEIL_OPERATOR,
    Role.Code.ESG_MANAGER,
)
def activity_record_submit_view(request, record_id):
    """
    Renders the submission confirmation gate and processes the formal POST submission.
    Server-enforces object-level scoping and eligibility checks before committing state.
    """
    user = request.user
    record = get_object_or_404(
        ActivityRecord.objects.select_related(
            "site",
            "site__project",
            "site__project__subsidiary",
            "site__project__subsidiary__company",
            "reporting_period",
            "activity",
            "activity__category",
            "activity__base_unit",
            "unit",
            "created_by",
            "updated_by",
        ),
        pk=record_id,
    )

    # Anti-IDOR Authorization Check
    if not user_can_access_activity_record(user, record) or not user_can_access_site(user, record.site):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"ActivityRecord:{record_id}:Submit",
            details=f"Unauthorized submission attempt for Site {record.site.code} by user {user.username}.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have authorization to submit this activity record.")

    # If record is already SUBMITTED, inform user and redirect to submission detail
    if record.status == RecordStatus.SUBMITTED:
        latest_sub = record.latest_submission
        if latest_sub:
            messages.info(
                request,
                f"Activity Record #{record.id} has already been submitted for review (Submission #{latest_sub.submission_number}).",
            )
            return redirect("core:submission_detail", submission_id=latest_sub.id)
        else:
            messages.info(request, f"Activity Record #{record.id} is already in SUBMITTED status.")
            return redirect("core:activity_record_detail", record_id=record.id)

    # Evaluate full server-side eligibility
    is_eligible, errors, warnings = check_submission_eligibility(user, record)

    evidence_files = record.evidence_files.select_related("uploaded_by").order_by("-created_at")
    latest_run = record.latest_validation_run
    validation_results = latest_run.results.select_related("rule").order_by("severity", "id") if latest_run else []

    if request.method == "POST":
        form = ActivityRecordSubmitForm(request.POST)
        if not is_eligible:
            err_msg = "; ".join(errors)
            messages.error(request, f"Cannot submit record: {err_msg}")
        elif form.is_valid():
            try:
                comments = form.cleaned_data.get("comments", "").strip()
                submission = submit_activity_record(
                    record=record,
                    user=user,
                    comments=comments,
                    request=request,
                    force_revalidate=True,
                )
                messages.success(
                    request,
                    f"Activity Record #{record.id} successfully submitted for downstream review (Submission #{submission.submission_number}).",
                )
                return redirect("core:submission_detail", submission_id=submission.id)
            except ValidationError as exc:
                messages.error(request, f"Submission blocked: {exc.message if hasattr(exc, 'message') else str(exc)}")
            except Exception as exc:
                logger.error("Submission failed for Record #%d: %s", record.id, exc, exc_info=True)
                messages.error(request, f"An unexpected error occurred during submission: {exc}")
    else:
        form = ActivityRecordSubmitForm()

    context = {
        "page_title": f"Submit Activity Record #{record.id}",
        "page_subtitle": f"{record.activity.name} @ {record.site.name}",
        "active_nav": "submissions",
        "record": record,
        "form": form,
        "is_eligible": is_eligible,
        "errors": errors,
        "warnings": warnings,
        "evidence_files": evidence_files,
        "latest_validation_run": latest_run,
        "validation_results": validation_results,
    }
    return render(request, "submissions/submission_confirm.html", context)


# -----------------------------------------------------------------------------
# 2. SUBMISSIONS LIST LEDGER
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.SITE_MANAGER,
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.ESG_MANAGER,
    Role.Code.AUDITOR,
    Role.Code.MEIL_OPERATOR,
)
def submission_list_view(request):
    """
    Renders the scoped ledger of activity submissions.
    Supports filtering by site, period, status, and text search.
    """
    user = request.user
    base_qs = get_accessible_submissions(user)

    # Filter parameters
    search_query = request.GET.get("q", "").strip()
    site_filter = request.GET.get("site", "").strip()
    period_filter = request.GET.get("period", "").strip()
    status_filter = request.GET.get("status", "").strip()

    qs = base_qs

    if search_query:
        qs = qs.filter(
            models.Q(activity_record__activity__name__icontains=search_query)
            | models.Q(activity_record__activity__code__icontains=search_query)
            | models.Q(site__name__icontains=search_query)
            | models.Q(site__code__icontains=search_query)
            | models.Q(reporting_period__code__icontains=search_query)
            | models.Q(submitted_by__username__icontains=search_query)
        )

    if site_filter:
        qs = qs.filter(site_id=site_filter)

    if period_filter:
        qs = qs.filter(reporting_period_id=period_filter)

    if status_filter:
        qs = qs.filter(status=status_filter)

    # Summary KPI aggregations
    total_count = base_qs.count()
    pending_count = base_qs.filter(status=SubmissionStatus.SUBMITTED).count()
    under_review_count = base_qs.filter(status=SubmissionStatus.UNDER_REVIEW).count()
    approved_count = base_qs.filter(status=SubmissionStatus.APPROVED).count()
    withdrawn_count = base_qs.filter(status=SubmissionStatus.WITHDRAWN).count()

    # Pagination
    paginator = Paginator(qs, 15)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    # Dropdown candidate selectors
    accessible_sites = get_accessible_sites(user).order_by("name")
    accessible_periods = get_accessible_reporting_periods(user).order_by("-start_date")

    context = {
        "page_title": "Activity Submissions",
        "page_subtitle": "Governed Handover Ledger & Downstream Review Pipeline",
        "active_nav": "submissions" if user.has_role(Role.Code.SITE_MANAGER) else "submission_inbox",
        "submissions": page_obj,
        "page_obj": page_obj,
        "total_count": total_count,
        "pending_count": pending_count,
        "under_review_count": under_review_count,
        "approved_count": approved_count,
        "withdrawn_count": withdrawn_count,
        "search_query": search_query,
        "site_filter": site_filter,
        "period_filter": period_filter,
        "status_filter": status_filter,
        "status_choices": SubmissionStatus.choices,
        "accessible_sites": accessible_sites,
        "accessible_periods": accessible_periods,
    }
    return render(request, "submissions/submission_list.html", context)


# -----------------------------------------------------------------------------
# 3. SUBMISSION DETAIL & AUDIT LINEAGE
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.SITE_MANAGER,
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.ESG_MANAGER,
    Role.Code.AUDITOR,
    Role.Code.MEIL_OPERATOR,
)
def submission_detail_view(request, submission_id):
    """
    Renders detailed submission audit lineage connecting:
    Submission -> Activity Record -> Activity Master -> Site Hierarchy -> Period -> Evidence -> OCR -> Validation Run.
    """
    user = request.user
    submission = get_object_or_404(
        Submission.objects.select_related(
            "activity_record",
            "activity_record__activity",
            "activity_record__activity__category",
            "activity_record__activity__base_unit",
            "activity_record__unit",
            "activity_record__created_by",
            "site",
            "site__project",
            "site__project__subsidiary",
            "site__project__subsidiary__company",
            "reporting_period",
            "submitted_by",
            "validation_run",
            "validation_run__executed_by",
        ),
        pk=submission_id,
    )

    # Anti-IDOR Authorization Check
    if not user_can_access_submission(user, submission):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"Submission:{submission_id}",
            details=f"Unauthorized access attempt to Submission #{submission_id} by {user.username}.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have authorization to view this submission.")

    record = submission.activity_record
    evidence_files = record.evidence_files.select_related("uploaded_by").order_by("-created_at")

    # Validation findings from the evaluated run at submission
    validation_run = submission.validation_run
    validation_results = []
    if validation_run:
        validation_results = validation_run.results.select_related("rule").order_by("severity", "id")

    # Evaluate whether submitter can withdraw
    can_withdraw = (
        submission.status == SubmissionStatus.SUBMITTED
        and user_can_submit_activity_record(user, record)
        and submission.reporting_period.allows_data_modification
    )
    withdraw_form = SubmissionWithdrawForm() if can_withdraw else None

    # Fetch audit events relating to this submission
    audit_logs = AuthAuditLog.objects.filter(
        models.Q(resource_accessed__icontains=f"Submission:{submission.id}")
        | models.Q(resource_accessed__icontains=f"ActivityRecord:{record.id}")
    ).order_by("-created_at")[:10]

    # Check if current user is an authorized reviewer for this submission
    can_review = user_can_review_submission(user, submission)

    context = {
        "page_title": f"Submission #{submission.submission_number}",
        "page_subtitle": f"{record.activity.name} @ {submission.site.name}",
        "active_nav": "submissions" if user.has_role(Role.Code.SITE_MANAGER) else "submission_inbox",
        "submission": submission,
        "record": record,
        "evidence_files": evidence_files,
        "validation_run": validation_run,
        "validation_results": validation_results,
        "can_withdraw": can_withdraw,
        "withdraw_form": withdraw_form,
        "can_review": can_review,
        "audit_logs": audit_logs,
    }
    return render(request, "submissions/submission_detail.html", context)


# -----------------------------------------------------------------------------
# 4. SUBMISSION WITHDRAWAL
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.SITE_MANAGER,
    Role.Code.MEIL_OPERATOR,
    Role.Code.ESG_MANAGER,
)
def submission_withdraw_view(request, submission_id):
    """
    Processes submitter withdrawal of an active submission prior to downstream review.
    Reverts the associated ActivityRecord back to DRAFT state.
    """
    user = request.user
    submission = get_object_or_404(
        Submission.objects.select_related("activity_record", "site", "reporting_period"),
        pk=submission_id,
    )

    if not user_can_access_submission(user, submission) or not user_can_submit_activity_record(user, submission.activity_record):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"Submission:{submission_id}:Withdraw",
            details=f"Unauthorized withdrawal attempt for Submission #{submission_id} by {user.username}.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have permission to withdraw this submission.")

    if request.method != "POST":
        return redirect("core:submission_detail", submission_id=submission.id)

    form = SubmissionWithdrawForm(request.POST)
    if form.is_valid():
        reason = form.cleaned_data.get("reason", "").strip()
        try:
            withdraw_submission(
                submission=submission,
                user=user,
                reason=reason,
                request=request,
            )
            messages.success(
                request,
                f"Submission #{submission.submission_number} successfully withdrawn. Activity Record #{submission.activity_record_id} reverted to DRAFT for revision.",
            )
            return redirect("core:activity_record_detail", record_id=submission.activity_record_id)
        except ValidationError as exc:
            messages.error(request, f"Withdrawal error: {exc.message if hasattr(exc, 'message') else str(exc)}")
        except Exception as exc:
            logger.error("Failed to withdraw submission #%d: %s", submission.id, exc, exc_info=True)
            messages.error(request, f"Unexpected error during withdrawal: {exc}")
    else:
        err_msg = "; ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
        messages.error(request, f"Please correct form errors: {err_msg}")

    return redirect("core:submission_detail", submission_id=submission.id)
