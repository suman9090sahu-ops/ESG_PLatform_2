"""
Views for ESG Governed Reporting, Enterprise GHG Consolidation, and 'Trace This Number' Lineage.

Fulfills Phase 20 Requirements:
- Enterprise Consolidation & BRSR Reporting Workspace (/reports/)
- Governed Disclosures Table with dynamic Scope 1, Scope 2, Scope 3, Water, and Waste metrics
- 5-Layer 'Trace This Number' Deep Inspection Workspace (/reports/trace/<id>/)
- Trace Selector Catalog (/auditor/trace/ & /reports/trace/)
- Auditor Assurance Mode (strictly read-only enforcement)
- Anti-IDOR Object-Level Access Enforcement & CSRF Protection
"""

import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.core.auth_services import log_auth_event, role_required
from apps.core.data_entry_services import user_can_access_activity_record
from apps.core.models import (
    ActivityRecord,
    AuthAuditLog,
    RecordStatus,
    Role,
    ScopeClassification,
)
from apps.core.reporting_services import (
    get_consolidated_report,
    get_trace_lineage_context,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. ENTERPRISE CONSOLIDATION & GOVERNED REPORTS VIEW
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.ESG_MANAGER,
    Role.Code.AUDITOR,
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.MEIL_OPERATOR,
)
def reports_overview_view(request):
    """
    Renders the central Enterprise ESG Consolidation and Governed Reports Workspace.
    Aggregates verified operational activity data across subsidiaries, projects, and sites.
    Provides interactive filters by reporting period, subsidiary division, and emission scope.
    """
    user = request.user
    period_param = request.GET.get("period")
    sub_param = request.GET.get("subsidiary")
    scope_param = request.GET.get("scope")

    period_id = int(period_param) if period_param and period_param.isdigit() else None
    subsidiary_id = int(sub_param) if sub_param and sub_param.isdigit() else None

    # Derive consolidated report metrics
    report = get_consolidated_report(
        user=user,
        period_id=period_id,
        subsidiary_id=subsidiary_id,
        scope_filter=scope_param,
    )

    is_auditor = user.has_role(Role.Code.AUDITOR) and not user.has_role(Role.Code.MEIL_OPERATOR)

    # Pagination for disclosures list
    disclosures = report["disclosures"]
    paginator = Paginator(disclosures, 15)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "page_title": "Enterprise ESG Consolidation & Governed Reports",
        "page_subtitle": "Regulatory Scope 1, 2, 3 GHG Accounting, Resource Consumption & BRSR Verification",
        "active_nav": "governed_reports" if is_auditor else "consolidation",
        "is_auditor": is_auditor,
        "report": report,
        "current_period": report["current_period"],
        "accessible_periods": report["accessible_periods"],
        "accessible_subsidiaries": report["accessible_subsidiaries"],
        "selected_period_id": period_id or (report["current_period"].id if report["current_period"] else None),
        "selected_subsidiary_id": subsidiary_id,
        "scope_filter": scope_param or "",
        "page_obj": page_obj,
        "disclosures": page_obj.object_list,
        "total_disclosures_count": len(disclosures),
        "scope_choices": [
            ("SCOPE_1", "Scope 1 - Direct Combustion"),
            ("SCOPE_2", "Scope 2 - Purchased Electricity"),
            ("SCOPE_3", "Scope 3 - Value Chain"),
            ("WATER", "Water Resources"),
            ("WASTE", "Waste Management"),
        ],
    }
    return render(request, "reports/reports_overview.html", context)


# -----------------------------------------------------------------------------
# 2. 5-LAYER "TRACE THIS NUMBER" LINEAGE DETAIL VIEW
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.AUDITOR,
    Role.Code.ESG_MANAGER,
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.SITE_MANAGER,
    Role.Code.MEIL_OPERATOR,
)
def trace_number_view(request, record_id):
    """
    Renders the definitive 5-layer 'Trace This Number' regulatory audit lineage view.
    Follows an ESG disclosure value back through:
    Report -> Consolidated Data -> Verified Submission -> Site Data -> Audit Evidence.
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

    # Object-level authorization check
    if not user_can_access_activity_record(user, record):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"TraceLineage:Record:{record_id}",
            details=f"Unauthorized lineage trace attempt for ActivityRecord #{record_id} by {user.username}.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have authorization to trace this operational record.")

    lineage = get_trace_lineage_context(record_id=record.id, user=user)

    is_auditor = user.has_role(Role.Code.AUDITOR) and not user.has_role(Role.Code.MEIL_OPERATOR)

    context = {
        "page_title": f"Trace Lineage: {record.activity.name}",
        "page_subtitle": f"Record #{record.id} @ {record.site.name} — Full 5-Layer Regulatory Lineage",
        "active_nav": "calculation_lineage" if is_auditor else "consolidation",
        "is_auditor": is_auditor,
        "record": record,
        **lineage,
    }
    return render(request, "reports/trace_detail.html", context)


# -----------------------------------------------------------------------------
# 3. TRACE NUMBER SELECTOR / CATALOG VIEW
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.AUDITOR,
    Role.Code.ESG_MANAGER,
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.MEIL_OPERATOR,
)
def trace_selector_view(request):
    """
    Renders the interactive Trace Selector allowing auditors and managers to pick
    any verified ESG telemetry value across the enterprise and inspect its lineage.
    """
    user = request.user
    report = get_consolidated_report(user=user)

    disclosures = report["disclosures"]
    query = request.GET.get("q", "").strip().lower()
    if query:
        disclosures = [
            d for d in disclosures
            if query in d["activity_name"].lower()
            or query in d["site"].name.lower()
            or query in d["subsidiary"].name.lower()
            or query in d["activity_code"].lower()
        ]

    paginator = Paginator(disclosures, 15)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    is_auditor = user.has_role(Role.Code.AUDITOR) and not user.has_role(Role.Code.MEIL_OPERATOR)

    context = {
        "page_title": "Trace This Number — ESG Lineage Directory",
        "page_subtitle": "Select Any Governed ESG Telemetry Reading to Inspect End-to-End Regulatory Lineage",
        "active_nav": "calculation_lineage" if is_auditor else "consolidation",
        "is_auditor": is_auditor,
        "page_obj": page_obj,
        "disclosures": page_obj.object_list,
        "total_count": len(disclosures),
        "search_query": query,
        "current_period": report["current_period"],
    }
    return render(request, "reports/trace_selector.html", context)
