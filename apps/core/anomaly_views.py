"""
Views for ESG Anomaly Detection Engine and Review Workspace in apps.core.

Fulfills Phase 15 Requirements:
- Scoped Queryset Access & Object-Level Authorization (Zero client trust, anti-IDOR)
- Dedicated Anomaly Desk view with real metrics and multidimensional filtering
- Deep Anomaly Detail view rendering observed vs baseline, variance %, and regulatory audit context
- Governed Review Actions (Acknowledge, Explain, Resolve, Dismiss) with atomic transitions
- On-Demand Anomaly Detection trigger endpoints
"""

import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.anomaly_forms import AnomalyFilterForm, AnomalyReviewActionForm
from apps.core.anomaly_services import (
    detect_anomalies_for_record,
    execute_anomaly_review_action,
    get_accessible_anomalies,
    get_anomaly_dashboard_metrics,
    run_batch_anomaly_detection,
    user_can_access_anomaly,
    user_can_review_anomaly,
)
from apps.core.auth_services import log_auth_event, role_required
from apps.core.models import (
    ActivityCategory,
    ActivityRecord,
    AnomalyCategory,
    AnomalyRecord,
    AnomalySeverity,
    AnomalyStatus,
    AuthAuditLog,
    Role,
    Site,
)
from apps.core.period_services import get_accessible_reporting_periods
from apps.core.scope_services import get_accessible_sites

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. ANOMALY DESK / LIST VIEW
# -----------------------------------------------------------------------------

@login_required
def anomaly_list_view(request):
    """
    Renders the Anomaly Desk workspace showing all accessible anomalies within the user's scope.
    """
    user = request.user
    base_qs = get_accessible_anomalies(user)

    search_query = request.GET.get("q", "").strip()
    severity_filter = request.GET.get("severity", "").strip()
    status_filter = request.GET.get("status", "").strip()
    category_filter = request.GET.get("category", "").strip()
    site_filter = request.GET.get("site", "").strip()
    period_filter = request.GET.get("period", "").strip()

    qs = base_qs

    if search_query:
        qs = qs.filter(
            models.Q(rule_code__icontains=search_query)
            | models.Q(explanation__icontains=search_query)
            | models.Q(activity_record__activity__name__icontains=search_query)
            | models.Q(activity_record__activity__code__icontains=search_query)
            | models.Q(activity_record__site__name__icontains=search_query)
            | models.Q(activity_record__site__code__icontains=search_query)
        )

    if severity_filter:
        qs = qs.filter(severity=severity_filter)

    if status_filter:
        qs = qs.filter(status=status_filter)

    if category_filter:
        qs = qs.filter(rule__category=category_filter)

    if site_filter:
        qs = qs.filter(activity_record__site_id=site_filter)

    if period_filter:
        qs = qs.filter(activity_record__reporting_period_id=period_filter)

    # Real metrics without fabrication
    metrics = get_anomaly_dashboard_metrics(user)

    # Pagination
    paginator = Paginator(qs, 15)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    accessible_sites = get_accessible_sites(user).order_by("name")
    accessible_periods = get_accessible_reporting_periods(user).order_by("-start_date")

    context = {
        "page_title": "ESG Anomaly Desk",
        "page_subtitle": "Operational Telemetry Pattern Inspection & Review Signals",
        "active_nav": "anomalies",
        "anomalies": page_obj,
        "page_obj": page_obj,
        "metrics": metrics,
        "search_query": search_query,
        "severity_filter": severity_filter,
        "status_filter": status_filter,
        "category_filter": category_filter,
        "site_filter": site_filter,
        "period_filter": period_filter,
        "severity_choices": AnomalySeverity.choices,
        "status_choices": AnomalyStatus.choices,
        "category_choices": AnomalyCategory.choices,
        "accessible_sites": accessible_sites,
        "accessible_periods": accessible_periods,
    }
    return render(request, "anomalies/anomaly_list.html", context)


# -----------------------------------------------------------------------------
# 2. ANOMALY DETAIL VIEW
# -----------------------------------------------------------------------------

@login_required
def anomaly_detail_view(request, anomaly_id):
    """
    Renders deep detail view for an AnomalyRecord.
    Enforces strict server-side anti-IDOR authorization.
    """
    user = request.user
    anomaly = get_object_or_404(
        AnomalyRecord.objects.select_related(
            "activity_record",
            "activity_record__activity",
            "activity_record__activity__category",
            "activity_record__unit",
            "activity_record__site",
            "activity_record__site__project",
            "activity_record__site__project__subsidiary",
            "activity_record__site__project__subsidiary__company",
            "activity_record__reporting_period",
            "submission",
            "submission__submitted_by",
            "rule",
            "reviewed_by",
            "detection_run",
        ),
        pk=anomaly_id,
    )

    # Anti-IDOR Check
    if not user_can_access_anomaly(user, anomaly):
        log_auth_event(
            event_type=AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"AnomalyRecord:{anomaly_id}:Detail",
            details=f"IDOR violation: User '{user.username}' denied access to unassigned Anomaly #{anomaly_id}.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have authorization to view this anomaly.")

    can_review = user_can_review_anomaly(user, anomaly)
    action_form = AnomalyReviewActionForm()

    record = anomaly.activity_record
    evidence_files = record.evidence_files.filter(status="ACTIVE").order_by("-created_at")

    # Other anomalies on the same activity record
    related_anomalies = (
        AnomalyRecord.objects.filter(activity_record=record)
        .exclude(id=anomaly.id)
        .select_related("rule")
        .order_by("-created_at")
    )

    context = {
        "page_title": f"Anomaly #{anomaly.id} Detail",
        "page_subtitle": f"{record.activity.name} @ {record.site.name} ({record.reporting_period.code})",
        "active_nav": "anomalies",
        "anomaly": anomaly,
        "record": record,
        "evidence_files": evidence_files,
        "related_anomalies": related_anomalies,
        "can_review": can_review,
        "action_form": action_form,
    }
    return render(request, "anomalies/anomaly_detail.html", context)


# -----------------------------------------------------------------------------
# 3. ANOMALY REVIEW ACTION HANDLER (POST ONLY & CSRF)
# -----------------------------------------------------------------------------

@login_required
@require_POST
def anomaly_review_action_view(request, anomaly_id):
    """
    Processes Anomaly Review Actions:
    - ACKNOWLEDGE
    - EXPLAIN
    - RESOLVE
    - DISMISS
    """
    user = request.user
    anomaly = get_object_or_404(
        AnomalyRecord.objects.select_related("activity_record", "activity_record__site"),
        pk=anomaly_id,
    )

    # Anti-IDOR and Review Permission Check
    if not user_can_review_anomaly(user, anomaly):
        log_auth_event(
            event_type=AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"AnomalyRecord:{anomaly_id}:ReviewAction",
            details=f"Unauthorized anomaly action attempt by user '{user.username}'.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have authorization to review this anomaly.")

    form = AnomalyReviewActionForm(request.POST)
    next_url = request.POST.get("next") or reverse("core:anomaly_detail", kwargs={"anomaly_id": anomaly.id})

    if form.is_valid():
        action = form.cleaned_data["action"]
        comment = form.cleaned_data["comment"]
        try:
            execute_anomaly_review_action(
                anomaly=anomaly,
                action=action,
                comment=comment,
                user=user,
                request=request,
            )
            messages.success(
                request,
                f"Anomaly #{anomaly.id} successfully transitioned to {action}.",
            )
        except ValidationError as exc:
            messages.error(request, f"Action blocked: {exc.message if hasattr(exc, 'message') else str(exc)}")
        except Exception as exc:
            logger.error("Failed to execute review action on Anomaly #%d: %s", anomaly.id, exc, exc_info=True)
            messages.error(request, f"An unexpected error occurred: {exc}")
    else:
        err_msg = "; ".join([f"{f}: {e[0]}" for f, e in form.errors.items()])
        messages.error(request, f"Please correct form errors: {err_msg}")

    return redirect(next_url)


# -----------------------------------------------------------------------------
# 4. ON-DEMAND ANOMALY DETECTION TRIGGER
# -----------------------------------------------------------------------------

@login_required
@require_POST
def anomaly_run_detection_view(request, record_id):
    """
    Triggers deterministic anomaly detection on demand for an ActivityRecord.
    """
    user = request.user
    record = get_object_or_404(
        ActivityRecord.objects.select_related("site", "reporting_period", "activity"),
        pk=record_id,
    )

    # Verify site access
    from apps.core.data_entry_services import user_can_access_activity_record

    if not user_can_access_activity_record(user, record):
        raise PermissionDenied("Access Denied: You do not have access to this activity record.")

    detected = detect_anomalies_for_record(
        record=record,
        user=user,
        request=request,
    )

    if detected:
        messages.warning(
            request,
            f"Anomaly detection completed: {len(detected)} potential operational issue(s) identified.",
        )
    else:
        messages.success(
            request,
            "Anomaly detection completed: Record conforms to expected operational baselines.",
        )

    next_url = request.POST.get("next") or reverse("core:activity_record_detail", kwargs={"record_id": record.id})
    return redirect(next_url)
