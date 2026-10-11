"""
Dashboard Data Aggregation and Scoping Services for MEIL ESG CONTROL TOWER.

Fulfills Phase 07 Requirements:
- Scoped Site Manager operational dashboard context aggregation (get_site_manager_dashboard_context)
- Server-side object-level access boundaries (no client parameter trust)
- Optimization with select_related / prefetch_related preventing N+1 queries
- Integration with Phase 04 Reporting Periods, Phase 05 Projects & Sites, and Phase 06 Activity Master
- Real metrics aggregation without fabricated statistics
- Clean integration hooks for future Phase 08 (Data Entry) and Phase 13 (Offline Sync)
"""

import logging
from datetime import timedelta
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Count, Q
from django.utils import timezone

from django.urls import reverse

from apps.core.activity_services import (
    get_accessible_activity_categories,
    get_accessible_activity_masters,
)
from apps.core.data_entry_services import get_accessible_activity_records
from apps.core.models import (
    AuthAuditLog,
    CorrectionRequest,
    CorrectionStatus,
    EvidenceStatus,
    MasterStatus,
    OrganizationStatus,
    PeriodStatus,
    Project,
    RecordStatus,
    ReportingPeriod,
    Role,
    Site,
    Submission,
    SubmissionStatus,
    ValidationStatus,
)
from apps.core.period_services import get_accessible_reporting_periods
from apps.core.scope_services import (
    get_accessible_companies,
    get_accessible_projects,
    get_accessible_sites,
    get_accessible_subsidiaries,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# SITE MANAGER DASHBOARD SERVICE
# -----------------------------------------------------------------------------

def get_site_manager_dashboard_context(user, as_of_date=None, requested_site_id=None):
    """
    Aggregates authoritative operational workspace data for a SITE_MANAGER.

    Strictly scopes data to the user's authorized operational site assignment.
    Does NOT accept or trust unassigned client-supplied object IDs.

    Returns a rich dictionary containing:
    - selected_site: active authoritative Site instance (or None)
    - site_summary: compact metrics scoped strictly to selected_site
    - guided_workflow: 4-step pipeline (Data Entry -> Evidence -> Validation -> Submit)
    - site_submissions: recent submissions for selected_site
    - site_corrections: pending corrections for selected_site
    - assigned_sites: QuerySet of Site models optimized with select_related
    - assigned_projects: QuerySet of Project models containing the user's sites
    - sites_count: total authorized sites
    - active_sites_count: count of active operational sites
    - projects_count: count of unique parent projects
    - active_projects_count: count of active parent projects
    - current_period: authoritative current OPEN ReportingPeriod (or None)
    - accessible_periods: QuerySet of all accessible ReportingPeriods
    - active_activities_count: count of approved active ESG master activities
    - active_categories_count: count of active activity categories
    - pending_actions_count: real count of pending items (0 if none)
    - pending_actions_list: list of actionable items
    - workflow_status: dictionary of ESG workflow metrics
    - recent_activity: QuerySet of recent AuthAuditLog records for user/site
    - alerts: list of operational alerts
    """
    if not user or not user.is_authenticated or not user.is_active:
        raise PermissionDenied("User is not authenticated or account is inactive.")

    check_date = as_of_date or timezone.now().date()

    # 1. Accessible Sites (Optimized with select_related to eliminate N+1 queries)
    assigned_sites = (
        get_accessible_sites(user)
        .select_related(
            "project",
            "project__subsidiary",
            "project__subsidiary__company",
            "created_by",
            "updated_by",
        )
        .order_by("name")
    )

    sites_count = assigned_sites.count()
    active_sites_count = assigned_sites.filter(status=OrganizationStatus.ACTIVE).count()
    inactive_sites_count = sites_count - active_sites_count

    # Resolve selected site safely (server-enforced authorization)
    selected_site = None
    if sites_count > 0:
        if requested_site_id:
            try:
                req_id = int(requested_site_id)
                selected_site = assigned_sites.filter(id=req_id).first()
            except (ValueError, TypeError):
                selected_site = None
        if not selected_site:
            selected_site = assigned_sites.first()

    # 2. Accessible Projects (Distinct parent projects containing authorized sites)
    assigned_projects = (
        get_accessible_projects(user)
        .select_related("subsidiary", "subsidiary__company")
        .order_by("name")
    )

    projects_count = assigned_projects.count()
    active_projects_count = assigned_projects.filter(status=OrganizationStatus.ACTIVE).count()

    # 3. Accessible Companies & Subsidiaries (for organizational context)
    accessible_companies = get_accessible_companies(user)
    accessible_subsidiaries = get_accessible_subsidiaries(user)

    # 4. Current Reporting Period (Authoritative resolution scoped to site's corporate scope)
    accessible_periods = get_accessible_reporting_periods(user)

    current_period = None
    if selected_site and selected_site.project and selected_site.project.subsidiary:
        site_company = selected_site.project.subsidiary.company
        current_period = (
            accessible_periods.filter(
                company=site_company,
                status=PeriodStatus.OPEN,
                start_date__lte=check_date,
                end_date__gte=check_date,
            )
            .order_by("-start_date")
            .first()
        )
        if not current_period:
            current_period = (
                accessible_periods.filter(
                    company=site_company,
                    status=PeriodStatus.OPEN,
                )
                .order_by("-start_date")
                .first()
            )

    if not current_period:
        current_period = (
            accessible_periods.filter(
                status=PeriodStatus.OPEN,
                start_date__lte=check_date,
                end_date__gte=check_date,
            )
            .order_by("-start_date")
            .first()
        )
        if not current_period:
            current_period = (
                accessible_periods.filter(status=PeriodStatus.OPEN)
                .order_by("-start_date")
                .first()
            )

    period_days_remaining = None
    if current_period and current_period.end_date >= check_date:
        period_days_remaining = (current_period.end_date - check_date).days

    # 5. ESG Activity Catalog Readiness
    accessible_activities = get_accessible_activity_masters(user)
    active_activities_count = accessible_activities.filter(status=MasterStatus.ACTIVE).count()

    accessible_categories = get_accessible_activity_categories(user)
    active_categories_count = accessible_categories.filter(status=MasterStatus.ACTIVE).count()

    # 6. Workflow Status & Real Pending Actions Scoped to Site
    records_qs = get_accessible_activity_records(user)
    if selected_site:
        site_records_qs = records_qs.filter(site=selected_site)
        site_corrections_qs = CorrectionRequest.objects.filter(
            activity_record__site=selected_site,
            status__in=[
                CorrectionStatus.OPEN,
                CorrectionStatus.IN_PROGRESS,
                CorrectionStatus.READY_FOR_RESUBMISSION,
            ],
        ).select_related("activity_record", "activity_record__activity", "requested_by", "submission").order_by("-created_at")
        site_submissions_qs = Submission.objects.filter(
            site=selected_site,
        ).select_related("activity_record", "activity_record__activity", "reporting_period", "submitted_by").order_by("-submitted_at")
    else:
        site_records_qs = records_qs.none()
        site_corrections_qs = CorrectionRequest.objects.none()
        site_submissions_qs = Submission.objects.none()

    draft_records_count = site_records_qs.filter(status=RecordStatus.DRAFT).count()
    ready_records_count = site_records_qs.filter(status=RecordStatus.READY).count()
    submitted_records_count = site_records_qs.filter(
        status__in=[RecordStatus.SUBMITTED, RecordStatus.VERIFIED, RecordStatus.APPROVED]
    ).count()
    total_records_count = site_records_qs.count()

    pending_evidence_count = site_records_qs.exclude(
        evidence_files__status=EvidenceStatus.ACTIVE
    ).distinct().count()

    validation_issues_count = site_records_qs.filter(
        validation_status=ValidationStatus.INVALID
    ).count()

    active_corrections_count = site_corrections_qs.count()
    submissions_awaiting_action = site_submissions_qs.filter(
        status__in=[SubmissionStatus.SUBMITTED, SubmissionStatus.UNDER_REVIEW]
    ).count()

    workflow_status = {
        "is_data_entry_ready": bool(current_period and current_period.status == PeriodStatus.OPEN and sites_count > 0),
        "draft_records_count": draft_records_count,
        "ready_records_count": ready_records_count,
        "submitted_records_count": submitted_records_count,
        "total_records_count": total_records_count,
        "corrections_count": active_corrections_count,
        "pending_evidence_count": pending_evidence_count,
        "validation_issues_count": validation_issues_count,
        "phase_note": "MEIL ESG Platform End-to-End Governance Engine Active.",
    }

    pending_actions_list = []
    if inactive_sites_count > 0:
        pending_actions_list.append({
            "title": f"{inactive_sites_count} Inactive Site(s) Detected",
            "description": "One or more assigned sites are marked INACTIVE and require operational status verification.",
            "category": "Site Governance",
            "level": "warning",
            "url": "#",
        })

    if draft_records_count > 0:
        pending_actions_list.append({
            "title": f"{draft_records_count} Draft Activity Record(s)",
            "description": "You have saved draft activity records awaiting completion or review.",
            "category": "ESG Data Entry",
            "level": "info",
            "url": reverse("core:activity_record_list") + f"?status={RecordStatus.DRAFT}",
        })

    if active_corrections_count > 0:
        pending_actions_list.append({
            "title": f"{active_corrections_count} Correction Request(s) Awaiting Revision",
            "description": "Subsidiary Reviewers have requested revisions on submitted activity records.",
            "category": "Corrections Workflow",
            "level": "warning",
            "url": reverse("core:correction_inbox"),
        })

    pending_actions_count = len(pending_actions_list)

    # 7. Recent Operational & Security Activity (AuthAuditLog scoped strictly to authorized site)
    if selected_site:
        site_resource_filter = Q(resource_accessed__icontains=selected_site.code)
        recent_activity = (
            AuthAuditLog.objects.filter(
                (Q(user=user) & (Q(resource_accessed="") | Q(resource_accessed__isnull=True)))
                | site_resource_filter
            )
            .select_related("user")
            .order_by("-created_at")[:10]
        )
    elif sites_count > 0:
        site_codes = list(assigned_sites.values_list("code", flat=True))
        site_resource_filter = Q()
        for code in site_codes:
            site_resource_filter |= Q(resource_accessed__icontains=code)
        recent_activity = (
            AuthAuditLog.objects.filter(
                (Q(user=user) & (Q(resource_accessed="") | Q(resource_accessed__isnull=True)))
                | site_resource_filter
            )
            .select_related("user")
            .order_by("-created_at")[:10]
        )
    else:
        recent_activity = AuthAuditLog.objects.none()

    # 8. Operational Alerts
    alerts = []
    if sites_count == 0:
        alerts.append({
            "type": "warning",
            "icon": "icon-exclamation",
            "title": "No Assigned Operational Sites",
            "message": "No site has been assigned to your account. Please contact your administrator. No operational sites are currently assigned to your account. Please contact your subsidiary manager or platform administrator if this is unexpected.",
        })

    if not current_period:
        alerts.append({
            "type": "info",
            "icon": "icon-calendar",
            "title": "No Active Reporting Period",
            "message": "There is currently no open reporting cycle for your assigned organization scope. Operational data ingestion will commence once a period is opened.",
        })
    elif period_days_remaining is not None and period_days_remaining <= 30:
        alerts.append({
            "type": "warning",
            "icon": "icon-clock",
            "title": "Reporting Period Closing Soon",
            "message": f"Cycle {current_period.code} closes in {period_days_remaining} day(s) on {current_period.end_date:%d %B %Y}.",
        })

    # 9. Compact Site Summary
    site_summary = {
        "site_name": selected_site.name if selected_site else "No Site Assigned",
        "site_code": selected_site.code if selected_site else "—",
        "project_name": selected_site.project.name if selected_site else "—",
        "subsidiary_name": selected_site.project.subsidiary.name if selected_site and selected_site.project and selected_site.project.subsidiary else "—",
        "subsidiary_code": selected_site.project.subsidiary.code if selected_site and selected_site.project and selected_site.project.subsidiary else "—",
        "reporting_period_code": current_period.code if current_period else "None Open",
        "activities_requiring_data_entry": draft_records_count,
        "missing_evidence_count": pending_evidence_count,
        "validation_issues_count": validation_issues_count,
        "submissions_awaiting_action": submissions_awaiting_action,
        "corrections_count": active_corrections_count,
        "ready_records_count": ready_records_count,
        "total_records_count": total_records_count,
    }

    # 10. Guided Workflow Pipeline (4 Structured Steps)
    guided_workflow = [
        {
            "step_number": 1,
            "title": "Data Entry",
            "badge": "IN PROGRESS" if draft_records_count > 0 else ("READY" if current_period and current_period.status == PeriodStatus.OPEN and selected_site else "PAUSED"),
            "badge_class": "badge-warning" if draft_records_count > 0 else ("badge-success" if current_period and current_period.status == PeriodStatus.OPEN and selected_site else "badge-secondary"),
            "description": f"Enter and save activity telemetry records for {selected_site.name} under cycle {current_period.code}." if selected_site and current_period else "Enter and save operational activity records.",
            "metric_label": "Draft Records",
            "metric_value": draft_records_count,
            "action_label": "Log Data",
            "action_url": reverse("core:activity_record_create") + (f"?site_id={selected_site.id}" if selected_site else ""),
            "action_icon": "icon-pencil",
            "action_class": "btn-outline-primary",
        },
        {
            "step_number": 2,
            "title": "Evidence",
            "badge": "ATTENTION NEEDED" if pending_evidence_count > 0 else "UP TO DATE",
            "badge_class": "badge-warning" if pending_evidence_count > 0 else "badge-success",
            "description": "Upload and review supporting evidence documents (invoices, challans, meter logs).",
            "metric_label": "Missing Evidence",
            "metric_value": pending_evidence_count,
            "action_label": "Upload Evidence",
            "action_url": reverse("core:evidence_list") + (f"?site={selected_site.id}" if selected_site else ""),
            "action_icon": "icon-paper-clip",
            "action_class": "btn-outline-info",
        },
        {
            "step_number": 3,
            "title": "Validation",
            "badge": "ERRORS DETECTED" if validation_issues_count > 0 else ("VALIDATED" if ready_records_count > 0 or submitted_records_count > 0 else "READY"),
            "badge_class": "badge-danger" if validation_issues_count > 0 else "badge-success",
            "description": "Run automated validation checks to resolve missing fields and validation errors.",
            "metric_label": "Validation Issues",
            "metric_value": validation_issues_count,
            "action_label": "Review Issues" if validation_issues_count > 0 else "Validate Records",
            "action_url": reverse("core:activity_record_list") + (f"?site={selected_site.id}&validation_status={ValidationStatus.INVALID}" if selected_site else f"?validation_status={ValidationStatus.INVALID}"),
            "action_icon": "icon-check",
            "action_class": "btn-outline-warning" if validation_issues_count > 0 else "btn-outline-success",
        },
        {
            "step_number": 4,
            "title": "Submit & Track",
            "badge": "REVISION REQUIRED" if active_corrections_count > 0 else ("IN REVIEW" if submissions_awaiting_action > 0 else ("READY TO SUBMIT" if ready_records_count > 0 else "ON TRACK")),
            "badge_class": "badge-danger" if active_corrections_count > 0 else ("badge-warning" if submissions_awaiting_action > 0 else ("badge-primary" if ready_records_count > 0 else "badge-success")),
            "description": "Submit eligible records and monitor real review status and approval lineage.",
            "metric_label": "Awaiting Review",
            "metric_value": submissions_awaiting_action,
            "action_label": "View Corrections" if active_corrections_count > 0 else ("Submit Records" if ready_records_count > 0 else "Track Submissions"),
            "action_url": reverse("core:correction_inbox") if active_corrections_count > 0 else (reverse("core:activity_record_list") + f"?site={selected_site.id}&status={RecordStatus.READY}" if ready_records_count > 0 and selected_site else reverse("core:submission_list") + (f"?site={selected_site.id}" if selected_site else "")),
            "action_icon": "icon-paper-plane",
            "action_class": "btn-outline-primary",
        },
    ]

    # 11. Compatibility placeholder
    offline_sync_status = {
        "status": "ONLINE",
        "badge_class": "badge-success",
        "mode": "Direct Operational Connection",
        "pending_sync_count": 0,
        "last_synced": timezone.now(),
        "is_offline_capable": False,
        "notice": "Authoritative real-time operational connection active.",
    }

    return {
        "page_title": "My Assigned Site",
        "page_subtitle": "Operational Telemetry, ESG Workflow & Assigned Site Oversight",
        "active_nav": "my_assigned_site",
        "role_code": Role.Code.SITE_MANAGER,
        # Selected Site Scoping
        "selected_site": selected_site,
        "site_summary": site_summary,
        "guided_workflow": guided_workflow,
        "site_submissions": site_submissions_qs[:10],
        "site_corrections": site_corrections_qs[:10],
        # Assigned Sites & Projects
        "assigned_sites": assigned_sites,
        "assigned_projects": assigned_projects,
        "sites_count": sites_count,
        "active_sites_count": active_sites_count,
        "inactive_sites_count": inactive_sites_count,
        "projects_count": projects_count,
        "active_projects_count": active_projects_count,
        # Hierarchy context
        "accessible_companies": accessible_companies,
        "accessible_subsidiaries": accessible_subsidiaries,
        # Reporting Period
        "current_period": current_period,
        "accessible_periods": accessible_periods,
        "period_days_remaining": period_days_remaining,
        "check_date": check_date,
        # Activity Master Catalog
        "active_activities_count": active_activities_count,
        "active_categories_count": active_categories_count,
        # Workflow & Pending Actions
        "workflow_status": workflow_status,
        "pending_actions_count": pending_actions_count,
        "pending_actions_list": pending_actions_list,
        "active_corrections_count": active_corrections_count,
        # Activity Feed & Alerts
        "recent_activity": recent_activity,
        "alerts": alerts,
        # Compatibility hooks
        "offline_sync_status": offline_sync_status,
    }
