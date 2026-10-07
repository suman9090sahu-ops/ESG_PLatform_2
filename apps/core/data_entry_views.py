"""
Views for ESG Data Entry and Activity Telemetry for MEIL ESG CONTROL TOWER.

Fulfills Phase 08 Requirements:
- Scoped Activity Records List with Filter Bar and Operational Counters
- Secure Activity Record Creation Form with Auto-selection and Multi-action Draft / Ready support
- Read-only Record Detail View with Lineage and Downstream Evidence / Calculation Integration Points
- Scoped Record Editing guarded against Tampering and Protected Lifecycle States
- Safe Draft Record Deletion with Audit Logging
- Dynamic Unit Selector AJAX API endpoint
- Rigorous Anti-IDOR Protections and Server-side Scope Enforcement
"""

import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.auth_services import log_auth_event, role_required
from apps.core.data_entry_forms import (
    ActivityRecordFilterForm,
    ActivityRecordForm,
)
from apps.core.data_entry_services import (
    get_accessible_activity_records,
    get_candidate_activities_for_data_entry,
    get_candidate_periods_for_site,
    get_candidate_sites_for_data_entry,
    get_candidate_units_for_activity,
    log_activity_record_event,
    user_can_access_activity_record,
    user_can_create_activity_record,
    user_can_delete_activity_record,
    user_can_modify_activity_record,
)
from apps.core.evidence_services import user_can_upload_evidence
from apps.core.validation_services import user_can_validate_record
from apps.core.models import (
    ActivityMaster,
    ActivityRecord,
    AuthAuditLog,
    MasterStatus,
    OrganizationStatus,
    PeriodStatus,
    RecordStatus,
    ReportingPeriod,
    Role,
    Site,
)
from apps.core.period_services import get_accessible_reporting_periods
from apps.core.scope_services import user_can_access_site

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. ACTIVITY RECORDS LEDGER / LIST VIEW
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.SITE_MANAGER,
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.MEIL_OPERATOR,
    Role.Code.ESG_MANAGER,
    Role.Code.AUDITOR,
)
def activity_record_list_view(request):
    """
    Displays the scoped list of ESG Activity Records for the logged-in user.
    Supports filtering by site, period, category, status, date range, and search.
    """
    user = request.user
    base_qs = get_accessible_activity_records(user)

    # Initialize filter form
    filter_form = ActivityRecordFilterForm(request.GET or None, user=user)
    records_qs = base_qs

    if filter_form.is_valid():
        site = filter_form.cleaned_data.get("site")
        reporting_period = filter_form.cleaned_data.get("reporting_period")
        category = filter_form.cleaned_data.get("category")
        status = filter_form.cleaned_data.get("status")
        validation_status = filter_form.cleaned_data.get("validation_status")
        date_from = filter_form.cleaned_data.get("date_from")
        date_to = filter_form.cleaned_data.get("date_to")
        search = filter_form.cleaned_data.get("search")

        if site:
            records_qs = records_qs.filter(site=site)
        if reporting_period:
            records_qs = records_qs.filter(reporting_period=reporting_period)
        if category:
            records_qs = records_qs.filter(activity__category=category)
        if status:
            records_qs = records_qs.filter(status=status)
        if validation_status:
            records_qs = records_qs.filter(validation_status=validation_status)
        if date_from:
            records_qs = records_qs.filter(measurement_date__gte=date_from)
        if date_to:
            records_qs = records_qs.filter(measurement_date__lte=date_to)
        if search:
            records_qs = records_qs.filter(
                models.Q(notes__icontains=search)
                | models.Q(evidence_reference__icontains=search)
                | models.Q(activity__name__icontains=search)
                | models.Q(activity__code__icontains=search)
                | models.Q(site__name__icontains=search)
            )

    # Operational metrics
    total_count = base_qs.count()
    draft_count = base_qs.filter(status=RecordStatus.DRAFT).count()
    ready_count = base_qs.filter(status=RecordStatus.READY).count()
    submitted_count = base_qs.filter(
        status__in=[RecordStatus.SUBMITTED, RecordStatus.VERIFIED, RecordStatus.APPROVED]
    ).count()

    # Pagination
    paginator = Paginator(records_qs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    can_create = user_can_create_activity_record(user)

    context = {
        "page_title": "ESG Activity Records",
        "page_subtitle": "Operational Telemetry Ledger & Activity Logs",
        "active_nav": "activity_records",
        "filter_form": filter_form,
        "page_obj": page_obj,
        "records": page_obj.object_list,
        "total_count": total_count,
        "draft_count": draft_count,
        "ready_count": ready_count,
        "submitted_count": submitted_count,
        "can_create": can_create,
    }
    return render(request, "data_entry/record_list.html", context)


# -----------------------------------------------------------------------------
# 2. ACTIVITY RECORD CREATE VIEW
# -----------------------------------------------------------------------------

@login_required
@role_required(Role.Code.SITE_MANAGER, Role.Code.MEIL_OPERATOR, Role.Code.ESG_MANAGER)
def activity_record_create_view(request):
    """
    Handles creation of a new ESG Activity Record by an authorized manager.
    Supports pre-populating candidate site, period, or activity from query string with anti-IDOR validation.
    """
    user = request.user
    candidate_sites = get_candidate_sites_for_data_entry(user)

    if not candidate_sites.exists():
        messages.warning(
            request,
            "You have no active operational sites assigned to your account for ESG data entry. "
            "Please contact your subsidiary manager or administrator."
        )
        return redirect("core:site_manager_dashboard")

    # Initial object resolvers with server-side authorization check
    initial_site = None
    site_param = request.GET.get("site_id")
    if site_param:
        try:
            candidate = Site.objects.get(pk=site_param)
            if user_can_access_site(user, candidate) and candidate.status == OrganizationStatus.ACTIVE:
                initial_site = candidate
            else:
                log_auth_event(
                    AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
                    request=request,
                    user=user,
                    resource_accessed=f"Site:{site_param}",
                    details="Attempted data entry creation for unassigned site.",
                    success=False,
                )
                raise PermissionDenied("You are not authorized to record data for this operational site.")
        except Site.DoesNotExist:
            pass

    initial_period = None
    period_param = request.GET.get("period_id")
    if period_param:
        try:
            candidate_p = ReportingPeriod.objects.get(pk=period_param)
            if candidate_p.status == PeriodStatus.OPEN and candidate_p in get_accessible_reporting_periods(user):
                initial_period = candidate_p
            else:
                raise PermissionDenied("Reporting period is closed or unauthorized for data entry.")
        except ReportingPeriod.DoesNotExist:
            pass

    initial_activity = None
    activity_param = request.GET.get("activity_id")
    if activity_param:
        try:
            candidate_a = ActivityMaster.objects.get(pk=activity_param)
            if candidate_a.is_active and candidate_a.status == MasterStatus.ACTIVE:
                initial_activity = candidate_a
        except ActivityMaster.DoesNotExist:
            pass

    if request.method == "POST":
        form = ActivityRecordForm(
            request.POST,
            user=user,
            initial_site=initial_site,
            initial_period=initial_period,
            initial_activity=initial_activity,
        )
        if form.is_valid():
            record = form.save(commit=False)
            record.created_by = user
            record.updated_by = user
            record.save()

            log_activity_record_event(
                AuthAuditLog.EventType.ACTIVITY_RECORD_CREATED,
                record=record,
                user=user,
                request=request,
                details=(
                    f"Created {record.status} activity record for site '{record.site.name}' "
                    f"({record.activity.name}: {record.quantity} {record.unit.symbol})."
                ),
            )

            status_label = "Draft saved" if record.status == RecordStatus.DRAFT else "Record logged and marked ready"
            messages.success(
                request,
                f"{status_label} successfully: {record.activity.name} "
                f"({record.quantity} {record.unit.symbol}) for site {record.site.name}."
            )
            return redirect("core:activity_record_detail", record_id=record.id)
    else:
        form = ActivityRecordForm(
            user=user,
            initial_site=initial_site,
            initial_period=initial_period,
            initial_activity=initial_activity,
        )

    context = {
        "page_title": "New ESG Data Entry",
        "page_subtitle": "Record Operational Consumption & ESG Activity Telemetry",
        "active_nav": "data_entry",
        "form": form,
        "candidate_sites_count": candidate_sites.count(),
        "is_create": True,
    }
    return render(request, "data_entry/record_form.html", context)


# -----------------------------------------------------------------------------
# 3. ACTIVITY RECORD DETAIL VIEW
# -----------------------------------------------------------------------------

@login_required
@role_required(
    Role.Code.SITE_MANAGER,
    Role.Code.SUBSIDIARY_MANAGER,
    Role.Code.MEIL_OPERATOR,
    Role.Code.ESG_MANAGER,
    Role.Code.AUDITOR,
)
def activity_record_detail_view(request, record_id):
    """
    Displays the detailed, read-only operational telemetry of a specific ActivityRecord.
    Server-enforces object-level scoping to prevent IDOR access.
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

    if not user_can_access_activity_record(user, record):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"ActivityRecord:{record_id}",
            details=f"Attempted inspection of unauthorized ActivityRecord for site {record.site.code}.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have permission to view this activity record.")

    can_edit = user_can_modify_activity_record(user, record)
    can_delete = user_can_delete_activity_record(user, record)
    can_upload_evidence = user_can_upload_evidence(user, record)
    can_validate = user_can_validate_record(user, record)
    evidence_files = record.evidence_files.select_related("uploaded_by").order_by("-created_at")

    validation_runs = record.validation_runs.select_related("executed_by").prefetch_related("results__rule").order_by("-executed_at", "-run_number")
    latest_run = validation_runs.first()
    validation_results = latest_run.results.select_related("rule").order_by("severity", "id") if latest_run else []

    context = {
        "page_title": f"Activity Record #{record.id}",
        "page_subtitle": f"{record.activity.name} @ {record.site.name}",
        "active_nav": "activity_records",
        "record": record,
        "can_edit": can_edit,
        "can_delete": can_delete,
        "can_upload_evidence": can_upload_evidence,
        "can_validate": can_validate,
        "evidence_files": evidence_files,
        "latest_validation_run": latest_run,
        "validation_runs": validation_runs,
        "validation_results": validation_results,
    }
    return render(request, "data_entry/record_detail.html", context)


# -----------------------------------------------------------------------------
# 4. ACTIVITY RECORD EDIT VIEW
# -----------------------------------------------------------------------------

@login_required
@role_required(Role.Code.SITE_MANAGER, Role.Code.MEIL_OPERATOR, Role.Code.ESG_MANAGER)
def activity_record_edit_view(request, record_id):
    """
    Handles updating an existing ActivityRecord.
    Permitted only while the record is in an editable lifecycle state (DRAFT, READY, REJECTED)
    and the governing reporting period is OPEN.
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

    if not user_can_access_activity_record(user, record):
        log_auth_event(
            AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            request=request,
            user=user,
            resource_accessed=f"ActivityRecord:{record_id}:edit",
            details="Unauthorized edit attempt on protected ActivityRecord.",
            success=False,
        )
        raise PermissionDenied("Access Denied: You do not have permission to access this activity record.")

    if not user_can_modify_activity_record(user, record):
        raise PermissionDenied(
            f"This activity record cannot be edited because its status is '{record.get_status_display()}' "
            f"or the reporting period '{record.reporting_period.code}' is closed."
        )

    if request.method == "POST":
        form = ActivityRecordForm(request.POST, instance=record, user=user)
        if form.is_valid():
            updated_record = form.save(commit=False)
            updated_record.updated_by = user
            updated_record.save()

            log_activity_record_event(
                AuthAuditLog.EventType.ACTIVITY_RECORD_UPDATED,
                record=updated_record,
                user=user,
                request=request,
                details=f"Updated activity record #{record.id} for site '{record.site.name}'.",
            )

            messages.success(request, f"Activity record #{record.id} updated successfully.")
            return redirect("core:activity_record_detail", record_id=record.id)
    else:
        form = ActivityRecordForm(instance=record, user=user)

    context = {
        "page_title": f"Edit Activity Record #{record.id}",
        "page_subtitle": f"{record.activity.name} @ {record.site.name}",
        "active_nav": "activity_records",
        "form": form,
        "record": record,
        "is_create": False,
    }
    return render(request, "data_entry/record_form.html", context)


# -----------------------------------------------------------------------------
# 5. ACTIVITY RECORD DELETE VIEW
# -----------------------------------------------------------------------------

@login_required
@role_required(Role.Code.SITE_MANAGER, Role.Code.MEIL_OPERATOR, Role.Code.ESG_MANAGER)
@require_http_methods(["GET", "POST"])
def activity_record_delete_view(request, record_id):
    """
    Handles safe deletion of DRAFT ActivityRecords.
    Non-draft or protected records cannot be deleted.
    """
    user = request.user
    record = get_object_or_404(ActivityRecord, pk=record_id)

    if not user_can_access_activity_record(user, record):
        raise PermissionDenied("Access Denied: You do not have permission to access this record.")

    if not user_can_delete_activity_record(user, record):
        raise PermissionDenied("Only draft activity records in open reporting cycles can be deleted.")

    if request.method == "POST":
        summary_desc = f"Activity record #{record.id} ({record.activity.name} @ {record.site.name})"
        log_activity_record_event(
            AuthAuditLog.EventType.ACTIVITY_RECORD_DELETED,
            record=record,
            user=user,
            request=request,
            details=f"Deleted draft activity record #{record.id}.",
        )
        record.delete()
        messages.success(request, f"Draft record #{record_id} deleted successfully.")
        return redirect("core:activity_record_list")

    context = {
        "page_title": f"Confirm Deletion — Record #{record.id}",
        "record": record,
    }
    return render(request, "data_entry/record_confirm_delete.html", context)


# -----------------------------------------------------------------------------
# 6. DYNAMIC UNIT SELECTOR API (AJAX Helper)
# -----------------------------------------------------------------------------

@login_required
def activity_units_api_view(request):
    """
    JSON API endpoint returning allowed UnitOfMeasure entries for a given activity_id.
    Used by frontend Vanilla JS to dynamically adjust unit choices without full page reload.
    """
    activity_id = request.GET.get("activity_id")
    if not activity_id:
        return JsonResponse({"error": "activity_id parameter required"}, status=400)

    try:
        activity = ActivityMaster.objects.get(pk=activity_id)
    except ActivityMaster.DoesNotExist:
        return JsonResponse({"error": "Activity not found"}, status=404)

    units_qs = get_candidate_units_for_activity(activity)
    units_data = [
        {
            "id": u.id,
            "name": u.name,
            "symbol": u.symbol,
            "dimension": u.dimension,
            "is_base": (u.id == activity.base_unit_id),
        }
        for u in units_qs
    ]

    return JsonResponse({
        "activity_id": activity.id,
        "activity_name": activity.name,
        "base_unit_id": activity.base_unit_id,
        "units": units_data,
    })
