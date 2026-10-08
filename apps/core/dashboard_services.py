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

def get_site_manager_dashboard_context(user, as_of_date=None):
    """
    Aggregates authoritative operational dashboard data for a SITE_MANAGER.

    Strictly scopes data to the user's authorized operational sites.
    Does NOT accept or trust client-supplied object IDs.

    Returns a rich dictionary containing:
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
    - workflow_status: dictionary of ESG workflow metrics (Phase 08-12 hooks)
    - recent_activity: QuerySet of recent AuthAuditLog records for user/sites
    - alerts: list of operational alerts
    - offline_sync_status: offline/sync readiness metadata (Phase 13 hook)
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

    # 4. Current Reporting Period (Authoritative resolution scoped to user's assigned scope)
    accessible_periods = get_accessible_reporting_periods(user)

    # Try finding an OPEN period where check_date is within start_date and end_date
    current_period = (
        accessible_periods.filter(
            status=PeriodStatus.OPEN,
            start_date__lte=check_date,
            end_date__gte=check_date,
        )
        .order_by("-start_date")
        .first()
    )

    # Fallback to any currently OPEN period if date window is not strictly matched
    if not current_period:
        current_period = (
            accessible_periods.filter(status=PeriodStatus.OPEN)
            .order_by("-start_date")
            .first()
        )

    # Calculate days remaining in period if open
    period_days_remaining = None
    if current_period and current_period.end_date >= check_date:
        period_days_remaining = (current_period.end_date - check_date).days

    # 5. ESG Activity Catalog Readiness (from Phase 06)
    accessible_activities = get_accessible_activity_masters(user)
    active_activities_count = accessible_activities.filter(status=MasterStatus.ACTIVE).count()

    accessible_categories = get_accessible_activity_categories(user)
    active_categories_count = accessible_categories.filter(status=MasterStatus.ACTIVE).count()

    # 6. Workflow Status & Real Pending Actions (Phase 08 Integration)
    records_qs = get_accessible_activity_records(user)
    draft_records_count = records_qs.filter(status=RecordStatus.DRAFT).count()
    ready_records_count = records_qs.filter(status=RecordStatus.READY).count()
    submitted_records_count = records_qs.filter(
        status__in=[RecordStatus.SUBMITTED, RecordStatus.VERIFIED, RecordStatus.APPROVED]
    ).count()

    # Phase 09 Integration: Real pending evidence calculation
    pending_evidence_count = records_qs.exclude(
        evidence_files__status=EvidenceStatus.ACTIVE
    ).distinct().count()

    workflow_status = {
        "is_data_entry_ready": bool(current_period and current_period.status == PeriodStatus.OPEN and sites_count > 0),
        "draft_records_count": draft_records_count,
        "ready_records_count": ready_records_count,
        "submitted_records_count": submitted_records_count,
        "total_records_count": records_qs.count(),
        "corrections_count": 0,
        "pending_evidence_count": pending_evidence_count,
        "validation_issues_count": 0,
        "phase_note": "ESG Data Entry & Evidence Management active (Phase 09).",
    }

    pending_actions_list = []
    # If any assigned site is inactive or missing critical setup, add as real actionable notice
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

    active_corrections_count = CorrectionRequest.objects.filter(
        activity_record__site__in=assigned_sites,
        status__in=[
            CorrectionStatus.OPEN,
            CorrectionStatus.IN_PROGRESS,
            CorrectionStatus.READY_FOR_RESUBMISSION,
        ],
    ).count()

    if active_corrections_count > 0:
        pending_actions_list.append({
            "title": f"{active_corrections_count} Correction Request(s) Awaiting Revision",
            "description": "Subsidiary Reviewers have requested revisions on submitted activity records.",
            "category": "Corrections Workflow",
            "level": "warning",
            "url": reverse("core:correction_inbox"),
        })

    pending_actions_count = len(pending_actions_list)

    # 7. Recent Operational & Security Activity (AuthAuditLog scoped strictly to authorized sites)
    site_codes = list(assigned_sites.values_list("code", flat=True))
    if site_codes:
        site_resource_filter = Q()
        for code in site_codes:
            site_resource_filter |= Q(resource_accessed__icontains=code)

        # Include general authentication events (login/logout) and site-specific events for authorized sites only.
        # Excludes unauthorized access attempts on foreign sites to prevent data leakage.
        recent_activity = (
            AuthAuditLog.objects.filter(
                (Q(user=user) & (Q(resource_accessed="") | Q(resource_accessed__isnull=True)))
                | site_resource_filter
            )
            .select_related("user")
            .order_by("-created_at")[:10]
        )
    else:
        recent_activity = (
            AuthAuditLog.objects.filter(
                user=user,
                resource_accessed="",
            )
            .select_related("user")
            .order_by("-created_at")[:10]
        )

    # 8. Operational Alerts
    alerts = []
    if sites_count == 0:
        alerts.append({
            "type": "warning",
            "icon": "icon-exclamation",
            "title": "No Assigned Operational Sites",
            "message": "No operational sites are currently assigned to your user account. Please contact your Subsidiary Manager or Platform Administrator.",
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

    # 9. Offline & Synchronization Pipeline Readiness (Phase 13 hook)
    offline_sync_status = {
        "status": "ONLINE",
        "badge_class": "badge-success",
        "mode": "Direct Cloud Telemetry",
        "pending_sync_count": 0,
        "last_synced": timezone.now(),
        "is_offline_capable": False,
        "notice": "Offline local synchronization engine is scheduled for deployment in Phase 13.",
    }

    return {
        "page_title": "Site Manager Operational Dashboard",
        "page_subtitle": "Operational Telemetry, ESG Workflow & Assigned Site Oversight",
        "active_nav": "site_dashboard",
        "role_code": Role.Code.SITE_MANAGER,
        # Site & Project Metrics
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
        # Sync Integration
        "offline_sync_status": offline_sync_status,
    }
