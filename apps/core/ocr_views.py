"""
OCR Views for MEIL ESG CONTROL TOWER.

Fulfills Phase 11 Requirements:
- POST trigger view for OCR processing & document extraction (evidence_ocr_process_view).
- Dedicated audit inspection view for specific historical OCR runs (ocr_run_detail_view).
- JSON status & telemetry API endpoint (evidence_ocr_status_api).
- Retry view for re-evaluating documents (ocr_run_retry_view).
- Strict RBAC enforcement & Anti-IDOR protection across all routes.
- Dual-mode responses supporting both reactive AJAX and standard HTTP redirection.
"""

import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.core.auth_services import log_auth_event, role_required
from apps.core.evidence_services import user_can_access_evidence
from apps.core.models import (
    AuthAuditLog,
    Evidence,
    EvidenceStatus,
    OCRRun,
    OCRStatus,
    Role,
)
from apps.core.ocr_services import (
    execute_ocr_run,
    user_can_process_ocr,
    user_can_view_ocr,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. OCR PROCESSING TRIGGER VIEW (POST-ONLY)
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.SITE_MANAGER,
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.ESG_MANAGER,
    Role.Code.MEIL_OPERATOR,
    Role.Code.AUDITOR,
)
@require_POST
def evidence_ocr_process_view(request, evidence_id: int):
    """
    POST-only endpoint initiating optical character recognition on an evidence document.
    Enforces server-side authorization and denies Auditor (strictly read-only role).
    """
    evidence = get_object_or_404(Evidence, id=evidence_id)

    # 1. Scope / Object-level check
    if not user_can_access_evidence(request.user, evidence):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Evidence:{evidence_id}/ocr/process",
            details="IDOR Defense: Unauthorized attempt to initiate OCR on foreign evidence.",
            success=False,
        )
        raise PermissionDenied("You do not have authorization to access this evidence document.")

    # 2. Role permission check (prohibits Auditor mutation)
    if not user_can_process_ocr(request.user, evidence):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Evidence:{evidence_id}/ocr/process",
            details="Permission Denied: Auditor attempted to trigger OCR mutation.",
            success=False,
        )
        raise PermissionDenied("Auditors are restricted to read-only inspection and cannot execute OCR processing.")

    # 3. Retired evidence check
    if evidence.status == EvidenceStatus.RETIRED:
        messages.warning(
            request,
            "Document is marked as RETIRED. OCR processing should be run on active documents."
        )

    # 4. Execute OCR processing run
    try:
        ocr_run = execute_ocr_run(
            evidence=evidence,
            user=request.user,
            request=request,
        )
    except Exception as exc:
        logger.exception("Unexpected error executing OCR for Evidence %s: %s", evidence_id, exc)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({
                "success": False,
                "status": "FAILED",
                "error": str(exc),
            }, status=400)
        messages.error(request, f"OCR processing failed: {str(exc)}")
        return redirect("core:evidence_detail", evidence_id=evidence.id)

    # 5. Dual-mode response
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("accept", "")
    if is_ajax:
        return JsonResponse({
            "success": ocr_run.is_completed,
            "status": ocr_run.status,
            "run_id": ocr_run.id,
            "run_number": ocr_run.run_number,
            "engine": ocr_run.engine,
            "confidence": float(ocr_run.confidence) if ocr_run.confidence else None,
            "page_count": ocr_run.page_count,
            "fields_count": ocr_run.fields_count,
            "execution_duration_ms": ocr_run.execution_duration_ms,
            "comparison": ocr_run.comparison_summary,
            "error_message": ocr_run.error_message,
        })

    if ocr_run.is_completed:
        messages.success(
            request,
            f"OCR processing completed (Run #{ocr_run.run_number}). "
            f"Extracted {ocr_run.fields_count} structured fields with {ocr_run.confidence or 0}% confidence."
        )
    else:
        messages.error(
            request,
            f"OCR extraction failed: {ocr_run.error_message}"
        )

    # Check redirect parameter
    next_url = request.POST.get("next")
    if next_url and next_url.startswith("/"):
        return redirect(next_url)

    return redirect("core:evidence_detail", evidence_id=evidence.id)


# -----------------------------------------------------------------------------
# 2. HISTORICAL OCR RUN AUDIT DETAIL VIEW
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.SITE_MANAGER,
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.ESG_MANAGER,
    Role.Code.MEIL_OPERATOR,
    Role.Code.AUDITOR,
)
def ocr_run_detail_view(request, evidence_id: int, run_id: int):
    """
    Granular audit report for a specific OCR execution run.
    Displays immutable run telemetry, extracted text, structured fields,
    page breakdowns, and comparison against parent activity record.
    """
    evidence = get_object_or_404(Evidence, id=evidence_id)

    # Anti-IDOR Object Scoping
    if not user_can_view_ocr(request.user, evidence):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"Evidence:{evidence_id}/ocr/runs/{run_id}",
            details="IDOR Defense: Unauthorized attempt to view OCR run audit ledger.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to view OCR audit records for this evidence.")

    ocr_run = get_object_or_404(OCRRun, id=run_id, evidence=evidence)

    can_process = user_can_process_ocr(request.user, evidence)
    fields = ocr_run.fields.all()
    comparison = ocr_run.comparison_summary
    historical_runs = evidence.ocr_runs.order_by("-run_number")

    context = {
        "page_title": f"OCR Run #{ocr_run.run_number} Audit Ledger",
        "page_subtitle": f"Document Intelligence & Entity Extraction for Evidence #EV-{evidence.id:05d}",
        "active_nav": "evidence",
        "evidence": evidence,
        "ocr_run": ocr_run,
        "fields": fields,
        "comparison": comparison,
        "historical_runs": historical_runs,
        "can_process": can_process,
    }
    return render(request, "evidence/ocr_run_detail.html", context)


# -----------------------------------------------------------------------------
# 3. TELEMETRY STATUS API (GET)
# -----------------------------------------------------------------------------

@login_required
@require_GET
def evidence_ocr_status_api(request, evidence_id: int):
    """
    GET JSON endpoint returning current OCR processing status and metadata.
    """
    evidence = get_object_or_404(Evidence, id=evidence_id)

    if not user_can_view_ocr(request.user, evidence):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    latest_run = evidence.latest_ocr_run
    if not latest_run:
        return JsonResponse({
            "has_run": False,
            "status": "NOT_PROCESSED",
            "evidence_id": evidence.id,
            "is_supported": evidence.is_ocr_supported,
        })

    return JsonResponse({
        "has_run": True,
        "evidence_id": evidence.id,
        "run_id": latest_run.id,
        "run_number": latest_run.run_number,
        "status": latest_run.status,
        "engine": latest_run.engine,
        "confidence": float(latest_run.confidence) if latest_run.confidence else None,
        "page_count": latest_run.page_count,
        "fields_count": latest_run.fields_count,
        "is_latest": latest_run.is_latest,
        "completed_at": latest_run.completed_at.isoformat() if latest_run.completed_at else None,
        "comparison": latest_run.comparison_summary,
        "error_message": latest_run.error_message,
    })


# -----------------------------------------------------------------------------
# 4. OCR RETRY HANDLER (POST-ONLY)
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.SITE_MANAGER,
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.ESG_MANAGER,
    Role.Code.MEIL_OPERATOR,
)
@require_POST
def ocr_run_retry_view(request, evidence_id: int, run_id: int):
    """
    POST-only action re-running optical character recognition for an evidence document.
    Creates a new OCRRun with an incremented run_number while preserving prior history.
    """
    evidence = get_object_or_404(Evidence, id=evidence_id)

    if not user_can_process_ocr(request.user, evidence):
        raise PermissionDenied("You do not have permission to retry OCR processing for this evidence.")

    return evidence_ocr_process_view(request, evidence_id=evidence.id)
