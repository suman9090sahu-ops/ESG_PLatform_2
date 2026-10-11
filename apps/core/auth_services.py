"""
Authentication & Authorization Services for MEIL ESG CONTROL TOWER.

Includes:
1. Object-level access verification (user_can_access_site, user_can_access_subsidiary, etc.)
2. Queryset filtering by organizational assignment
3. RBAC decorators & Class-Based View mixins
4. Safe post-login redirection resolution (preventing open redirects)
5. Audit event logging helper
6. Role-aware dynamic sidebar navigation builder
"""

from functools import wraps
import logging
from django.conf import settings
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from django.db import models
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from apps.core.models import (
    AuthAuditLog,
    Company,
    CompanyAssignment,
    Project,
    ProjectAssignment,
    Role,
    Site,
    SiteAssignment,
    Subsidiary,
    SubsidiaryAssignment,
    ValidationStatus,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# CLIENT IP & AUDIT LOGGING HELPER
# -----------------------------------------------------------------------------

def get_client_ip(request):
    """Safely retrieves client IP address from HTTP headers."""
    if not request:
        return None
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def log_auth_event(
    event_type,
    request=None,
    user=None,
    username_attempted="",
    details="",
    resource_accessed="",
    success=True,
):
    """
    Creates an AuthAuditLog entry for security tracking and BRSR governance.
    """
    try:
        ip_addr = get_client_ip(request) if request else None
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:500] if request else ""
        if request and not resource_accessed:
            resource_accessed = request.path[:255]

        if not user and request and hasattr(request, "user") and request.user.is_authenticated:
            user = request.user

        if not username_attempted and user:
            username_attempted = user.username

        return AuthAuditLog.objects.create(
            user=user if (user and user.is_authenticated) else None,
            username_attempted=username_attempted[:150],
            event_type=event_type,
            ip_address=ip_addr,
            user_agent=user_agent,
            resource_accessed=resource_accessed,
            details=details,
            success=success,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to write AuthAuditLog entry: {exc}")
        return None


# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# OBJECT-LEVEL AUTHORIZATION & QUERYSET SCOPING SERVICES
# (Imported from unified scope_services layer)
# -----------------------------------------------------------------------------
from apps.core.scope_services import (  # noqa: E402
    get_accessible_companies,
    get_accessible_projects,
    get_accessible_sites,
    get_accessible_subsidiaries,
    get_user_accessible_companies,
    get_user_accessible_projects,
    get_user_accessible_sites,
    get_user_accessible_subsidiaries,
    safe_deactivate_entity,
    user_can_access_company,
    user_can_access_project,
    user_can_access_site,
    user_can_access_subsidiary,
    user_can_manage_hierarchy,
    user_can_manage_project,
    user_can_manage_site,
    user_can_manage_subsidiary,
)


# -----------------------------------------------------------------------------
# RBAC DECORATORS & MIXINS
# -----------------------------------------------------------------------------

def role_required(*allowed_roles):
    """
    View decorator verifying that the user is authenticated and holds at least
    one of the specified allowed_roles (or is superuser).
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(f"{reverse('core:login')}?next={request.path}")

            if not request.user.is_active:
                log_auth_event(
                    AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
                    request=request,
                    user=request.user,
                    details="Inactive user attempted to access protected route.",
                    success=False,
                )
                raise PermissionDenied("User account is inactive.")

            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            # Flatten allowed roles if passed as a single iterable (list/tuple/set)
            roles_set = set()
            for r in allowed_roles:
                if isinstance(r, (list, tuple, set)):
                    roles_set.update(r)
                else:
                    roles_set.add(r)

            user_roles = set(request.user.get_assigned_roles().values_list("code", flat=True))
            if not any(role in user_roles for role in roles_set):
                log_auth_event(
                    AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
                    request=request,
                    user=request.user,
                    details=f"Required roles {list(roles_set)}, but user holds {list(user_roles)}.",
                    success=False,
                )
                raise PermissionDenied("You do not have the required role to access this resource.")

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


class RoleRequiredMixin(AccessMixin):
    """
    CBV mixin verifying that user holds at least one of the specified allowed_roles.
    """

    allowed_roles = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if not request.user.is_active:
            raise PermissionDenied("User account is inactive.")

        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)

        user_roles = set(request.user.get_assigned_roles().values_list("code", flat=True))
        if not any(role in user_roles for role in self.allowed_roles):
            log_auth_event(
                AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
                request=request,
                user=request.user,
                details=f"CBV denied: Required {self.allowed_roles}, has {list(user_roles)}.",
                success=False,
            )
            raise PermissionDenied("You do not have permission to access this resource.")

        return super().dispatch(request, *args, **kwargs)


# -----------------------------------------------------------------------------
# SAFE LOGIN REDIRECTION
# -----------------------------------------------------------------------------

def get_post_login_redirect_url(request, user):
    """
    Determines post-login destination URL.
    1. Validates 'next' parameter if present to prevent Open Redirects.
    2. Routes deterministically by primary role:
       - SITE_MANAGER -> /site-manager/dashboard/ (My Assigned Site workspace)
       - SUBSIDIARY_MANAGER -> /subsidiary-manager/dashboard/
       - ESG_MANAGER -> /esg-manager/dashboard/
       - AUDITOR -> /auditor/dashboard/
       - MEIL_OPERATOR -> /meil-operator/dashboard/
       - Fallback -> /
    """
    primary_role = user.get_primary_role() if hasattr(user, "get_primary_role") else None
    next_url = request.POST.get("next") or request.GET.get("next")

    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        # Prevent Site Manager from being redirected to generic executive dashboard
        if primary_role == Role.Code.SITE_MANAGER:
            generic_dashboard_urls = [
                reverse("core:control_tower_dashboard"),
                reverse("core:control_tower_dashboard_alias"),
                reverse("core:control_tower"),
                "/dashboard/",
                "/dashboard/control-tower/",
                "/control-tower/",
            ]
            if any(next_url == g_url or next_url.startswith(g_url + "?") for g_url in generic_dashboard_urls):
                return reverse("core:site_manager_dashboard")
        return next_url

    role_dashboard_map = {
        Role.Code.SITE_MANAGER: reverse("core:site_manager_dashboard"),
        Role.Code.SUBSIDIARY_MANAGER: reverse("core:subsidiary_manager_dashboard"),
        Role.Code.ESG_MANAGER: reverse("core:esg_manager_dashboard"),
        Role.Code.AUDITOR: reverse("core:auditor_dashboard"),
        Role.Code.MEIL_OPERATOR: reverse("core:meil_operator_dashboard"),
    }

    if primary_role in role_dashboard_map:
        return role_dashboard_map[primary_role]

    return reverse("core:control_tower_dashboard")


# -----------------------------------------------------------------------------
# ROLE-AWARE SIDEBAR NAVIGATION BUILDER
# -----------------------------------------------------------------------------

def get_role_sidebar_menu(user):
    """
    Builds context-injected `sidebar_menu` tailored to the user's primary functional role.
    """
    if not user or not user.is_authenticated:
        return None

    primary_role = user.get_primary_role()

    if primary_role == Role.Code.SITE_MANAGER:
        return [
            {
                "title": "Site Operations",
                "items": [
                    {
                        "nav_id": "my_assigned_site",
                        "label": "My Assigned Site",
                        "url": reverse("core:site_manager_dashboard"),
                        "icon": "icon-location-pin text-success",
                    },
                    {
                        "nav_id": "data_entry",
                        "label": "ESG Data Entry",
                        "url": reverse("core:activity_record_create"),
                        "icon": "icon-pencil text-warning",
                    },
                    {
                        "nav_id": "activity_records",
                        "label": "My Activity Data",
                        "url": reverse("core:activity_record_list"),
                        "icon": "icon-docs text-primary",
                    },
                    {
                        "nav_id": "evidence",
                        "label": "Evidence",
                        "url": reverse("core:evidence_list"),
                        "icon": "icon-paper-clip text-info",
                    },
                    {
                        "nav_id": "validation_issues",
                        "label": "Validation Issues",
                        "url": reverse("core:activity_record_list") + f"?validation_status={ValidationStatus.INVALID}",
                        "icon": "icon-check text-danger",
                    },
                    {
                        "nav_id": "submissions",
                        "label": "Submissions",
                        "url": reverse("core:submission_list"),
                        "icon": "icon-paper-plane text-success",
                    },
                    {
                        "nav_id": "corrections",
                        "label": "Corrections",
                        "url": reverse("core:correction_inbox"),
                        "icon": "icon-action-undo text-danger",
                    },
                ],
            },
        ]

    if primary_role == Role.Code.SUBSIDIARY_MANAGER:
        return [
            {
                "title": "Subsidiary Review",
                "items": [
                    {
                        "nav_id": "sub_dashboard",
                        "label": "Subsidiary Dashboard",
                        "url": reverse("core:subsidiary_manager_dashboard"),
                        "icon": "icon-screen-desktop text-primary",
                    },
                    {
                        "nav_id": "sub_list",
                        "label": "Assigned Subsidiaries",
                        "url": reverse("core:org_subsidiary_list"),
                        "icon": "icon-briefcase text-info",
                    },
                    {
                        "nav_id": "projects",
                        "label": "Infrastructure Projects",
                        "url": reverse("core:org_project_list"),
                        "icon": "icon-layers text-warning",
                    },
                    {
                        "nav_id": "sites",
                        "label": "Operational Sites",
                        "url": reverse("core:org_site_list"),
                        "icon": "icon-location-pin text-success",
                    },
                    {
                        "nav_id": "org_tree",
                        "label": "Hierarchy Explorer",
                        "url": reverse("core:org_overview"),
                        "icon": "icon-organization text-primary",
                    },
                    {
                        "nav_id": "reporting_periods",
                        "label": "Reporting Periods",
                        "url": reverse("core:period_list"),
                        "icon": "icon-calendar text-info",
                    },
                    {
                        "nav_id": "activity_master",
                        "label": "Activity Catalog",
                        "url": reverse("core:activity_list"),
                        "icon": "icon-list text-success",
                    },
                    {
                        "nav_id": "submission_inbox",
                        "label": "Submission Inbox",
                        "url": reverse("core:subsidiary_submission_inbox"),
                        "icon": "icon-envelope-letter text-warning",
                        "badge": {"text": "Review", "class": "badge-warning"},
                    },
                    {
                        "nav_id": "data_review",
                        "label": "Telemetry Review",
                        "url": reverse("core:subsidiary_submission_inbox"),
                        "icon": "icon-magnifier text-success",
                    },
                    {
                        "nav_id": "anomalies",
                        "label": "Anomaly Desk",
                        "url": reverse("core:anomaly_list"),
                        "icon": "icon-flag text-danger",
                    },
                    {
                        "nav_id": "escalations",
                        "label": "Escalation Hub",
                        "url": reverse("core:subsidiary_submission_inbox") + "?status=ESCALATED",
                        "icon": "icon-energy text-danger",
                    },
                    {
                        "nav_id": "procurement_inbox",
                        "label": "Procurement Review",
                        "url": reverse("core:procurement_review_inbox"),
                        "icon": "icon-basket-loaded text-warning",
                    },
                    {
                        "nav_id": "transport_inbox",
                        "label": "Transport Review",
                        "url": reverse("core:transport_review_inbox"),
                        "icon": "icon-cursor text-warning",
                    },
                    {
                        "nav_id": "scope3_inventory",
                        "label": "Scope 3 Inventory",
                        "url": reverse("core:scope3_inventory"),
                        "icon": "icon-pie-chart text-success",
                    },
                    {
                        "nav_id": "suppliers",
                        "label": "Supplier Directory",
                        "url": reverse("core:supplier_list"),
                        "icon": "icon-people text-info",
                    },
                    {
                        "nav_id": "carriers",
                        "label": "Carrier Directory",
                        "url": reverse("core:carrier_list"),
                        "icon": "icon-globe text-info",
                    },
                ],
            },
            {
                "title": "System Tools",
                "items": [
                    {
                        "nav_id": "health",
                        "label": "Health Telemetry",
                        "url": reverse("core:health_check"),
                        "icon": "icon-pulse text-danger",
                    },
                ],
            },
        ]

    if primary_role == Role.Code.ESG_MANAGER:
        return [
            {
                "title": "Corporate ESG",
                "items": [
                    {
                        "nav_id": "esg_dashboard",
                        "label": "Governance Dashboard",
                        "url": reverse("core:esg_manager_dashboard"),
                        "icon": "icon-screen-desktop text-success",
                    },
                    {
                        "nav_id": "org_entities",
                        "label": "Enterprise Hierarchy",
                        "url": reverse("core:org_overview"),
                        "icon": "icon-organization text-info",
                    },
                    {
                        "nav_id": "projects",
                        "label": "Infrastructure Projects",
                        "url": reverse("core:org_project_list"),
                        "icon": "icon-layers text-warning",
                    },
                    {
                        "nav_id": "sites",
                        "label": "Operational Sites",
                        "url": reverse("core:org_site_list"),
                        "icon": "icon-location-pin text-success",
                    },
                    {
                        "nav_id": "reporting_periods",
                        "label": "Reporting Periods",
                        "url": reverse("core:period_list"),
                        "icon": "icon-calendar text-info",
                    },
                    {
                        "nav_id": "activity_master",
                        "label": "Activity Master",
                        "url": reverse("core:activity_list"),
                        "icon": "icon-list text-success",
                    },
                    {
                        "nav_id": "validation_rules",
                        "label": "Validation Rules",
                        "url": reverse("core:validation_rule_list"),
                        "icon": "icon-check text-warning",
                    },
                    {
                        "nav_id": "emission_factors",
                        "label": "Emission Factors",
                        "url": reverse("core:emission_factor_list"),
                        "icon": "icon-chemistry text-info",
                    },
                    {
                        "nav_id": "calculation_desk",
                        "label": "Calculation Desk",
                        "url": reverse("core:calculation_desk"),
                        "icon": "icon-calculator text-warning",
                    },
                    {
                        "nav_id": "consolidation",
                        "label": "Consolidation Engine",
                        "url": reverse("core:reports_overview"),
                        "icon": "icon-chart text-primary",
                    },
                    {
                        "nav_id": "ghg_accounting",
                        "label": "Scope 1, 2, 3 GHG",
                        "url": reverse("core:reports_overview") + "?scope=SCOPE_1",
                        "icon": "icon-energy text-info",
                    },
                    {
                        "nav_id": "scope3_inventory",
                        "label": "Scope 3 Inventory",
                        "url": reverse("core:scope3_inventory"),
                        "icon": "icon-pie-chart text-success",
                    },
                    {
                        "nav_id": "verified_submissions",
                        "label": "Verified Submissions",
                        "url": reverse("core:submission_list") + "?status=VERIFIED",
                        "icon": "icon-badge text-success",
                    },
                    {
                        "nav_id": "anomalies",
                        "label": "Anomaly Desk",
                        "url": reverse("core:anomaly_list"),
                        "icon": "icon-flag text-danger",
                    },
                    {
                        "nav_id": "brsr_finalization",
                        "label": "BRSR Finalization",
                        "url": reverse("core:reports_overview"),
                        "icon": "icon-doc text-success",
                    },
                    {
                        "nav_id": "procurement",
                        "label": "Procurement Ledger",
                        "url": reverse("core:procurement_list"),
                        "icon": "icon-basket text-warning",
                    },
                    {
                        "nav_id": "suppliers",
                        "label": "Supplier Directory",
                        "url": reverse("core:supplier_list"),
                        "icon": "icon-people text-info",
                    },
                    {
                        "nav_id": "transport",
                        "label": "Transport Ledger",
                        "url": reverse("core:transport_list"),
                        "icon": "icon-cursor text-info",
                    },
                    {
                        "nav_id": "carriers",
                        "label": "Carrier Directory",
                        "url": reverse("core:carrier_list"),
                        "icon": "icon-globe text-info",
                    },
                ],
            },
            {
                "title": "System Tools",
                "items": [
                    {
                        "nav_id": "ui_preview",
                        "label": "Design System",
                        "url": reverse("core:ui_preview"),
                        "icon": "icon-layers text-primary",
                    },
                    {
                        "nav_id": "health",
                        "label": "Health Telemetry",
                        "url": reverse("core:health_check"),
                        "icon": "icon-pulse text-danger",
                    },
                ],
            },
        ]

    if primary_role == Role.Code.AUDITOR:
        return [
            {
                "title": "Assurance & Audit",
                "items": [
                    {
                        "nav_id": "auditor_dashboard",
                        "label": "Auditor Dashboard",
                        "url": reverse("core:auditor_dashboard"),
                        "icon": "icon-screen-desktop text-warning",
                    },
                    {
                        "nav_id": "governed_reports",
                        "label": "Governed Reports",
                        "url": reverse("core:reports_overview"),
                        "icon": "icon-doc text-primary",
                    },
                    {
                        "nav_id": "calculation_lineage",
                        "label": "Calculation Lineage",
                        "url": reverse("core:trace_selector"),
                        "icon": "icon-directions text-info",
                    },
                    {
                        "nav_id": "scope3_inventory",
                        "label": "Scope 3 Inventory",
                        "url": reverse("core:scope3_inventory"),
                        "icon": "icon-pie-chart text-warning",
                    },
                    {
                        "nav_id": "verified_submissions",
                        "label": "Verified Submissions",
                        "url": reverse("core:submission_list") + "?status=VERIFIED",
                        "icon": "icon-badge text-success",
                    },
                    {
                        "nav_id": "evidence_trace",
                        "label": "Evidence Traceability",
                        "url": reverse("core:evidence_list"),
                        "icon": "icon-magnifier text-success",
                    },
                    {
                        "nav_id": "validation_rules",
                        "label": "Validation Rules",
                        "url": reverse("core:validation_rule_list"),
                        "icon": "icon-check text-info",
                    },
                    {
                        "nav_id": "audit_findings",
                        "label": "Audit Findings",
                        "url": reverse("core:anomaly_list"),
                        "icon": "icon-notebook text-danger",
                    },
                    {
                        "nav_id": "org_scope",
                        "label": "Governed Entities",
                        "url": reverse("core:org_overview"),
                        "icon": "icon-organization text-primary",
                    },
                    {
                        "nav_id": "projects",
                        "label": "Governed Projects",
                        "url": reverse("core:org_project_list"),
                        "icon": "icon-layers text-warning",
                    },
                    {
                        "nav_id": "sites",
                        "label": "Operational Sites",
                        "url": reverse("core:org_site_list"),
                        "icon": "icon-location-pin text-success",
                    },
                    {
                        "nav_id": "reporting_periods",
                        "label": "Reporting Periods",
                        "url": reverse("core:period_list"),
                        "icon": "icon-calendar text-warning",
                    },
                    {
                        "nav_id": "activity_master",
                        "label": "Activity Master",
                        "url": reverse("core:activity_list"),
                        "icon": "icon-list text-success",
                    },
                    {
                        "nav_id": "procurement",
                        "label": "Procurement Ledger",
                        "url": reverse("core:procurement_list"),
                        "icon": "icon-basket text-warning",
                    },
                    {
                        "nav_id": "suppliers",
                        "label": "Supplier Directory",
                        "url": reverse("core:supplier_list"),
                        "icon": "icon-people text-info",
                    },
                    {
                        "nav_id": "transport",
                        "label": "Transport Trace",
                        "url": reverse("core:transport_list"),
                        "icon": "icon-cursor text-info",
                    },
                    {
                        "nav_id": "carriers",
                        "label": "Carrier Directory",
                        "url": reverse("core:carrier_list"),
                        "icon": "icon-globe text-info",
                    },
                ],
            },
            {
                "title": "System Tools",
                "items": [
                    {
                        "nav_id": "health",
                        "label": "Health Telemetry",
                        "url": reverse("core:health_check"),
                        "icon": "icon-pulse text-danger",
                    },
                ],
            },
        ]

    if primary_role == Role.Code.MEIL_OPERATOR:
        return [
            {
                "title": "Operations Command",
                "items": [
                    {
                        "nav_id": "operator_dashboard",
                        "label": "Operator Dashboard",
                        "url": reverse("core:meil_operator_dashboard"),
                        "icon": "icon-screen-desktop text-danger",
                    },
                    {
                        "nav_id": "entities",
                        "label": "Organization Entities",
                        "url": reverse("core:org_overview"),
                        "icon": "icon-organization text-info",
                    },
                    {
                        "nav_id": "projects",
                        "label": "Infrastructure Projects",
                        "url": reverse("core:org_project_list"),
                        "icon": "icon-layers text-warning",
                    },
                    {
                        "nav_id": "sites",
                        "label": "Operational Sites",
                        "url": reverse("core:org_site_list"),
                        "icon": "icon-location-pin text-success",
                    },
                    {
                        "nav_id": "reporting_periods",
                        "label": "Reporting Periods",
                        "url": reverse("core:period_list"),
                        "icon": "icon-calendar text-success",
                    },
                    {
                        "nav_id": "activity_master",
                        "label": "Activity Master",
                        "url": reverse("core:activity_list"),
                        "icon": "icon-list text-success",
                    },
                    {
                        "nav_id": "scope3_inventory",
                        "label": "Scope 3 Inventory",
                        "url": reverse("core:scope3_inventory"),
                        "icon": "icon-pie-chart text-success",
                    },
                    {
                        "nav_id": "evidence",
                        "label": "Evidence Repository",
                        "url": reverse("core:evidence_list"),
                        "icon": "icon-docs text-info",
                    },
                    {
                        "nav_id": "validation_rules",
                        "label": "Validation Rules",
                        "url": reverse("core:validation_rule_list"),
                        "icon": "icon-check text-warning",
                    },
                    {
                        "nav_id": "telemetry_sync",
                        "label": "Telemetry Pipelines",
                        "url": "#",
                        "icon": "icon-feed text-warning",
                    },
                    {
                        "nav_id": "procurement",
                        "label": "Procurement Ledger",
                        "url": reverse("core:procurement_list"),
                        "icon": "icon-basket text-warning",
                    },
                    {
                        "nav_id": "suppliers",
                        "label": "Supplier Directory",
                        "url": reverse("core:supplier_list"),
                        "icon": "icon-people text-info",
                    },
                    {
                        "nav_id": "transport",
                        "label": "Transport Ledger",
                        "url": reverse("core:transport_list"),
                        "icon": "icon-cursor text-info",
                    },
                    {
                        "nav_id": "carriers",
                        "label": "Carriers & Fleet",
                        "url": reverse("core:carrier_list"),
                        "icon": "icon-globe text-primary",
                    },
                    {
                        "nav_id": "audit_events",
                        "label": "Security Audit Log",
                        "url": reverse("admin:core_authauditlog_changelist"),
                        "icon": "icon-shield text-danger",
                    },
                ],
            },

            {
                "title": "System Tools",
                "items": [
                    {
                        "nav_id": "health",
                        "label": "Health Telemetry",
                        "url": reverse("core:health_check"),
                        "icon": "icon-pulse text-danger",
                    },
                    {
                        "nav_id": "admin",
                        "label": "Django Admin",
                        "url": reverse("admin:index"),
                        "icon": "icon-settings text-secondary",
                    },
                ],
            },
        ]

    # Return None so sidebar renders default overview categories
    return None
