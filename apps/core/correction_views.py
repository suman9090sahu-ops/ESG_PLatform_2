"""
Views for Site Manager Correction, Revision, and Resubmission Workflows.

Fulfills Phase 14 Requirements:
- Site Manager Correction Inbox (Filtered by assigned sites, statuses, and search)
- Comprehensive Correction Detail View (Original submission, review reason, changes, evidence, validation)
- Server-side Data Editing Controls restricted to approved operational fields
- Integrated Validation Engine Re-run before Resubmission
- Controlled, Audited Resubmission Handler creating versioned submission iterations
- Anti-IDOR Authorization and CSRF Protection
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
from apps.core.correction_forms import CorrectionUpdateForm, ResubmitCorrectionForm
from apps.core.correction_services import (
    get_accessible_correction_requests,
    get_submission_history_timeline,
    resubmit_corrected_activity,
    start_correction,
    update_corrected_record,
    user_can_access_correction_request,
    user_can_edit_correction_request,
)
from apps.core.models import (
    ActivityRecord,
    AuthAuditLog,
    CorrectionAffectedArea,
    CorrectionRequest,
    CorrectionStatus,
    Role,
    Submission,
    ValidationStatus,
)
from apps.core.scope_services import get_accessible_sites
from apps.core.validation_services import execute_validation_run

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. SITE MANAGER CORRECTION INBOX
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.SITE_MANAGER,
    Role.Code.MEIL_OPERATOR,
    Role.Code.ESG_MANAGER,
    Role.Code.AUDITOR,
)
def correction_inbox_view(request):
    """
    Renders the Site Manager Correction Inbox.
    Surfaces all pending and historical correction requests for assigned sites.
    """
    user = request.user
    accessible_qs = get_accessible_correction_requests(user)

    # Calculate status counts for KPI widgets
    counts_map = (
        accessible_qs.values("status")
        .annotate(total=models.Count("id"))
    )
    kpis = {
        CorrectionStatus.OPEN: 0,
        CorrectionStatus.IN_PROGRESS: 0,
        CorrectionStatus.READY_FOR_RESUBMISSION: 0,
        CorrectionStatus.RESOLVED: 0,
    }
    for item in counts_map:
        if item["status"] in kpis:
            kpis[item["status"]] = item["total"]

    total_count = accessible_qs.count()
    active_count = (
        kpis[CorrectionStatus.OPEN]
        + kpis[CorrectionStatus.IN_PROGRESS]
        + kpis[CorrectionStatus.READY_FOR_RESUBMISSION]
    )

    # Filter by Status
    status_filter = request.GET.get("status", "").strip()
    if status_filter == "ALL":
        filtered_qs = accessible_qs
    elif status_filter in CorrectionStatus.values:
        filtered_qs = accessible_qs.filter(status=status_filter)
    else:
        # Default: show active unresolved correction requests
        filtered_qs = accessible_qs.filter(
            status__in=[
                CorrectionStatus.OPEN,
                CorrectionStatus.IN_PROGRESS,
                CorrectionStatus.READY_FOR_RESUBMISSION,
            ]
        )

    # Filter by Site
    site_id = request.GET.get("site", "").strip()
    if site_id.isdigit():
        filtered_qs = filtered_qs.filter(activity_record__site_id=int(site_id))

    # Search query
    query = request.GET.get("q", "").strip()
    if query:
        filtered_qs = filtered_qs.filter(
            models.Q(activity_record__activity__name__icontains=query)
            | models.Q(activity_record__activity__code__icontains=query)
            | models.Q(reason__icontains=query)
            | models.Q(required_correction__icontains=query)
            | models.Q(activity_record__site__name__icontains=query)
        )

    # Pagination
    paginator = Paginator(filtered_qs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    assigned_sites = get_accessible_sites(user)

    context = {
        "page_title": "Site Manager Correction Inbox",
        "page_subtitle": "Review Discrepancies, Revise Operational Telemetry & Execute Resubmissions",
        "active_nav": "corrections",
        "corrections": page_obj,
        "page_obj": page_obj,
        "kpis": kpis,
        "total_count": total_count,
        "active_count": active_count,
        "current_status": status_filter or "ACTIVE",
        "current_site_id": site_id,
        "assigned_sites": assigned_sites,
        "search_query": query,
        "status_choices": CorrectionStatus.choices,
    }
    return render(request, "corrections/correction_inbox.html", context)


# -----------------------------------------------------------------------------
# 2. CORRECTION DETAIL WORKSPACE
# -----------------------------------------------------------------------------

@login_required
def correction_detail_view(request, correction_id):
    """
    Renders the detailed Correction Workspace for an individual CorrectionRequest.

    Displays:
    - Authoritative Review Decision, Requester, Reason, and Instructions
    - Side-by-side Original Submitted Telemetry vs Current Value
    - Supporting Evidence document files and OCR intelligence
    - Phase 10 Validation Run status and rule findings
    - Correctable operational data form
    - Resubmission confirmation controls
    - Complete chronological audit timeline
    """
    user = request.user
    correction_req = get_object_or_404(
        CorrectionRequest.objects.select_related(
            "activity_record",
            "activity_record__activity",
            "activity_record__activity__category",
            "activity_record__activity__base_unit",
            "activity_record__unit",
            "activity_record__site",
            "activity_record__site__project",
            "activity_record__site__project__subsidiary",
            "activity_record__site__project__subsidiary__company",
            "activity_record__reporting_period",
            "submission",
            "submission__submitted_by",
            "review",
            "review__reviewer",
            "requested_by",
            "resolved_by",
            "resubmission",
        ),
        pk=correction_id,
    )

    # Anti-IDOR Authorization Check
    if not user_can_access_correction_request(user, correction_req):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"CorrectionRequest:{correction_id}:View",
            details=f"IDOR violation: User '{user.username}' denied access to unassigned CorrectionRequest #{correction_id}.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have authorization to view this correction request.")

    record = correction_req.activity_record
    can_edit = user_can_edit_correction_request(user, correction_req)

    # Auto-transition from OPEN to IN_PROGRESS when authorized Site Manager opens work
    if can_edit and correction_req.status == CorrectionStatus.OPEN:
        try:
            correction_req = start_correction(correction_req, user, request=request)
        except Exception as e:
            logger.warning("Could not auto-start correction #%d: %s", correction_req.id, str(e))

    # Evidence files attached to the record
    evidence_files = (
        record.evidence_files.select_related("uploaded_by")
        .prefetch_related("ocr_runs")
        .order_by("-created_at")
    )

    # Latest Validation Run findings
    val_run = record.latest_validation_run
    val_results = val_run.results.select_related("rule").order_by("severity", "id") if val_run else []

    # Historical timeline
    timeline = get_submission_history_timeline(correction_req.submission)

    # Forms
    update_form = CorrectionUpdateForm(
        instance=record,
        initial={"site_manager_notes": correction_req.site_manager_notes},
    )
    resubmit_form = ResubmitCorrectionForm(
        initial={"resubmission_comments": correction_req.site_manager_notes}
    )

    # Baseline comparison data
    prev_snapshot = correction_req.submission.snapshot_data or {}

    context = {
        "page_title": f"Correction Request #{correction_req.id}",
        "page_subtitle": f"{record.activity.name} @ {record.site.name} ({record.reporting_period.code})",
        "active_nav": "corrections",
        "correction_req": correction_req,
        "record": record,
        "submission": correction_req.submission,
        "review": correction_req.review,
        "can_edit": can_edit,
        "evidence_files": evidence_files,
        "val_run": val_run,
        "val_results": val_results,
        "timeline": timeline,
        "update_form": update_form,
        "resubmit_form": resubmit_form,
        "prev_snapshot": prev_snapshot,
        "is_ready_for_resubmission": (
            can_edit
            and not correction_req.is_resolved
            and record.validation_status in [ValidationStatus.VALID, ValidationStatus.WARNING]
            and (not record.activity.requires_evidence or record.has_evidence)
        ),
    }
    return render(request, "corrections/correction_detail.html", context)


# -----------------------------------------------------------------------------
# 3. SITE MANAGER DATA CORRECTION HANDLER (POST ONLY)
# -----------------------------------------------------------------------------

@login_required
def correction_edit_view(request, correction_id):
    """
    Handles POST requests from Site Manager to update correctable operational telemetry.
    Revalidates using Phase 10 Validation Engine and updates correction lifecycle status.
    """
    if request.method != "POST":
        return redirect("core:correction_detail", correction_id=correction_id)

    correction_req = get_object_or_404(
        CorrectionRequest.objects.select_related("activity_record", "submission"),
        pk=correction_id,
    )

    if not user_can_edit_correction_request(request.user, correction_req):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"CorrectionRequest:{correction_id}:Edit",
            details=f"Unauthorized correction edit attempt by {request.user.username}.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have authorization to edit this record.")

    form = CorrectionUpdateForm(request.POST, instance=correction_req.activity_record)
    if form.is_valid():
        try:
            record, val_run = update_corrected_record(
                correction_req=correction_req,
                user=request.user,
                form_data=form.cleaned_data,
                request=request,
            )
            val_status_display = record.get_validation_status_display()
            if record.validation_status in [ValidationStatus.VALID, ValidationStatus.WARNING]:
                messages.success(
                    request,
                    f"Operational changes saved successfully! Revalidation passed ({val_status_display}). Record is ready for resubmission.",
                )
            else:
                messages.warning(
                    request,
                    f"Operational changes saved, but validation failed ({val_status_display}). Please resolve blocking validation errors before resubmitting.",
                )
        except ValidationError as e:
            messages.error(request, f"Validation Error: {e.message}")
        except Exception as e:
            logger.exception("Error updating corrected record #%d: %s", correction_req.activity_record_id, str(e))
            messages.error(request, f"An unexpected error occurred while saving changes: {str(e)}")
    else:
        err_msg = "; ".join([f"{f}: {', '.join(errs)}" for f, errs in form.errors.items()])
        messages.error(request, f"Please correct form errors: {err_msg}")

    return redirect("core:correction_detail", correction_id=correction_id)


# -----------------------------------------------------------------------------
# 4. SITE MANAGER REVALIDATION TRIGGER (POST ONLY)
# -----------------------------------------------------------------------------

@login_required
def correction_validate_view(request, correction_id):
    """
    Explicitly re-runs the Phase 10 Validation Engine on a corrected record.
    """
    if request.method != "POST":
        return redirect("core:correction_detail", correction_id=correction_id)

    correction_req = get_object_or_404(
        CorrectionRequest.objects.select_related("activity_record"),
        pk=correction_id,
    )

    if not user_can_edit_correction_request(request.user, correction_req):
        raise PermissionDenied("Access Denied: You do not have authorization to validate this record.")

    record = correction_req.activity_record
    val_run = execute_validation_run(record, executed_by=request.user, request=request)
    record.refresh_from_db()

    if record.validation_status in [ValidationStatus.VALID, ValidationStatus.WARNING]:
        if correction_req.status != CorrectionStatus.RESOLVED:
            correction_req.status = CorrectionStatus.READY_FOR_RESUBMISSION
            correction_req.save(update_fields=["status", "updated_at"])
        messages.success(
            request,
            f"Validation run #{val_run.run_number} completed: {record.get_validation_status_display()}. Record is eligible for resubmission.",
        )
    else:
        messages.error(
            request,
            f"Validation run #{val_run.run_number} failed with blocking errors. Please resolve errors before resubmitting.",
        )

    return redirect("core:correction_detail", correction_id=correction_id)


# -----------------------------------------------------------------------------
# 5. SITE MANAGER RESUBMISSION HANDLER (POST ONLY)
# -----------------------------------------------------------------------------

@login_required
def correction_resubmit_view(request, correction_id):
    """
    Handles formal Resubmission of a corrected ActivityRecord back to Subsidiary Review.
    """
    if request.method != "POST":
        return redirect("core:correction_detail", correction_id=correction_id)

    correction_req = get_object_or_404(
        CorrectionRequest.objects.select_related("activity_record", "submission"),
        pk=correction_id,
    )

    if not user_can_edit_correction_request(request.user, correction_req):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"CorrectionRequest:{correction_id}:Resubmit",
            details=f"Unauthorized resubmission attempt by {request.user.username}.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have authorization to resubmit this record.")

    form = ResubmitCorrectionForm(request.POST)
    if form.is_valid():
        try:
            comments = form.cleaned_data.get("resubmission_comments", "")
            new_submission = resubmit_corrected_activity(
                correction_req=correction_req,
                user=request.user,
                comments=comments,
                request=request,
            )
            messages.success(
                request,
                f"Activity record successfully resubmitted as Iteration #{new_submission.submission_number}! It has returned to the Subsidiary Manager review queue.",
            )
            return redirect("core:submission_detail", submission_id=new_submission.id)
        except ValidationError as e:
            messages.error(request, f"Resubmission rejected: {e.message if hasattr(e, 'message') else str(e)}")
        except Exception as e:
            logger.exception("Error during resubmission of correction #%d: %s", correction_id, str(e))
            messages.error(request, f"An unexpected error occurred during resubmission: {str(e)}")
    else:
        err_msg = "; ".join([f"{f}: {', '.join(errs)}" for f, errs in form.errors.items()])
        messages.error(request, f"Resubmission failed: {err_msg}")

    return redirect("core:correction_detail", correction_id=correction_id)
