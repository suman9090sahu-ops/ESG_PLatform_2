"""
Activity Master Domain and ESG Catalog Governance Services for MEIL ESG CONTROL TOWER.

Fulfills Phase 06 Requirements:
- Scoped Activity Catalog Retrieval (get_accessible_activity_masters, get_accessible_activity_categories)
- Controlled Unit of Measure Retrieval (get_accessible_units)
- Object-level Authorization & Role Boundary Enforcement (user_can_manage_activity_master, user_can_view_activity_master)
- Safe Deactivation & Lifecycle Control preserving Historical Data Lineage
- Audit-Ready Logging integration with AuthAuditLog
- Unit Validation Preparation for downstream Data Entry and Scope 1/2/3 engines
"""

import logging
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models

from apps.core.auth_services import log_auth_event
from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    AuthAuditLog,
    MasterStatus,
    Role,
    UnitOfMeasure,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. SCOPED QUERYSET RETRIEVAL
# -----------------------------------------------------------------------------

def get_accessible_activity_categories(user, include_inactive=False):
    """
    Returns QuerySet of ActivityCategory records.
    - Master administrators (MEIL_OPERATOR, ESG_MANAGER, Superuser) can inspect all categories.
    - Operational roles (SITE_MANAGER, SUBSIDIARY_MANAGER) only see ACTIVE categories unless include_inactive is explicitly requested.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return ActivityCategory.objects.none()

    qs = ActivityCategory.objects.all().order_by("display_order", "name")

    if not include_inactive:
        if not (user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR) or user.has_role(Role.Code.ESG_MANAGER)):
            qs = qs.filter(status=MasterStatus.ACTIVE)

    return qs


def get_accessible_activity_masters(user, include_inactive=False):
    """
    Returns QuerySet of ActivityMaster records.
    Optimized with select_related on category and base_unit, and prefetch_related on allowed_units.
    - SITE_MANAGER / SUBSIDIARY_MANAGER: Confined to ACTIVE approved master activities by default.
    - MEIL_OPERATOR / ESG_MANAGER / AUDITOR: Can inspect all catalog entries including inactive.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return ActivityMaster.objects.none()

    qs = ActivityMaster.objects.select_related(
        "category",
        "base_unit",
        "created_by",
        "updated_by",
    ).prefetch_related("allowed_units").order_by("category__display_order", "category__name", "name")

    if not include_inactive:
        if not (
            user.is_superuser
            or user.has_role(Role.Code.MEIL_OPERATOR)
            or user.has_role(Role.Code.ESG_MANAGER)
            or user.has_role(Role.Code.AUDITOR)
        ):
            qs = qs.filter(status=MasterStatus.ACTIVE)

    return qs


def get_accessible_units(user, include_inactive=False):
    """
    Returns QuerySet of UnitOfMeasure records.
    """
    if not user or not user.is_authenticated or not user.is_active:
        return UnitOfMeasure.objects.none()

    qs = UnitOfMeasure.objects.all().order_by("dimension", "name")
    if not include_inactive:
        if not (user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR) or user.has_role(Role.Code.ESG_MANAGER)):
            qs = qs.filter(status=MasterStatus.ACTIVE)
    return qs


# -----------------------------------------------------------------------------
# 2. RBAC & PERMISSION EVALUATORS
# -----------------------------------------------------------------------------

def user_can_view_activity_master(user):
    """
    Evaluates whether a user has read access to the Activity Master catalog.
    Permitted for all authenticated platform personas:
    - SITE_MANAGER (to reference valid activity codes and units for data entry)
    - SUBSIDIARY_MANAGER (to review expected reporting streams)
    - ESG_MANAGER (to inspect corporate emission factor baselines)
    - AUDITOR (independent read-only inspection)
    - MEIL_OPERATOR (system oversight)
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False

    return (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
        or user.has_role(Role.Code.SUBSIDIARY_MANAGER)
        or user.has_role(Role.Code.SITE_MANAGER)
    )


def user_can_manage_activity_master(user):
    """
    Evaluates whether a user has authority to create, edit, or alter lifecycle of Activity Master.
    Centrally controlled:
    - Superuser: Allowed
    - MEIL_OPERATOR: Allowed
    - ESG_MANAGER: Allowed (corporate taxonomy governance)
    - SITE_MANAGER: Strictly DENIED (cannot invent arbitrary activities)
    - SUBSIDIARY_MANAGER: Strictly DENIED (view-only governance)
    - AUDITOR: Strictly DENIED (strictly read-only assurance)
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False

    return (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
    )


# -----------------------------------------------------------------------------
# 3. LIFECYCLE & MUTATION OPERATIONS
# -----------------------------------------------------------------------------

def safe_deactivate_activity_master(activity, user, request=None):
    """
    Safely transitions an ActivityMaster to INACTIVE without hard-deleting.
    Preserves historical operational activity records, calculation lineages, and audit logs.
    """
    if not user_can_manage_activity_master(user):
        raise PermissionDenied("You do not have permission to alter the lifecycle of Activity Master entries.")

    activity.status = MasterStatus.INACTIVE
    activity.is_active = False
    activity.updated_by = user
    activity.save(update_fields=["status", "is_active", "updated_by", "updated_at"])

    details = f"Activity '{activity.name}' ({activity.code}) deactivated by {user.username}."
    log_auth_event(
        user=user,
        event_type=AuthAuditLog.EventType.ACTIVITY_MASTER_DEACTIVATED,
        resource_accessed=f"ActivityMaster:{activity.id}:{activity.code}",
        details=details,
        success=True,
        request=request,
    )
    logger.info("ActivityMaster [%s] deactivated by user %s", activity.code, user.username)
    return activity


def safe_activate_activity_master(activity, user, request=None):
    """
    Activates a previously inactive ActivityMaster.
    """
    if not user_can_manage_activity_master(user):
        raise PermissionDenied("You do not have permission to alter the lifecycle of Activity Master entries.")

    activity.status = MasterStatus.ACTIVE
    activity.is_active = True
    activity.updated_by = user
    activity.save(update_fields=["status", "is_active", "updated_by", "updated_at"])

    details = f"Activity '{activity.name}' ({activity.code}) activated by {user.username}."
    log_auth_event(
        user=user,
        event_type=AuthAuditLog.EventType.ACTIVITY_MASTER_UPDATED,
        resource_accessed=f"ActivityMaster:{activity.id}:{activity.code}",
        details=details,
        success=True,
        request=request,
    )
    logger.info("ActivityMaster [%s] activated by user %s", activity.code, user.username)
    return activity


# -----------------------------------------------------------------------------
# 4. UNIT VALIDATION HELPER (Integration hook for Phase 07 / Phase 08)
# -----------------------------------------------------------------------------

def validate_activity_unit(activity, unit):
    """
    Validates whether a candidate UnitOfMeasure is permissible for an ActivityMaster.
    Acceptable if candidate unit is the activity's base_unit OR in its allowed_units.
    """
    if not activity or not unit:
        return False

    if activity.base_unit_id == unit.id:
        return True

    return activity.allowed_units.filter(id=unit.id).exists()
