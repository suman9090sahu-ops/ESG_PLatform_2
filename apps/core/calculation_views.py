"""
Views for ESG Calculation Engine, Calculation Detail Lineage, and Emission Factor Administration.

Fulfills Phase 24 Requirements:
- Calculation Detail View (/calculations/<id>/ and /calculations/record/<id>/)
- Calculation Quality Desk / Health Monitor (/calculations/quality/)
- Emission Factor Directory (/emission-factors/)
- Emission Factor Create & Edit (/emission-factors/create/ and /emission-factors/<id>/edit/)
- Strict server-side RBAC enforcement:
    - Auditor is strictly READ-ONLY (mutation endpoints return HTTP 403 Forbidden)
    - Site Manager is blocked from modifying emission factors (HTTP 403 Forbidden)
    - ESG Manager and MEIL Operator can administer emission factors
- Anti-IDOR object-level authorization guards
"""

import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.auth_services import log_auth_event, role_required
from apps.core.calculation_forms import EmissionFactorForm
from apps.core.calculation_services import (
    calculate_activity_record,
    recalculate_record,
    select_emission_factor,
)
from apps.core.data_entry_services import user_can_access_activity_record
from apps.core.models import (
    ActivityMaster,
    ActivityRecord,
    AuthAuditLog,
    CalculationResult,
    CalculationStatus,
    EmissionFactor,
    EmissionFactorStatus,
    RecordStatus,
    Role,
    ScopeClassification,
)
from apps.core.period_services import get_accessible_reporting_periods
from apps.core.scope_services import get_accessible_sites, get_accessible_subsidiaries

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. CALCULATION DETAIL VIEW
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.SITE_MANAGER,
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.ESG_MANAGER,
    Role.Code.AUDITOR,
    Role.Code.MEIL_OPERATOR,
)
def calculation_detail_view(request, calculation_id: int):
    """
    Renders the definitive Calculation Detail View showing the full step-by-step
    transformation from Raw Activity Data to Normalized Quantity to Emission Factor to Final Metric.
    """
    user = request.user
    calc = get_object_or_404(
        CalculationResult.objects.select_related(
            "activity_record",
            "activity_record__site",
            "activity_record__site__project",
            "activity_record__site__project__subsidiary",
            "activity_record__site__project__subsidiary__company",
            "activity_record__reporting_period",
            "activity",
            "activity__category",
            "raw_unit",
            "normalized_unit",
            "emission_factor",
            "emission_factor__input_unit",
        ),
        pk=calculation_id,
    )

    record = calc.activity_record

    # Object-level authorization check
    if not user_can_access_activity_record(user, record):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"CalculationResult:{calculation_id}",
            details=f"Unauthorized calculation detail access attempt by {user.username}.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have permission to view calculations for this record.")

    is_auditor = user.has_role(Role.Code.AUDITOR) and not user.has_role(Role.Code.MEIL_OPERATOR)
    can_recalculate = any(user.has_role(r) for r in [Role.Code.ESG_MANAGER, Role.Code.SUBSIDIARY_MANAGER, Role.Code.MEIL_OPERATOR]) and not is_auditor

    # Historical runs for this record
    all_runs = record.calculation_results.select_related("emission_factor").order_by("-calculated_at")

    context = {
        "page_title": f"Calculation Lineage: {record.activity.name}",
        "page_subtitle": f"Record #{record.id} @ {record.site.name} — Deterministic ESG Calculation Audit Ledger",
        "active_nav": "calculation_lineage" if is_auditor else "consolidation",
        "is_auditor": is_auditor,
        "can_recalculate": can_recalculate,
        "calc": calc,
        "record": record,
        "all_runs": all_runs,
        "trace_url": reverse("core:trace_number_detail", kwargs={"record_id": record.id}),
    }
    return render(request, "calculations/calculation_detail.html", context)


@login_required
def calculation_record_detail_view(request, record_id: int):
    """
    Convenience route redirecting to the latest CalculationResult for a given ActivityRecord.
    If no calculation exists, calculates on-the-fly first.
    """
    user = request.user
    record = get_object_or_404(
        ActivityRecord.objects.select_related(
            "activity", "unit", "site", "site__project", "site__project__subsidiary", "reporting_period"
        ),
        pk=record_id,
    )

    if not user_can_access_activity_record(user, record):
        raise PermissionDenied("Access Denied.")

    calc = record.latest_calculation
    if not calc:
        calc = calculate_activity_record(record, user=user)

    return redirect("core:calculation_detail", calculation_id=calc.id)


# -----------------------------------------------------------------------------
# 2. CALCULATION QUALITY DESK / HEALTH DASHBOARD
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.ESG_MANAGER,
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.AUDITOR,
    Role.Code.MEIL_OPERATOR,
)
def calculation_desk_view(request):
    """
    Renders the Calculation Quality Desk displaying platform-wide calculation health,
    missing-factor flags, unit mismatches, and reporting-readiness metrics.
    """
    user = request.user
    is_auditor = user.has_role(Role.Code.AUDITOR) and not user.has_role(Role.Code.MEIL_OPERATOR)

    accessible_sites = get_accessible_sites(user)
    accessible_periods = get_accessible_reporting_periods(user).order_by("-start_date")

    status_filter = request.GET.get("status", "").strip().upper()
    scope_filter = request.GET.get("scope", "").strip().upper()
    period_param = request.GET.get("period")
    period_id = int(period_param) if period_param and period_param.isdigit() else None

    calcs_qs = CalculationResult.objects.filter(
        site__in=accessible_sites,
        is_latest=True,
    ).select_related(
        "activity_record",
        "activity_record__site",
        "activity_record__site__project",
        "activity_record__site__project__subsidiary",
        "activity_record__reporting_period",
        "activity",
        "raw_unit",
        "normalized_unit",
        "emission_factor",
    ).order_by("-calculated_at")

    if period_id:
        calcs_qs = calcs_qs.filter(reporting_period_id=period_id)

    # Health summary metrics
    total_evaluated = calcs_qs.count()
    calculated_count = calcs_qs.filter(status=CalculationStatus.CALCULATED).count()
    requires_config_count = calcs_qs.filter(status=CalculationStatus.REQUIRES_CONFIGURATION).count()
    failed_count = calcs_qs.filter(status=CalculationStatus.FAILED).count()
    verified_ready_count = calcs_qs.filter(
        status=CalculationStatus.CALCULATED,
        activity_record__status__in=[RecordStatus.VERIFIED, RecordStatus.APPROVED],
    ).count()

    # Apply filters to list
    if status_filter:
        calcs_qs = calcs_qs.filter(status=status_filter)
    if scope_filter:
        calcs_qs = calcs_qs.filter(scope=scope_filter)

    paginator = Paginator(calcs_qs, 20)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "page_title": "Calculation Quality & Factor Audit Desk",
        "page_subtitle": "Real-time Verification of Unit Normalization, Emission Factor Coverage & GHG Lineage",
        "active_nav": "calculation_lineage" if is_auditor else "calculation_desk",
        "is_auditor": is_auditor,
        "page_obj": page_obj,
        "calculations": page_obj.object_list,
        "total_evaluated": total_evaluated,
        "calculated_count": calculated_count,
        "requires_config_count": requires_config_count,
        "failed_count": failed_count,
        "verified_ready_count": verified_ready_count,
        "status_filter": status_filter,
        "scope_filter": scope_filter,
        "accessible_periods": accessible_periods,
        "selected_period_id": period_id,
        "status_choices": CalculationStatus.choices,
        "scope_choices": ScopeClassification.choices,
    }
    return render(request, "calculations/calculation_desk.html", context)


# -----------------------------------------------------------------------------
# 3. RECALCULATION ACTION VIEW
# -----------------------------------------------------------------------------

@login_required
@require_POST
def recalculate_record_action_view(request, record_id: int):
    """
    Triggers explicit recalculation of an ActivityRecord.
    Protected against Auditor mutation (HTTP 403).
    """
    user = request.user
    if user.has_role(Role.Code.AUDITOR) and not user.has_role(Role.Code.MEIL_OPERATOR):
        raise PermissionDenied("Auditor mode is strictly read-only. Recalculation mutation denied.")

    if not any(user.has_role(r) for r in [Role.Code.ESG_MANAGER, Role.Code.SUBSIDIARY_MANAGER, Role.Code.MEIL_OPERATOR]):
        raise PermissionDenied("Site Managers and unauthorized roles are not permitted to trigger recalculation.")

    record = get_object_or_404(ActivityRecord, pk=record_id)
    if not user_can_access_activity_record(user, record):
        raise PermissionDenied("Access Denied.")

    calc = recalculate_record(record.id, user=user)

    if calc.status == CalculationStatus.CALCULATED:
        messages.success(
            request,
            f"Recalculation complete for Record #{record.id}: {calc.calculated_value} {calc.result_unit}.",
        )
    elif calc.status == CalculationStatus.REQUIRES_CONFIGURATION:
        messages.warning(
            request,
            f"Recalculation flagged: {calc.error_message}",
        )
    else:
        messages.error(
            request,
            f"Recalculation failed: {calc.error_message}",
        )

    next_url = request.POST.get("next") or reverse("core:calculation_detail", kwargs={"calculation_id": calc.id})
    return redirect(next_url)


# -----------------------------------------------------------------------------
# 4. EMISSION FACTOR ADMINISTRATION VIEWS
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.ESG_MANAGER,
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.AUDITOR,
    Role.Code.MEIL_OPERATOR,
)
def emission_factor_list_view(request):
    """
    Renders the Regulatory Emission Factor Directory.
    Shows factor values, units, sources, baseline vintage years, and versioning.
    """
    user = request.user
    is_auditor = user.has_role(Role.Code.AUDITOR) and not user.has_role(Role.Code.MEIL_OPERATOR)
    can_manage = any(user.has_role(r) for r in [Role.Code.ESG_MANAGER, Role.Code.MEIL_OPERATOR])

    scope_filter = request.GET.get("scope", "").strip().upper()
    status_filter = request.GET.get("status", "").strip().upper()
    search_query = request.GET.get("q", "").strip()

    factors_qs = EmissionFactor.objects.select_related("activity", "input_unit", "reporting_period").order_by(
        "scope", "activity_code", "-effective_year", "-version"
    )

    if scope_filter:
        factors_qs = factors_qs.filter(scope=scope_filter)
    if status_filter:
        factors_qs = factors_qs.filter(status=status_filter)
    if search_query:
        factors_qs = factors_qs.filter(
            models.Q(name__icontains=search_query)
            | models.Q(code__icontains=search_query)
            | models.Q(activity_code__icontains=search_query)
            | models.Q(source__icontains=search_query)
        )

    paginator = Paginator(factors_qs, 15)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "page_title": "Regulatory Emission Factor Directory",
        "page_subtitle": "IPCC, Central Electricity Authority & SEBI BRSR Baseline Coefficients",
        "active_nav": "calculation_lineage" if is_auditor else "emission_factors",
        "is_auditor": is_auditor,
        "can_manage": can_manage,
        "page_obj": page_obj,
        "factors": page_obj.object_list,
        "total_count": factors_qs.count(),
        "search_query": search_query,
        "scope_filter": scope_filter,
        "status_filter": status_filter,
        "scope_choices": ScopeClassification.choices,
        "status_choices": EmissionFactorStatus.choices,
    }
    return render(request, "factors/factor_list.html", context)


@login_required
@role_required(
    Role.Code.ESG_MANAGER,
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.AUDITOR,
    Role.Code.MEIL_OPERATOR,
)
def emission_factor_detail_view(request, factor_id: int):
    """
    Renders detailed specifications for a specific EmissionFactor.
    """
    user = request.user
    factor = get_object_or_404(
        EmissionFactor.objects.select_related("activity", "input_unit", "reporting_period", "created_by", "updated_by"),
        pk=factor_id,
    )

    is_auditor = user.has_role(Role.Code.AUDITOR) and not user.has_role(Role.Code.MEIL_OPERATOR)
    can_manage = any(user.has_role(r) for r in [Role.Code.ESG_MANAGER, Role.Code.MEIL_OPERATOR])

    # Active calculations referencing this factor
    recent_calcs = factor.calculation_results.filter(is_latest=True).select_related(
        "activity_record", "site", "reporting_period"
    )[:10]

    context = {
        "page_title": f"Emission Factor: {factor.name}",
        "page_subtitle": f"{factor.code} ({factor.factor_value} {factor.factor_unit}) — Regulatory Standard Specification",
        "active_nav": "calculation_lineage" if is_auditor else "emission_factors",
        "is_auditor": is_auditor,
        "can_manage": can_manage,
        "factor": factor,
        "recent_calcs": recent_calcs,
    }
    return render(request, "factors/factor_detail.html", context)


@login_required
@role_required(Role.Code.ESG_MANAGER, Role.Code.MEIL_OPERATOR)
def emission_factor_create_view(request):
    """
    Creates a new regulatory emission factor.
    Restricted strictly to ESG_MANAGER and MEIL_OPERATOR.
    Auditors and Site Managers are denied with HTTP 403 Forbidden.
    """
    user = request.user
    if request.method == "POST":
        form = EmissionFactorForm(request.POST)
        if form.is_valid():
            factor = form.save(commit=False)
            factor.created_by = user
            factor.updated_by = user
            factor.save()

            log_auth_event(
                AuthAuditLog.EventType.EMISSION_FACTOR_CREATED,
                request=request,
                user=user,
                resource_accessed=f"EmissionFactor:{factor.id}:{factor.code}",
                details=f"Emission Factor '{factor.name}' ({factor.code}) created by {user.username}.",
                success=True,
            )

            messages.success(request, f"Emission Factor '{factor.name}' ({factor.code}) created successfully.")
            return redirect("core:emission_factor_detail", factor_id=factor.id)
    else:
        form = EmissionFactorForm()

    context = {
        "page_title": "Configure Regulatory Emission Factor",
        "page_subtitle": "Define Authoritative GHG Protocol or Grid Emission Baseline Parameter",
        "active_nav": "emission_factors",
        "form": form,
        "is_create": True,
    }
    return render(request, "factors/factor_form.html", context)


@login_required
@role_required(Role.Code.ESG_MANAGER, Role.Code.MEIL_OPERATOR)
def emission_factor_edit_view(request, factor_id: int):
    """
    Edits an existing emission factor.
    Restricted strictly to ESG_MANAGER and MEIL_OPERATOR.
    Factor Change Safety: Historical CalculationResult snapshots remain untouched.
    """
    user = request.user
    factor = get_object_or_404(EmissionFactor, pk=factor_id)

    if request.method == "POST":
        form = EmissionFactorForm(request.POST, instance=factor)
        if form.is_valid():
            factor = form.save(commit=False)
            factor.updated_by = user
            factor.save()

            log_auth_event(
                AuthAuditLog.EventType.EMISSION_FACTOR_UPDATED,
                request=request,
                user=user,
                resource_accessed=f"EmissionFactor:{factor.id}:{factor.code}",
                details=f"Emission Factor '{factor.name}' ({factor.code}) updated by {user.username}.",
                success=True,
            )

            messages.success(request, f"Emission Factor '{factor.name}' updated successfully.")
            return redirect("core:emission_factor_detail", factor_id=factor.id)
    else:
        form = EmissionFactorForm(instance=factor)

    context = {
        "page_title": f"Edit Emission Factor: {factor.code}",
        "page_subtitle": f"Update Parameters for {factor.name} — Historical Calculations Preserved",
        "active_nav": "emission_factors",
        "form": form,
        "factor": factor,
        "is_create": False,
    }
    return render(request, "factors/factor_form.html", context)
