"""
Organizational Scope and Queryset Scoping Services for MEIL ESG CONTROL TOWER.

Implements Section 16 & 17 of Phase 03:
- Reusable organizational-scope query layer
- Server-side object-level authorization helpers
- Queryset-based access filtering (preventing IDOR and data leakage)
- Role-specific organization mutation policies
- Safe deactivation & audit lineage hooks
"""

import logging
from django.db import models
from django.core.exceptions import PermissionDenied

from apps.core.models import (
    AuthAuditLog,
    Company,
    CompanyAssignment,
    OrganizationStatus,
    Project,
    ProjectAssignment,
    Role,
    Site,
    SiteAssignment,
    Subsidiary,
    SubsidiaryAssignment,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# QUERYSET SCOPING SERVICES
# -----------------------------------------------------------------------------

def get_accessible_companies(user):
    """
    Returns QuerySet of Company entities accessible to the user based on RBAC and assignments.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return Company.objects.none()

    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        return Company.objects.all().order_by("name")

    if user.has_role(Role.Code.SUBSIDIARY_MANAGER):
        assigned_cos = CompanyAssignment.objects.filter(user=user).values_list("company_id", flat=True)
        sub_cos = SubsidiaryAssignment.objects.filter(user=user).values_list("subsidiary__company_id", flat=True)
        return Company.objects.filter(models.Q(id__in=assigned_cos) | models.Q(id__in=sub_cos)).distinct().order_by("name")

    if user.has_role(Role.Code.SITE_MANAGER):
        site_cos = SiteAssignment.objects.filter(user=user).values_list(
            "site__project__subsidiary__company_id", flat=True
        )
        return Company.objects.filter(id__in=site_cos).distinct().order_by("name")

    # Project assignment scope fallback
    proj_cos = ProjectAssignment.objects.filter(user=user).values_list("project__subsidiary__company_id", flat=True)
    return Company.objects.filter(id__in=proj_cos).distinct().order_by("name")


def get_accessible_subsidiaries(user):
    """
    Returns QuerySet of Subsidiary entities accessible to the user.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return Subsidiary.objects.none()

    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        return Subsidiary.objects.all().select_related("company").order_by("name")

    if user.has_role(Role.Code.SUBSIDIARY_MANAGER):
        return (
            Subsidiary.objects.filter(
                models.Q(assigned_users__user=user)
                | models.Q(company__assigned_users__user=user)
            )
            .distinct()
            .select_related("company")
            .order_by("name")
        )

    if user.has_role(Role.Code.SITE_MANAGER):
        sub_ids = SiteAssignment.objects.filter(user=user).values_list(
            "site__project__subsidiary_id", flat=True
        )
        return Subsidiary.objects.filter(id__in=sub_ids).distinct().select_related("company").order_by("name")

    proj_sub_ids = ProjectAssignment.objects.filter(user=user).values_list("project__subsidiary_id", flat=True)
    return Subsidiary.objects.filter(id__in=proj_sub_ids).distinct().select_related("company").order_by("name")


def get_accessible_projects(user):
    """
    Returns QuerySet of Infrastructure Projects accessible to the user.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return Project.objects.none()

    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        return Project.objects.all().select_related("subsidiary", "subsidiary__company").order_by("name")

    if user.has_role(Role.Code.SUBSIDIARY_MANAGER):
        assigned_subs = SubsidiaryAssignment.objects.filter(user=user).values_list("subsidiary_id", flat=True)
        assigned_cos = CompanyAssignment.objects.filter(user=user).values_list("company_id", flat=True)
        return (
            Project.objects.filter(
                models.Q(subsidiary_id__in=assigned_subs)
                | models.Q(subsidiary__company_id__in=assigned_cos)
            )
            .distinct()
            .select_related("subsidiary", "subsidiary__company")
            .order_by("name")
        )

    if user.has_role(Role.Code.SITE_MANAGER):
        proj_ids = SiteAssignment.objects.filter(user=user).values_list("site__project_id", flat=True)
        return (
            Project.objects.filter(id__in=proj_ids)
            .distinct()
            .select_related("subsidiary", "subsidiary__company")
            .order_by("name")
        )

    return (
        Project.objects.filter(assigned_users__user=user)
        .distinct()
        .select_related("subsidiary", "subsidiary__company")
        .order_by("name")
    )


def get_accessible_sites(user):
    """
    Returns QuerySet of Operational Sites accessible to the user.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return Site.objects.none()

    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        return Site.objects.all().select_related("project", "project__subsidiary", "project__subsidiary__company").order_by("name")

    if user.has_role(Role.Code.SUBSIDIARY_MANAGER):
        assigned_subs = SubsidiaryAssignment.objects.filter(user=user).values_list("subsidiary_id", flat=True)
        assigned_cos = CompanyAssignment.objects.filter(user=user).values_list("company_id", flat=True)
        return (
            Site.objects.filter(
                models.Q(project__subsidiary_id__in=assigned_subs)
                | models.Q(project__subsidiary__company_id__in=assigned_cos)
            )
            .distinct()
            .select_related("project", "project__subsidiary", "project__subsidiary__company")
            .order_by("name")
        )

    if user.has_role(Role.Code.SITE_MANAGER):
        return (
            Site.objects.filter(assigned_users__user=user)
            .distinct()
            .select_related("project", "project__subsidiary", "project__subsidiary__company")
            .order_by("name")
        )

    return Site.objects.none()


# -----------------------------------------------------------------------------
# OBJECT-LEVEL AUTHORIZATION CHECKERS
# -----------------------------------------------------------------------------

def user_can_access_company(user, company):
    """
    Object-level access check for Company / Enterprise root.
    """
    if not user or not user.is_authenticated or not user.is_active or not company:
        return False

    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        return True

    return get_accessible_companies(user).filter(id=company.id).exists()


def user_can_access_subsidiary(user, subsidiary):
    """
    Object-level access check for a Subsidiary.
    """
    if not user or not user.is_authenticated or not user.is_active or not subsidiary:
        return False

    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        return True

    return get_accessible_subsidiaries(user).filter(id=subsidiary.id).exists()


def user_can_access_project(user, project):
    """
    Object-level access check for an Infrastructure Project.
    """
    if not user or not user.is_authenticated or not user.is_active or not project:
        return False

    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        return True

    return get_accessible_projects(user).filter(id=project.id).exists()


def user_can_access_site(user, site):
    """
    Object-level access check for an Operational Site.
    """
    if not user or not user.is_authenticated or not user.is_active or not site:
        return False

    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        return True

    return get_accessible_sites(user).filter(id=site.id).exists()


# -----------------------------------------------------------------------------
# MANAGEMENT / MUTATION AUTHORIZATION
# -----------------------------------------------------------------------------

def user_can_manage_hierarchy(user):
    """
    Check whether user has administrative rights to create/edit enterprise companies & subsidiaries.
    Restricted to MEIL_OPERATOR and Superusers.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False
    return user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR)


def user_can_manage_subsidiary(user, subsidiary=None):
    """
    Check whether user can edit or deactivate a subsidiary.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False
    return user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR)


def user_can_manage_project(user, project=None, subsidiary=None):
    """
    Check whether user can create, edit, or deactivate a project.
    - MEIL_OPERATOR / Superuser: Allowed across all projects.
    - SUBSIDIARY_MANAGER: Allowed only for projects within their assigned subsidiary.
    - ESG_MANAGER / AUDITOR / SITE_MANAGER: Denied.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False

    if user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR):
        return True

    if user.has_role(Role.Code.SUBSIDIARY_MANAGER):
        target_sub = subsidiary or (project.subsidiary if project else None)
        if target_sub:
            return user_can_access_subsidiary(user, target_sub)
        # Can access project creation workflow if user has assigned subsidiaries
        return get_accessible_subsidiaries(user).exists()

    return False


def user_can_manage_site(user, site=None, project=None):
    """
    Check whether user can create, edit, or deactivate an operational site.
    - MEIL_OPERATOR / Superuser: Allowed across all sites.
    - SUBSIDIARY_MANAGER: Allowed only for sites within their assigned subsidiary.
    - ESG_MANAGER / AUDITOR / SITE_MANAGER: Denied.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False

    if user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR):
        return True

    if user.has_role(Role.Code.SUBSIDIARY_MANAGER):
        target_proj = project or (site.project if site else None)
        if target_proj:
            return user_can_access_project(user, target_proj)
        # Can access site creation workflow if user has accessible projects
        return get_accessible_projects(user).exists()

    return False


# -----------------------------------------------------------------------------
# SAFE DELETION / DEACTIVATION POLICY HELPER
# -----------------------------------------------------------------------------

def safe_deactivate_entity(entity, user=None, request=None):
    """
    Implements Section 22: Safe Deactivation Policy.
    Sets status to INACTIVE and is_active to False.
    Records AuthAuditLog event.
    """
    entity_type = entity.__class__.__name__
    entity.status = OrganizationStatus.INACTIVE
    entity.is_active = False
    entity.save()

    # Log audit event
    from apps.core.auth_services import log_auth_event
    log_auth_event(
        AuthAuditLog.EventType.ORGANIZATION_DEACTIVATED,
        request=request,
        user=user,
        resource_accessed=f"{entity_type}:{entity.id} ({entity.code})",
        details=f"{entity_type} '{entity.name}' ({entity.code}) was archived/deactivated.",
        success=True,
    )
    return entity


# -----------------------------------------------------------------------------
# BACKWARD COMPATIBILITY ALIASES
# -----------------------------------------------------------------------------
get_user_accessible_sites = get_accessible_sites
get_user_accessible_subsidiaries = get_accessible_subsidiaries
get_user_accessible_companies = get_accessible_companies
get_user_accessible_projects = get_accessible_projects
