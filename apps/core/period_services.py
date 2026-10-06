"""
Reporting Period Domain and Temporal Governance Services for MEIL ESG CONTROL TOWER.

Fulfills Phase 04 Requirements:
- Scoped Queryset Retrieval (get_accessible_reporting_periods)
- Object-level Access and Lifecycle Authorization (user_can_access_reporting_period, user_can_manage_reporting_period)
- Controlled Lifecycle State Transitions with Auditing (transition_period_status)
- Operational ESG Data Entry and Modification Boundary Guards (can_user_enter_data, can_user_modify_data)
"""

import logging
from datetime import date
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import (
    AuthAuditLog,
    Company,
    PeriodStatus,
    ReportingPeriod,
    Role,
    Subsidiary,
)
from apps.core.scope_services import (
    get_accessible_companies,
    get_accessible_subsidiaries,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. SCOPED QUERYSET RETRIEVAL
# -----------------------------------------------------------------------------

def get_accessible_reporting_periods(user):
    """
    Returns QuerySet of ReportingPeriod records accessible to the user based on RBAC and organizational scope.

    - MEIL_OPERATOR / Superuser / ESG_MANAGER / AUDITOR:
      Has broad visibility across all periods belonging to their accessible companies.
    - SUBSIDIARY_MANAGER:
      Visible for assigned subsidiaries plus enterprise-level (null subsidiary) periods for their assigned companies.
    - SITE_MANAGER:
      Visible for periods matching their assigned site's company and subsidiary (or enterprise-wide).
    """
    if not user or not user.is_authenticated or not user.is_active:
        return ReportingPeriod.objects.none()

    base_qs = ReportingPeriod.objects.select_related("company", "subsidiary", "created_by", "updated_by")

    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        accessible_companies = get_accessible_companies(user)
        return base_qs.filter(company__in=accessible_companies).order_by("-start_date", "code")

    # Scoped for subsidiary and site managers
    accessible_companies = get_accessible_companies(user)
    accessible_subsidiaries = get_accessible_subsidiaries(user)

    return (
        base_qs.filter(
            company__in=accessible_companies,
        )
        .filter(
            models.Q(subsidiary__isnull=True)
            | models.Q(subsidiary__in=accessible_subsidiaries)
        )
        .distinct()
        .order_by("-start_date", "code")
    )


def get_current_reporting_period(company=None, subsidiary=None, as_of_date=None):
    """
    Retrieves the authoritative current OPEN reporting period for a given company/subsidiary scope.
    Defaults to current date if as_of_date is not provided.
    """
    check_date = as_of_date or timezone.now().date()
    qs = ReportingPeriod.objects.filter(
        status=PeriodStatus.OPEN,
        start_date__lte=check_date,
        end_date__gte=check_date,
    )

    if company:
        qs = qs.filter(company=company)

    if subsidiary:
        # Match specific subsidiary period or fallback to enterprise company-wide period
        sub_period = qs.filter(subsidiary=subsidiary).first()
        if sub_period:
            return sub_period
        return qs.filter(subsidiary__isnull=True).first()

    return qs.filter(subsidiary__isnull=True).first() or qs.first()


# -----------------------------------------------------------------------------
# 2. OBJECT-LEVEL AUTHORIZATION HELPERS
# -----------------------------------------------------------------------------

def user_can_access_reporting_period(user, period):
    """
    Server-side object-level access verification.
    Prevents IDOR and horizontal privilege escalation.
    """
    if not user or not user.is_authenticated or not user.is_active or not period:
        return False

    if (
        user.is_superuser
        or user.has_role(Role.Code.MEIL_OPERATOR)
        or user.has_role(Role.Code.ESG_MANAGER)
        or user.has_role(Role.Code.AUDITOR)
    ):
        return True

    return get_accessible_reporting_periods(user).filter(id=period.id).exists()


def user_can_manage_reporting_period(user, period=None, company=None):
    """
    Checks whether user has administrative authority to create or edit reporting period metadata.
    - MEIL_OPERATOR / Superuser: Full management across all periods.
    - ESG_MANAGER: Permitted for periods within their accessible companies.
    - SUBSIDIARY_MANAGER: Denied period creation/metadata modification.
    - SITE_MANAGER: Denied.
    - AUDITOR: Denied (Strictly read-only).
    """
    if not user or not user.is_authenticated or not user.is_active:
        return False

    if user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR):
        return True

    if user.has_role(Role.Code.ESG_MANAGER):
        target_company = company or (period.company if period else None)
        if target_company:
            return get_accessible_companies(user).filter(id=target_company.id).exists()
        return get_accessible_companies(user).exists()

    return False


def user_can_manage_period_lifecycle(user, period):
    """
    Checks whether user is authorized to perform status lifecycle transitions
    (e.g., Open, Close, Lock, Finalize).
    - MEIL_OPERATOR / Superuser: Permitted.
    - ESG_MANAGER: Permitted within their governed company scope.
    - AUDITOR, SUBSIDIARY_MANAGER, SITE_MANAGER: Denied.
    """
    return user_can_manage_reporting_period(user, period=period)


# -----------------------------------------------------------------------------
# 3. CONTROLLED LIFECYCLE TRANSITIONS & AUDIT LOGGING
# -----------------------------------------------------------------------------

def validate_status_transition(current_status, target_status):
    """
    Validates state machine transitions.
    Allowed transitions:
    - DRAFT -> OPEN
    - OPEN -> CLOSED
    - CLOSED -> OPEN (Reopening)
    - CLOSED -> LOCKED
    - LOCKED -> CLOSED (Unlocking)
    - LOCKED -> FINALIZED
    - FINALIZED -> None (Terminal immutable state)
    """
    allowed = ReportingPeriod.ALLOWED_TRANSITIONS.get(current_status, [])
    if target_status not in allowed:
        raise ValidationError(
            f"Invalid status transition from '{current_status}' to '{target_status}'. "
            f"Allowed next states: {', '.join(allowed) if allowed else 'None (Terminal state)'}."
        )


def transition_period_status(period, target_status, user=None, reason=None, request=None):
    """
    Executes a controlled, auditable status transition for a reporting period.
    Enforces server-side authorization, state machine rules, and audit logging.
    """
    from apps.core.auth_services import log_auth_event

    if user and not user_can_manage_period_lifecycle(user, period):
        if request:
            log_auth_event(
                AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
                request=request,
                user=user,
                resource_accessed=f"ReportingPeriod:{period.id} ({period.code})",
                details=f"Unauthorized lifecycle transition attempt from '{period.status}' to '{target_status}'.",
                success=False,
            )
        raise PermissionDenied("You are not authorized to alter the lifecycle status of this reporting period.")

    old_status = period.status
    validate_status_transition(old_status, target_status)

    period.status = target_status
    if user:
        period.updated_by = user
    period.save(update_fields=["status", "updated_by", "updated_at"])

    # Log audit event
    details = f"Reporting period '{period.name}' ({period.code}) transitioned from {old_status} to {target_status}."
    if reason:
        details += f" Reason / Notes: {reason}"

    log_auth_event(
        AuthAuditLog.EventType.PERIOD_STATUS_CHANGED,
        request=request,
        user=user,
        resource_accessed=f"ReportingPeriod:{period.id} ({period.code})",
        details=details,
        success=True,
    )
    return period


# -----------------------------------------------------------------------------
# 4. LIFECYCLE QUERY & DATA PROTECTION HELPERS
# -----------------------------------------------------------------------------

def is_period_open(period):
    """True if period is in OPEN status."""
    return bool(period and period.status == PeriodStatus.OPEN)


def is_period_closed(period):
    """True if period is in CLOSED status."""
    return bool(period and period.status == PeriodStatus.CLOSED)


def is_period_locked(period):
    """True if period is in LOCKED or FINALIZED status."""
    return bool(period and period.status in [PeriodStatus.LOCKED, PeriodStatus.FINALIZED])


def is_period_finalized(period):
    """True if period is in FINALIZED status."""
    return bool(period and period.status == PeriodStatus.FINALIZED)


def can_user_enter_data(user, period):
    """
    Operational data collection guard.
    Returns True ONLY if:
    1. User is authenticated and active
    2. User has access to this reporting period
    3. User has operational role (SITE_MANAGER, MEIL_OPERATOR, ESG_MANAGER) — AUDITOR is strictly excluded
    4. Period status is currently OPEN
    """
    if not user or not user.is_authenticated or not user.is_active or not period:
        return False

    if user.has_role(Role.Code.AUDITOR) and not (
        user.is_superuser or user.has_role(Role.Code.MEIL_OPERATOR)
    ):
        return False

    if not is_period_open(period):
        return False

    return user_can_access_reporting_period(user, period)


def can_user_modify_data(user, period):
    """
    Operational data modification guard.
    Closed, locked, or finalized periods strictly prohibit data mutation.
    """
    return can_user_enter_data(user, period)
