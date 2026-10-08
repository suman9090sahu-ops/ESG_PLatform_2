"""
Evidence Management Views for MEIL ESG CONTROL TOWER.

Fulfills Phase 09 Requirements:
- Scoped Evidence Repository List (evidence_list_view)
- Document Metadata & Traceability Inspection (evidence_detail_view)
- Secure File Upload Workflow (evidence_upload_view)
- Object-Authorized Binary Download (evidence_download_view)
- Inline Secure Preview for PDFs and Images (evidence_preview_view)
- Controlled Lifecycle Retirement (evidence_retire_view)
- Safe Draft Deletion (evidence_delete_view)
"""

import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.auth_services import log_auth_event, role_required
from apps.core.evidence_forms import (
    EvidenceFilterForm,
    EvidenceRetireForm,
    EvidenceUploadForm,
)
from apps.core.evidence_services import (
    create_evidence_record,
    delete_evidence_record,
    get_accessible_evidence,
    log_evidence_event,
    retire_evidence_record,
    user_can_access_evidence,
    user_can_delete_evidence,
    user_can_download_evidence,
    user_can_retire_evidence,
    user_can_upload_evidence,
)
from apps.core.models import (
    ActivityRecord,
    AuthAuditLog,
    Evidence,
    EvidenceStatus,
    Role,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. SCOPED EVIDENCE REPOSITORY LIST
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.SITE_MANAGER,
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.MEIL_OPERATOR,
    Role.Code.ESG_MANAGER,
    Role.Code.AUDITOR,
)
def evidence_list_view(request):
    """
    Displays the scoped list of all supporting evidence documents accessible
    to the authenticated user, with filtering by site, period, type, and keyword.
    """
    user = request.user
    qs = get_accessible_evidence(user, include_retired=True)

    filter_form = EvidenceFilterForm(request.GET, user=user)
    if filter_form.is_valid():
        site = filter_form.cleaned_data.get("site")
        period = filter_form.cleaned_data.get("reporting_period")
        ev_type = filter_form.cleaned_data.get("evidence_type")
        status = filter_form.cleaned_data.get("status")
        query = filter_form.cleaned_data.get("q")

        if site:
            qs = qs.filter(activity_record__site=site)
        if period:
            qs = qs.filter(activity_record__reporting_period=period)
        if ev_type:
            qs = qs.filter(evidence_type=ev_type)
        if status:
            qs = qs.filter(status=status)
        if query:
            qs = qs.filter(
                Q(original_filename__icontains=query)
                | Q(description__icontains=query)
                | Q(activity_record__activity__name__icontains=query)
                | Q(activity_record__evidence_reference__icontains=query)
            )

    # Aggregate KPIs
    total_docs = qs.count()
    active_docs = qs.filter(status=EvidenceStatus.ACTIVE).count()
    retired_docs = qs.filter(status=EvidenceStatus.RETIRED).count()
    total_bytes = qs.aggregate(Sum("file_size"))["file_size__sum"] or 0

    if total_bytes < 1024 * 1024:
        total_storage_formatted = f"{total_bytes / 1024:.1f} KB"
    else:
        total_storage_formatted = f"{total_bytes / (1024 * 1024):.2f} MB"

    # Pagination
    paginator = Paginator(qs, 20)
    page_number = request.GET.get("page", 1)
    try:
        page_obj = paginator.page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)

    context = {
        "page_title": "Audit Evidence Repository",
        "page_subtitle": "Traceable ESG Supporting Documents & Verification Invoices",
        "active_nav": "evidence",
        "evidence_list": page_obj,
        "filter_form": filter_form,
        "total_docs": total_docs,
        "active_docs": active_docs,
        "retired_docs": retired_docs,
        "total_storage_formatted": total_storage_formatted,
    }
    return render(request, "evidence/evidence_list.html", context)


# -----------------------------------------------------------------------------
# 2. EVIDENCE DETAIL VIEW
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.SITE_MANAGER,
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.MEIL_OPERATOR,
    Role.Code.ESG_MANAGER,
    Role.Code.AUDITOR,
)
def evidence_detail_view(request, evidence_id):
    """
    Displays full details, metadata, SHA-256 hash, and ESG relational lineage
    for an individual Evidence document.
    """
    user = request.user
    evidence = get_object_or_404(
        Evidence.objects.select_related(
            "activity_record",
            "activity_record__site",
            "activity_record__site__project",
            "activity_record__site__project__subsidiary",
            "activity_record__site__project__subsidiary__company",
            "activity_record__reporting_period",
            "activity_record__activity",
            "activity_record__activity__category",
            "activity_record__unit",
            "uploaded_by",
            "retired_by",
        ),
        pk=evidence_id,
    )

    if not user_can_access_evidence(user, evidence):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"Evidence:{evidence_id}",
            details=f"Unauthorized attempt to inspect evidence for site {evidence.site.code}.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have permission to view this evidence document.")

    can_download = user_can_download_evidence(user, evidence)
    can_retire = user_can_retire_evidence(user, evidence)
    can_delete = user_can_delete_evidence(user, evidence)

    # Phase 11: OCR Processing & Entity Intelligence
    from apps.core.ocr_services import user_can_process_ocr
    can_process_ocr = user_can_process_ocr(user, evidence)
    latest_ocr_run = evidence.latest_ocr_run
    ocr_runs = evidence.ocr_runs.order_by("-run_number")
    ocr_fields = latest_ocr_run.fields.all() if latest_ocr_run else []
    ocr_comparison = latest_ocr_run.comparison_summary if latest_ocr_run else {}

    context = {
        "page_title": f"Evidence #{evidence.id}",
        "page_subtitle": f"{evidence.original_filename} ({evidence.get_evidence_type_display()})",
        "active_nav": "evidence",
        "evidence": evidence,
        "can_download": can_download,
        "can_retire": can_retire,
        "can_delete": can_delete,
        "can_process_ocr": can_process_ocr,
        "latest_ocr_run": latest_ocr_run,
        "ocr_runs": ocr_runs,
        "ocr_fields": ocr_fields,
        "ocr_comparison": ocr_comparison,
    }
    return render(request, "evidence/evidence_detail.html", context)


# -----------------------------------------------------------------------------
# 3. EVIDENCE UPLOAD VIEW
# -----------------------------------------------------------------------------

@login_required
@role_required(Role.Code.SITE_MANAGER, Role.Code.MEIL_OPERATOR, Role.Code.ESG_MANAGER)
def evidence_upload_view(request, record_id):
    """
    Handles uploading a supporting document against a specific ActivityRecord.
    Server validates permissions, organizational boundaries, and file integrity.
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
            "unit",
        ),
        pk=record_id,
    )

    if not user_can_upload_evidence(user, record):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"ActivityRecord:{record_id}/evidence/upload",
            details="Unauthorized attempt to upload evidence for activity record.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to attach evidence to this activity record.")

    if request.method == "POST":
        form = EvidenceUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                evidence = create_evidence_record(
                    activity_record=record,
                    uploaded_file=form.cleaned_data["file"],
                    evidence_type=form.cleaned_data["evidence_type"],
                    description=form.cleaned_data.get("description", ""),
                    user=user,
                    request=request,
                )
                messages.success(
                    request,
                    f"Evidence document '{evidence.original_filename}' uploaded successfully for {record.activity.name}."
                )
                return redirect("core:activity_record_detail", record_id=record.id)
            except Exception as e:
                logger.error("Error creating evidence record: %s", e)
                messages.error(request, f"Upload error: {str(e)}")
    else:
        form = EvidenceUploadForm()

    context = {
        "page_title": "Attach Supporting Evidence",
        "page_subtitle": f"Record #{record.id}: {record.activity.name} @ {record.site.name}",
        "active_nav": "data_entry",
        "record": record,
        "form": form,
    }
    return render(request, "evidence/evidence_upload.html", context)


# -----------------------------------------------------------------------------
# 4. SECURE EVIDENCE DOWNLOAD
# -----------------------------------------------------------------------------

@login_required
def evidence_download_view(request, evidence_id):
    """
    Streams the evidence file securely to authorized users as an attachment.
    Enforces object-level authorization and records an audit log event.
    """
    user = request.user
    evidence = get_object_or_404(
        Evidence.objects.select_related("activity_record", "activity_record__site"),
        pk=evidence_id,
    )

    if not user_can_download_evidence(user, evidence):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"Evidence:{evidence_id}/download",
            details=f"Unauthorized download attempt for evidence #{evidence_id}.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have permission to download this evidence document.")

    if not evidence.file or not evidence.file.storage.exists(evidence.file.name):
        logger.error("Evidence file missing on storage: %s", evidence.file.name if evidence.file else "None")
        raise Http404("The requested file does not exist on storage.")

    # Record download audit event
    log_evidence_event(
        AuthAuditLog.EventType.EVIDENCE_DOWNLOADED,
        evidence=evidence,
        user=user,
        request=request,
        details=f"Downloaded file '{evidence.original_filename}' ({evidence.file_size_formatted}).",
    )

    response = FileResponse(
        evidence.file.open("rb"),
        content_type=evidence.file_type or "application/octet-stream",
        as_attachment=True,
        filename=evidence.original_filename,
    )
    return response


# -----------------------------------------------------------------------------
# 5. SECURE EVIDENCE PREVIEW
# -----------------------------------------------------------------------------

@login_required
def evidence_preview_view(request, evidence_id):
    """
    Serves the evidence file inline for browser preview (supported for PDF and images).
    Enforces object-level authorization.
    """
    user = request.user
    evidence = get_object_or_404(
        Evidence.objects.select_related("activity_record", "activity_record__site"),
        pk=evidence_id,
    )

    if not user_can_download_evidence(user, evidence):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"Evidence:{evidence_id}/preview",
            details=f"Unauthorized preview attempt for evidence #{evidence_id}.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have permission to view this evidence document.")

    if not evidence.file or not evidence.file.storage.exists(evidence.file.name):
        raise Http404("The requested file does not exist on storage.")

    if not evidence.is_previewable:
        # Redirect to attachment download if not inline previewable
        return redirect("core:evidence_download", evidence_id=evidence.id)

    response = FileResponse(
        evidence.file.open("rb"),
        content_type=evidence.file_type or "application/octet-stream",
        as_attachment=False,
        filename=evidence.original_filename,
    )
    return response


# -----------------------------------------------------------------------------
# 6. RETIRE EVIDENCE
# -----------------------------------------------------------------------------

@login_required
@role_required(Role.Code.SITE_MANAGER, Role.Code.MEIL_OPERATOR, Role.Code.ESG_MANAGER)
def evidence_retire_view(request, evidence_id):
    """
    Marks an active evidence document as retired/superseded with a required audit justification.
    """
    user = request.user
    evidence = get_object_or_404(
        Evidence.objects.select_related("activity_record", "activity_record__site"),
        pk=evidence_id,
    )

    if not user_can_retire_evidence(user, evidence):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"Evidence:{evidence_id}/retire",
            details="Unauthorized attempt to retire evidence.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to retire this evidence document.")

    if request.method == "POST":
        form = EvidenceRetireForm(request.POST)
        if form.is_valid():
            retire_evidence_record(
                evidence=evidence,
                user=user,
                reason=form.cleaned_data["reason"],
                request=request,
            )
            messages.success(
                request,
                f"Evidence '{evidence.original_filename}' has been retired and marked superseded."
            )
            return redirect("core:evidence_detail", evidence_id=evidence.id)
    else:
        form = EvidenceRetireForm()

    context = {
        "page_title": "Retire Supporting Evidence",
        "page_subtitle": f"Document: {evidence.original_filename}",
        "active_nav": "evidence",
        "evidence": evidence,
        "form": form,
    }
    return render(request, "evidence/evidence_retire_confirm.html", context)


# -----------------------------------------------------------------------------
# 7. DELETE DRAFT EVIDENCE
# -----------------------------------------------------------------------------

@login_required
@require_POST
def evidence_delete_view(request, record_id, evidence_id):
    """
    Safely deletes a draft evidence document and removes its file from storage.
    Permitted only while the parent ActivityRecord is in DRAFT state.
    """
    user = request.user
    record = get_object_or_404(ActivityRecord, pk=record_id)
    evidence = get_object_or_404(Evidence, pk=evidence_id, activity_record=record)

    if not user_can_delete_evidence(user, evidence):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"Evidence:{evidence_id}/delete",
            details="Unauthorized attempt to delete evidence.",
            success=False,
        )
        raise PermissionDenied("You cannot delete this evidence document. Hard-deletion is allowed only for draft records.")

    filename = evidence.original_filename
    delete_evidence_record(evidence, user, request=request)
    messages.success(request, f"Draft evidence document '{filename}' was deleted successfully.")
    return redirect("core:activity_record_detail", record_id=record.id)
