"""
Views for Subsidiary Manager Review Workspace and Governance Decision Flow.

Fulfills Phase 13 Requirements:
- Subsidiary Manager Review Dashboard (Real metrics & telemetry)
- Submission Review Inbox (Organization-scoped and filtered)
- Comprehensive Submission Review Detail Page (Data, Evidence, OCR, Validation, Decisions)
- Server-side State Decision Actions: Verify, Request Correction, Explain, Escalate
- Anti-IDOR Object-Level Authorization & CSRF Protection
"""

import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.core.auth_services import log_auth_event, role_required
from apps.core.models import (
    ActivityCategory,
    ActivityRecord,
    AuthAuditLog,
    Role,
    Submission,
    SubmissionReview,
    SubmissionStatus,
    ValidationStatus,
)
from apps.core.period_services import get_accessible_reporting_periods
from apps.core.review_forms import (
    EscalateSubmissionForm,
    ExplainSubmissionForm,
    RequestCorrectionForm,
    VerifySubmissionForm,
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
from apps.core.correction_services import (
    compute_submission_deltas,
    get_submission_history_timeline,
)
from apps.core.scope_services import (
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
# 1. SUBSIDIARY MANAGER GOVERNANCE DASHBOARD
# -----------------------------------------------------------------------------

@login_required
@role_required(Role.Code.SUBSIDIARY_MANAGER, Role.Code.MEIL_OPERATOR)
def subsidiary_manager_dashboard_view(request):
    """
    Renders the authoritative Subsidiary Manager Governance Dashboard.
    Surfaces real organizational metrics, pending submissions, and recent reviews.
    """
    user = request.user
    metrics = get_subsidiary_manager_dashboard_metrics(user)

    context = {
        "page_title": "Subsidiary Manager Review Workspace",
        "page_subtitle": "Subsidiary Manager Governance Dashboard — Division ESG Telemetry Review, Validation Audits & Verification Governance",
        "active_nav": "sub_dashboard",
        "role_code": Role.Code.SUBSIDIARY_MANAGER,
        **metrics,
    }
    return render(request, "dashboards/subsidiary_manager.html", context)


# -----------------------------------------------------------------------------
# 2. SUBMISSION REVIEW INBOX
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.MEIL_OPERATOR,
    Role.Code.ESG_MANAGER,
)
def submission_inbox_view(request):
    """
    Renders the organization-scoped Submission Review Inbox for Subsidiary Managers.
    Provides targeted filtering by site, project, reporting period, status, and search query.
    """
    user = request.user
    base_qs = get_accessible_submissions(user)

    # Filtering parameters
    search_query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    site_filter = request.GET.get("site", "").strip()
    period_filter = request.GET.get("period", "").strip()
    category_filter = request.GET.get("category", "").strip()

    qs = base_qs

    if search_query:
        qs = qs.filter(
            models.Q(activity_record__activity__name__icontains=search_query)
            | models.Q(activity_record__activity__code__icontains=search_query)
            | models.Q(site__name__icontains=search_query)
            | models.Q(site__code__icontains=search_query)
            | models.Q(submitted_by__username__icontains=search_query)
            | models.Q(reporting_period__code__icontains=search_query)
        )

    if status_filter:
        qs = qs.filter(status=status_filter)

    if site_filter:
        qs = qs.filter(site_id=site_filter)

    if period_filter:
        qs = qs.filter(reporting_period_id=period_filter)

    if category_filter:
        qs = qs.filter(activity_record__activity__category_id=category_filter)

    # KPI counts for quick tab filters
    total_count = base_qs.count()
    pending_count = base_qs.filter(status=SubmissionStatus.SUBMITTED).count()
    under_review_count = base_qs.filter(status=SubmissionStatus.UNDER_REVIEW).count()
    verified_count = base_qs.filter(status__in=[SubmissionStatus.VERIFIED, SubmissionStatus.APPROVED]).count()
    correction_count = base_qs.filter(status__in=[SubmissionStatus.CORRECTION_REQUESTED, SubmissionStatus.REJECTED]).count()
    explained_count = base_qs.filter(status=SubmissionStatus.EXPLAINED).count()
    escalated_count = base_qs.filter(status=SubmissionStatus.ESCALATED).count()

    # Pagination
    paginator = Paginator(qs, 15)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    # Filter candidates
    accessible_sites = get_accessible_sites(user).order_by("name")
    accessible_periods = get_accessible_reporting_periods(user).order_by("-start_date")
    accessible_categories = ActivityCategory.objects.filter(is_active=True).order_by("name")

    context = {
        "page_title": "Subsidiary Review Inbox",
        "page_subtitle": "Governed First-Line ESG Data Review & Verification Pipeline",
        "active_nav": "submission_inbox",
        "submissions": page_obj,
        "page_obj": page_obj,
        "total_count": total_count,
        "pending_count": pending_count,
        "under_review_count": under_review_count,
        "verified_count": verified_count,
        "correction_count": correction_count,
        "explained_count": explained_count,
        "escalated_count": escalated_count,
        "search_query": search_query,
        "status_filter": status_filter,
        "site_filter": site_filter,
        "period_filter": period_filter,
        "category_filter": category_filter,
        "status_choices": SubmissionStatus.choices,
        "accessible_sites": accessible_sites,
        "accessible_periods": accessible_periods,
        "accessible_categories": accessible_categories,
    }
    return render(request, "submissions/submission_inbox.html", context)


# -----------------------------------------------------------------------------
# 3. SUBMISSION REVIEW DETAIL WORKSPACE
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.MEIL_OPERATOR,
    Role.Code.ESG_MANAGER,
)
def submission_review_detail_view(request, submission_id):
    """
    Renders the comprehensive Subsidiary Manager ESG Review Workspace for a specific Submission.

    Provides multi-pane inspection:
    - Operational Data Review (Read-only activity telemetry, quantities, units, dates)
    - Supporting Evidence Review (Document metadata, SHA-256 hashes, status)
    - OCR Intelligence Review (Run info, confidence, extracted entities vs record comparison)
    - Phase 10 Validation Review (Rules evaluated, severities, findings)
    - Historical Review Decisions Ledger (Previous decisions, comments, timestamps)
    - Review Action Controls (VERIFY, REQUEST CORRECTION, EXPLAIN, ESCALATE)
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
            resource_accessed=f"Submission:{submission_id}:Review",
            details=f"IDOR violation: User '{user.username}' denied access to unassigned Submission #{submission_id}.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have authorization to review this submission.")

    # Review Authority & Self-Approval Evaluation
    can_review = user_can_review_submission(user, submission)
    is_self_submission = (submission.submitted_by_id == user.id)

    record = submission.activity_record
    evidence_files = (
        record.evidence_files.select_related("uploaded_by")
        .prefetch_related("ocr_runs")
        .order_by("-created_at")
    )

    # Aggregate OCR Run Information & Comparison Telemetry across evidence documents
    ocr_runs = []
    ocr_fields = []
    for ev in evidence_files:
        latest_ocr = ev.latest_ocr_run if hasattr(ev, "latest_ocr_run") else None
        if latest_ocr:
            ocr_runs.append(latest_ocr)
            for f in latest_ocr.fields.all():
                ocr_fields.append((ev, f))

    # Phase 10 Validation Run Findings
    val_run = submission.validation_run
    val_results = val_run.results.select_related("rule").order_by("severity", "id") if val_run else []

    # Historical Review Decisions
    reviews = submission.reviews.select_related("reviewer").order_by("-created_at")

    # Review Action Forms
    verify_form = VerifySubmissionForm()
    correction_form = RequestCorrectionForm()
    explain_form = ExplainSubmissionForm()
    escalate_form = EscalateSubmissionForm()
    # Historical Timeline & Revision Comparison Deltas
    timeline = get_submission_history_timeline(submission)
    deltas = compute_submission_deltas(submission)

    # Anomaly Engine Telemetry & Findings
    from apps.core.models import AnomalyRecord
    anomalies = (
        AnomalyRecord.objects.filter(activity_record=record)
        .select_related("rule", "reviewed_by")
        .order_by("-created_at")
    )

    context = {
        "page_title": f"Review: Submission #{submission.submission_number}",
        "page_subtitle": f"{record.activity.name} @ {submission.site.name} ({submission.reporting_period.code})",
        "active_nav": "submission_inbox",
        "submission": submission,
        "record": record,
        "evidence_files": evidence_files,
        "ocr_runs": ocr_runs,
        "ocr_fields": ocr_fields,
        "validation_run": val_run,
        "validation_results": val_results,
        "anomalies": anomalies,
        "reviews": reviews,
        "timeline": timeline,
        "deltas": deltas,
        "is_resubmission": submission.is_resubmission,
        "parent_submission": submission.parent_submission,
        "can_review": can_review,
        "is_self_submission": is_self_submission,
        "verify_form": verify_form,
        "correction_form": correction_form,
        "explain_form": explain_form,
        "escalate_form": escalate_form,
    }
    return render(request, "submissions/submission_review.html", context)


# -----------------------------------------------------------------------------
# 4. REVIEW ACTION HANDLERS (POST ONLY & CSRF PROTECTED)
# -----------------------------------------------------------------------------

@login_required
@role_required(Role.Code.SUBSIDIARY_MANAGER, Role.Code.MEIL_OPERATOR)
def submission_verify_view(request, submission_id):
    """Processes Subsidiary Manager VERIFY review decision."""
    submission = get_object_or_404(
        Submission.objects.select_related("activity_record", "site"),
        pk=submission_id,
    )

    if request.method != "POST":
        return redirect("core:submission_review_detail", submission_id=submission.id)

    # Anti-IDOR Authorization Check
    if not user_can_review_submission(request.user, submission):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Submission:{submission_id}:Verify",
            details=f"Unauthorized verify attempt by {request.user.username}.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have authorization to verify this submission.")

    form = VerifySubmissionForm(request.POST)
    if form.is_valid():
        try:
            comments = form.cleaned_data.get("comments", "").strip()
            review = verify_submission(
                submission=submission,
                user=request.user,
                comments=comments,
                request=request,
            )
            messages.success(
                request,
                f"Submission #{submission.submission_number} successfully VERIFIED for ESG governance.",
            )
        except ValidationError as exc:
            messages.error(request, f"Verification blocked: {exc.message if hasattr(exc, 'message') else str(exc)}")
        except Exception as exc:
            logger.error("Verify failed for Submission #%d: %s", submission.id, exc, exc_info=True)
            messages.error(request, f"An unexpected error occurred during verification: {exc}")
    else:
        err_msg = "; ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
        messages.error(request, f"Please correct form errors: {err_msg}")

    return redirect("core:submission_review_detail", submission_id=submission.id)


@login_required
@role_required(Role.Code.SUBSIDIARY_MANAGER, Role.Code.MEIL_OPERATOR)
def submission_request_correction_view(request, submission_id):
    """Processes Subsidiary Manager REQUEST CORRECTION review decision."""
    submission = get_object_or_404(
        Submission.objects.select_related("activity_record", "site"),
        pk=submission_id,
    )

    if request.method != "POST":
        return redirect("core:submission_review_detail", submission_id=submission.id)

    # Anti-IDOR Authorization Check
    if not user_can_review_submission(request.user, submission):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Submission:{submission_id}:RequestCorrection",
            details=f"Unauthorized correction request attempt by {request.user.username}.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have authorization to request correction on this submission.")

    form = RequestCorrectionForm(request.POST)
    if form.is_valid():
        try:
            reason = form.cleaned_data.get("reason", "").strip()
            required_correction = form.cleaned_data.get("required_correction", "").strip()
            affected_area = form.cleaned_data.get("affected_area", "ACTIVITY_DATA")
            review = request_correction_submission(
                submission=submission,
                user=request.user,
                reason=reason,
                required_correction=required_correction,
                affected_area=affected_area,
                request=request,
            )
            messages.warning(
                request,
                f"Correction requested for Submission #{submission.submission_number}. Status updated to Revision Requested.",
            )
        except ValidationError as exc:
            messages.error(request, f"Correction request blocked: {exc.message if hasattr(exc, 'message') else str(exc)}")
        except Exception as exc:
            logger.error("Request correction failed for Submission #%d: %s", submission.id, exc, exc_info=True)
            messages.error(request, f"An unexpected error occurred: {exc}")
    else:
        err_msg = "; ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
        messages.error(request, f"Please correct form errors: {err_msg}")

    return redirect("core:submission_review_detail", submission_id=submission.id)


@login_required
@role_required(Role.Code.SUBSIDIARY_MANAGER, Role.Code.MEIL_OPERATOR)
def submission_explain_view(request, submission_id):
    """Processes Subsidiary Manager EXPLAIN review decision."""
    submission = get_object_or_404(
        Submission.objects.select_related("activity_record", "site"),
        pk=submission_id,
    )

    if request.method != "POST":
        return redirect("core:submission_review_detail", submission_id=submission.id)

    # Anti-IDOR Authorization Check
    if not user_can_review_submission(request.user, submission):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Submission:{submission_id}:Explain",
            details=f"Unauthorized explanation attempt by {request.user.username}.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have authorization to record explanations for this submission.")

    form = ExplainSubmissionForm(request.POST)
    if form.is_valid():
        try:
            explanation = form.cleaned_data.get("explanation", "").strip()
            review = explain_submission(
                submission=submission,
                user=request.user,
                explanation=explanation,
                request=request,
            )
            messages.info(
                request,
                f"Operating explanation recorded for Submission #{submission.submission_number}.",
            )
        except ValidationError as exc:
            messages.error(request, f"Explanation blocked: {exc.message if hasattr(exc, 'message') else str(exc)}")
        except Exception as exc:
            logger.error("Explain failed for Submission #%d: %s", submission.id, exc, exc_info=True)
            messages.error(request, f"An unexpected error occurred: {exc}")
    else:
        err_msg = "; ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
        messages.error(request, f"Please correct form errors: {err_msg}")

    return redirect("core:submission_review_detail", submission_id=submission.id)


@login_required
@role_required(Role.Code.SUBSIDIARY_MANAGER, Role.Code.MEIL_OPERATOR)
def submission_escalate_view(request, submission_id):
    """Processes Subsidiary Manager ESCALATE review decision to Corporate ESG Manager."""
    submission = get_object_or_404(
        Submission.objects.select_related("activity_record", "site"),
        pk=submission_id,
    )

    if request.method != "POST":
        return redirect("core:submission_review_detail", submission_id=submission.id)

    # Anti-IDOR Authorization Check
    if not user_can_review_submission(request.user, submission):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Submission:{submission_id}:Escalate",
            details=f"Unauthorized escalation attempt by {request.user.username}.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have authorization to escalate this submission.")

    form = EscalateSubmissionForm(request.POST)
    if form.is_valid():
        try:
            reason = form.cleaned_data.get("reason", "").strip()
            target_role = form.cleaned_data.get("target_role", Role.Code.ESG_MANAGER)
            review = escalate_submission(
                submission=submission,
                user=request.user,
                reason=reason,
                target_role=target_role,
                request=request,
            )
            messages.warning(
                request,
                f"Submission #{submission.submission_number} ESCALATED to Corporate ESG Governance.",
            )
        except ValidationError as exc:
            messages.error(request, f"Escalation blocked: {exc.message if hasattr(exc, 'message') else str(exc)}")
        except Exception as exc:
            logger.error("Escalate failed for Submission #%d: %s", submission.id, exc, exc_info=True)
            messages.error(request, f"An unexpected error occurred: {exc}")
    else:
        err_msg = "; ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
        messages.error(request, f"Please correct form errors: {err_msg}")

    return redirect("core:submission_review_detail", submission_id=submission.id)
