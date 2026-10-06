"""
Reporting Period Views for MEIL ESG CONTROL TOWER.

Fulfills Phase 04 Requirements:
- Scoped Period Listing with Status & Organizational Filtering
- Period Detail View with Temporal Governance Lifecycle Timeline & Lineage Hooks
- Scoped Create and Edit Forms with Server-Side Authorization
- Controlled Status Lifecycle Transition Endpoint with Auditing
- Strict IDOR Protection & Object-Level Access Enforcement
"""

import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.core.auth_services import log_auth_event
from apps.core.models import (
    AuthAuditLog,
    Company,
    PeriodStatus,
    ReportingPeriod,
    Role,
)
from apps.core.period_forms import ReportingPeriodForm, ReportingPeriodStatusForm
from apps.core.period_services import (
    get_accessible_reporting_periods,
    is_period_open,
    transition_period_status,
    user_can_access_reporting_period,
    user_can_manage_period_lifecycle,
    user_can_manage_reporting_period,
)
from apps.core.scope_services import get_accessible_companies

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. REPORTING PERIOD LIST VIEW
# -----------------------------------------------------------------------------

@login_required
def period_list_view(request):
    """
    List reporting periods accessible to the authenticated user.
    Includes status badges, filters, search, and lifecycle summary metrics.
    """
    user = request.user
    periods = get_accessible_reporting_periods(user)

    search_q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    company_filter = request.GET.get("company", "").strip()

    if search_q:
        periods = periods.filter(
            Q(name__icontains=search_q)
            | Q(code__icontains=search_q)
            | Q(fiscal_year__icontains=search_q)
            | Q(company__name__icontains=search_q)
        )

    if status_filter and status_filter in PeriodStatus.values:
        periods = periods.filter(status=status_filter)

    if company_filter and company_filter.isdigit():
        periods = periods.filter(company_id=int(company_filter))

    # Metric counts (from unscoped or user-accessible base)
    accessible_base = get_accessible_reporting_periods(user)
    stats = {
        "total": accessible_base.count(),
        "open": accessible_base.filter(status=PeriodStatus.OPEN).count(),
        "draft": accessible_base.filter(status=PeriodStatus.DRAFT).count(),
        "closed": accessible_base.filter(status=PeriodStatus.CLOSED).count(),
        "locked": accessible_base.filter(status=PeriodStatus.LOCKED).count(),
        "finalized": accessible_base.filter(status=PeriodStatus.FINALIZED).count(),
    }

    accessible_companies = get_accessible_companies(user)
    can_create = user_can_manage_reporting_period(user)

    context = {
        "page_title": "Reporting Periods & Temporal Governance",
        "page_subtitle": "Regulatory Reporting Cycles, Temporal Boundaries & Lifecycle Control",
        "active_nav": "reporting_periods",
        "periods": periods,
        "stats": stats,
        "companies": accessible_companies,
        "can_create": can_create,
        "search_q": search_q,
        "status_filter": status_filter,
        "company_filter": company_filter,
        "period_status_choices": PeriodStatus.choices,
    }
    return render(request, "reporting_periods/list.html", context)


# -----------------------------------------------------------------------------
# 2. REPORTING PERIOD DETAIL VIEW
# -----------------------------------------------------------------------------

@login_required
def period_detail_view(request, period_id):
    """
    Detailed profile for a Reporting Period.
    Shows temporal boundary, organization scope, lifecycle timeline,
    and action controls for authorized users.
    """
    period = get_object_or_404(ReportingPeriod.objects.select_related("company", "subsidiary", "created_by", "updated_by"), id=period_id)

    if not user_can_access_reporting_period(request.user, period):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=request.user,
            resource_accessed=f"ReportingPeriod:{period.id} ({period.code})",
            details="IDOR violation attempt on Reporting Period detail.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have permission to access this reporting period.")

    can_manage = user_can_manage_reporting_period(request.user, period)
    can_transition = user_can_manage_period_lifecycle(request.user, period)
    allowed_transitions = period.get_allowed_transitions() if can_transition else []

    status_form = (
        ReportingPeriodStatusForm(period=period)
        if (can_transition and allowed_transitions)
        else None
    )

    # Fetch recent audit logs for this period
    audit_logs = AuthAuditLog.objects.filter(
        resource_accessed__startswith=f"ReportingPeriod:{period.id}"
    ).order_by("-created_at")[:10]

    context = {
        "page_title": f"Reporting Period: {period.code}",
        "page_subtitle": f"{period.fiscal_year} — {period.name}",
        "active_nav": "reporting_periods",
        "period": period,
        "can_manage": can_manage,
        "can_transition": can_transition,
        "allowed_transitions": allowed_transitions,
        "status_form": status_form,
        "audit_logs": audit_logs,
        "allows_edit": period.allows_metadata_edit and can_manage,
    }
    return render(request, "reporting_periods/detail.html", context)


# -----------------------------------------------------------------------------
# 3. REPORTING PERIOD CREATE VIEW
# -----------------------------------------------------------------------------

@login_required
def period_create_view(request):
    """
    Form view for creating a new Reporting Period.
    Restricted to MEIL_OPERATOR, ESG_MANAGER, and Superusers.
    Auditors, Site Managers, and Subsidiary Managers are denied.
    """
    user = request.user
    if not user_can_manage_reporting_period(user):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed="/reporting-periods/create/",
            details="Unauthorized attempt to create a reporting period.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to create reporting periods.")

    if request.method == "POST":
        form = ReportingPeriodForm(request.POST, user=user)
        if form.is_valid():
            period = form.save(commit=False)
            period.created_by = user
            period.updated_by = user
            period.save()

            log_auth_event(
                AuthAuditLog.EventType.PERIOD_CREATED,
                request=request,
                user=user,
                resource_accessed=f"ReportingPeriod:{period.id} ({period.code})",
                details=f"Reporting period '{period.name}' ({period.code}) created with status '{period.status}'.",
                success=True,
            )

            messages.success(request, f"Reporting Period '{period.name}' ({period.code}) was created successfully.")
            return redirect("core:period_detail", period_id=period.id)
    else:
        form = ReportingPeriodForm(user=user)

    context = {
        "page_title": "Create Reporting Period",
        "page_subtitle": "Define Temporal Boundary, Fiscal Year & Organizational Scope",
        "active_nav": "reporting_periods",
        "form": form,
        "is_create": True,
    }
    return render(request, "reporting_periods/form.html", context)


# -----------------------------------------------------------------------------
# 4. REPORTING PERIOD EDIT VIEW
# -----------------------------------------------------------------------------

@login_required
def period_edit_view(request, period_id):
    """
    Form view for updating an existing Reporting Period.
    Only permitted for periods in DRAFT, OPEN, or CLOSED status.
    LOCKED and FINALIZED periods prohibit modification.
    """
    period = get_object_or_404(ReportingPeriod, id=period_id)
    user = request.user

    if not user_can_manage_reporting_period(user, period):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"ReportingPeriod:{period.id}/edit/",
            details="Unauthorized attempt to edit reporting period.",
            success=False,
        )
        raise PermissionDenied("You do not have permission to modify this reporting period.")

    if not period.allows_metadata_edit:
        messages.error(
            request,
            f"Reporting Period '{period.code}' is {period.get_status_display().upper()} and cannot be edited. "
            f"Historical regulatory records are locked against modification.",
        )
        return redirect("core:period_detail", period_id=period.id)

    if request.method == "POST":
        form = ReportingPeriodForm(request.POST, instance=period, user=user)
        if form.is_valid():
            period = form.save(commit=False)
            period.updated_by = user
            period.save()

            log_auth_event(
                AuthAuditLog.EventType.PERIOD_UPDATED,
                request=request,
                user=user,
                resource_accessed=f"ReportingPeriod:{period.id} ({period.code})",
                details=f"Reporting period '{period.name}' ({period.code}) configuration updated.",
                success=True,
            )

            messages.success(request, f"Reporting Period '{period.code}' updated successfully.")
            return redirect("core:period_detail", period_id=period.id)
    else:
        form = ReportingPeriodForm(instance=period, user=user)

    context = {
        "page_title": f"Edit Reporting Period: {period.code}",
        "page_subtitle": f"Update parameters for {period.name}",
        "active_nav": "reporting_periods",
        "form": form,
        "period": period,
        "is_create": False,
    }
    return render(request, "reporting_periods/form.html", context)


# -----------------------------------------------------------------------------
# 5. STATUS LIFECYCLE TRANSITION VIEW
# -----------------------------------------------------------------------------

@login_required
@require_http_methods(["POST"])
def period_status_transition_view(request, period_id):
    """
    POST-only endpoint for executing controlled lifecycle status transitions.
    Protected with CSRF, state-machine validation, and audit event recording.
    """
    period = get_object_or_404(ReportingPeriod, id=period_id)
    user = request.user

    target_status = request.POST.get("target_status", "").strip()
    reason = request.POST.get("reason", "").strip()

    if not user_can_manage_period_lifecycle(user, period):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"ReportingPeriod:{period.id}/status/",
            details=f"Unauthorized lifecycle transition attempt to '{target_status}'.",
            success=False,
        )
        raise PermissionDenied("You do not have authority to alter the lifecycle status of this reporting period.")

    try:
        transition_period_status(
            period=period,
            target_status=target_status,
            user=user,
            reason=reason,
            request=request,
        )
        messages.success(
            request,
            f"Reporting Period '{period.code}' status successfully updated to {period.get_status_display()}.",
        )
    except (ValidationError, ValueError) as err:
        error_msg = getattr(err, "message", str(err))
        messages.error(request, f"Status Transition Failed: {error_msg}")

    return redirect("core:period_detail", period_id=period.id)
