"""
ESG Data Entry and Activity Record Scoping Services for MEIL ESG CONTROL TOWER.

Fulfills Phase 08 Requirements:
- Scoped Activity Record Queryset Retrieval (get_accessible_activity_records)
- Server-side Object-level Access & Modification Authorization
- Multi-tier Organizational & Period Boundary Enforcement
- Candidate Selector Services for UI Form (Sites, Periods, Activities, Units)
- Audit-Ready Event Logging Integration with AuthAuditLog
"""

import logging
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Q

from apps.core.activity_services import (
    get_accessible_activity_masters,
    get_accessible_units,
    validate_activity_unit,
)
from apps.core.auth_services import log_auth_event
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
    UnitOfMeasure,
)
from apps.core.period_services import (
    can_user_enter_data,
    can_user_modify_data,
    get_accessible_reporting_periods,
)
from apps.core.scope_services import (
    get_accessible_companies,
    get_accessible_sites,
    get_accessible_subsidiaries,
    user_can_access_site,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. SCOPED QUERYSET RETRIEVAL
# -----------------------------------------------------------------------------

def get_accessible_activity_records(user):
    """
    Returns QuerySet of ActivityRecord records accessible to the user.

    Strictly enforces organizational boundaries:
    - SITE_MANAGER: Confined exclusively to activity records from explicitly assigned sites.
    - SUBSIDIARY_MANAGER: Confined to activity records from child sites under assigned subsidiaries/companies.
    - MEIL_OPERATOR / ESG_MANAGER / AUDITOR / Superuser: Confined to activity records under accessible enterprise companies.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return ActivityRecord.objects.none()

    base_qs = ActivityRecord.objects.select_related(
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
    )

    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        accessible_companies = get_accessible_companies(user)
        return base_qs.filter(site__project__subsidiary__company__in=accessible_companies).order_by(
            "-measurement_date", "-created_at"
        )

    if user.has_role(Role.Code.SUBSIDIARY_MANAGER):
        accessible_subs = get_accessible_subsidiaries(user)
        return base_qs.filter(site__project__subsidiary__in=accessible_subs).order_by(
            "-measurement_date", "-created_at"
        )

    if user.has_role(Role.Code.SITE_MANAGER):
        accessible_sites = get_accessible_sites(user)
        return base_qs.filter(site__in=accessible_sites).order_by(
            "-measurement_date", "-created_at"
        )

    return ActivityRecord.objects.none()


# -----------------------------------------------------------------------------
# 2. OBJECT-LEVEL AUTHORIZATION & VALIDATION HELPERS
# -----------------------------------------------------------------------------

def user_can_access_activity_record(user, record):
    """
    Evaluates whether a user has read access to a specific ActivityRecord.
    """
    if not user or not user.is_authenticated or not user.is_active or not record:
        return False

    return get_accessible_activity_records(user).filter(id=record.id).exists()


def user_can_create_activity_record(user, site=None):
    """
    Evaluates whether a user has authority to initiate an ActivityRecord.
    - Permitted roles: SITE_MANAGER, MEIL_OPERATOR, ESG_MANAGER
    - AUDITOR: Strictly prohibited (read-only assurance)
    - SUBSIDIARY_MANAGER: Read & review only; cannot create site records directly
    - If site provided: User must have access to that specific site and site must be active.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False

    if user.has_role(Role.Code.AUDITOR) and not (
        user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR)
    ):
        return False

    if user.has_role(Role.Code.SUBSIDIARY_MANAGER) and not (
        user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR) or user.has_role(Role.Code.SITE_MANAGER)
    ):
        return False

    has_allowed_role = (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.SITE_MANAGER)
        or user.has_role(Role.Code.ESG_MANAGER)
    )
    if not has_allowed_role:
        return False

    if site is not None:
        if site.status != OrganizationStatus.ACTIVE:
            return False
        return user_can_access_site(user, site)

    return True


def user_can_modify_activity_record(user, record):
    """
    Evaluates whether a user can modify/update an existing ActivityRecord.
    Enforces:
    1. Read access to the record
    2. Authority to create/mutate data
    3. Record status must be editable (DRAFT, READY, REJECTED)
    4. Reporting period must be OPEN (allows data modification)
    """
    if not user_can_access_activity_record(user, record):
        return False

    if not user_can_create_activity_record(user, site=record.site):
        return False

    # Check reporting period lifecycle
    if not can_user_modify_data(user, record.reporting_period):
        return False

    # Check record status
    if not record.is_editable_by_site_manager:
        return False

    return True


def user_can_delete_activity_record(user, record):
    """
    Evaluates whether a user can delete an ActivityRecord.
    Deletion is permitted ONLY for records in DRAFT state, by authorized managers.
    Once submitted or processed, records must follow governance review/audit.
    """
    if not user_can_access_activity_record(user, record):
        return False

    if not user_can_create_activity_record(user, site=record.site):
        return False

    if record.status != RecordStatus.DRAFT:
        return False

    if not can_user_modify_data(user, record.reporting_period):
        return False

    return True


# -----------------------------------------------------------------------------
# 3. CANDIDATE SELECTOR SERVICES FOR DATA ENTRY FORMS
# -----------------------------------------------------------------------------

def get_candidate_sites_for_data_entry(user):
    """
    Returns QuerySet of operational sites available to the user for data entry.
    Only ACTIVE sites assigned to the user are returned.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return Site.objects.none()

    return (
        get_accessible_sites(user)
        .filter(status=OrganizationStatus.ACTIVE)
        .select_related("project", "project__subsidiary", "project__subsidiary__company")
        .order_by("name")
    )


def get_candidate_periods_for_site(site, user):
    """
    Returns QuerySet of OPEN ReportingPeriod records matching the organizational scope of the given site.
    """
    if not site or not user:
        return ReportingPeriod.objects.none()

    if isinstance(site, int):
        site = Site.objects.filter(pk=site).select_related("project__subsidiary__company", "project__subsidiary").first()
        if not site:
            return ReportingPeriod.objects.none()

    site_company = site.project.subsidiary.company
    site_subsidiary = site.project.subsidiary

    return (
        get_accessible_reporting_periods(user)
        .filter(
            status=PeriodStatus.OPEN,
            company=site_company,
        )
        .filter(
            models.Q(subsidiary__isnull=True) | models.Q(subsidiary=site_subsidiary)
        )
        .order_by("-start_date", "code")
    )


def get_candidate_activities_for_data_entry(user):
    """
    Returns QuerySet of active ActivityMaster catalog items available for data logging.
    """
    return (
        get_accessible_activity_masters(user, include_inactive=False)
        .filter(status=MasterStatus.ACTIVE)
        .select_related("category", "base_unit")
        .order_by("category__display_order", "category__name", "name")
    )


def get_candidate_units_for_activity(activity):
    """
    Returns QuerySet of UnitOfMeasure models permissible for the given activity.
    Union of base_unit and allowed_units.
    """
    if not activity:
        return UnitOfMeasure.objects.none()

    if isinstance(activity, int):
        activity = ActivityMaster.objects.filter(pk=activity).first()
        if not activity:
            return UnitOfMeasure.objects.none()

    allowed_ids = list(activity.allowed_units.filter(status=MasterStatus.ACTIVE).values_list("id", flat=True))
    if activity.base_unit_id:
        allowed_ids.append(activity.base_unit_id)

    return UnitOfMeasure.objects.filter(id__in=set(allowed_ids)).filter(status=MasterStatus.ACTIVE).order_by("dimension", "name")


# -----------------------------------------------------------------------------
# 4. AUDIT EVENT LOGGING HELPER
# -----------------------------------------------------------------------------

def log_activity_record_event(event_type, record, user, request=None, details=""):
    """
    Dispatches an AuthAuditLog security and compliance event for ActivityRecord actions.
    """
    resource_id = f"ActivityRecord:{record.id} ({record.activity.code} @ {record.site.code})"
    log_auth_event(
        user=user,
        event_type=event_type,
        resource_accessed=resource_id,
        details=details or f"Activity record {event_type} for site {record.site.name}.",
        success=True,
        request=request,
    )
    logger.info("ActivityRecord [%s] event %s logged by user %s", record.id, event_type, user.username if user else "System")
