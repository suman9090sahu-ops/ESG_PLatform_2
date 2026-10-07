"""
Activity Master Views for MEIL ESG CONTROL TOWER.

Fulfills Phase 06 Requirements:
- Scoped Activity Catalog Listing with Status, Category, and Scope Classification Filtering
- Activity Detail View with Reference Guidance, Unit Specs, Evidence Guidelines, and Lineage Hooks
- Scoped Create and Edit Forms with Server-Side Authorization (MEIL_OPERATOR, ESG_MANAGER)
- Controlled Safe Deactivation preserving Historical Integrity
- Category and Unit Management Endpoints
- Strict IDOR Defense and Object-Level Access Enforcement
"""

import logging
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.core.activity_forms import (
    ActivityCategoryForm,
    ActivityMasterForm,
    UnitOfMeasureForm,
)
from apps.core.activity_services import (
    get_accessible_activity_categories,
    get_accessible_activity_masters,
    get_accessible_units,
    safe_activate_activity_master,
    safe_deactivate_activity_master,
    user_can_manage_activity_master,
    user_can_view_activity_master,
)
from apps.core.auth_services import log_auth_event
from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    AuthAuditLog,
    MasterStatus,
    Role,
    ScopeClassification,
    UnitOfMeasure,
)

logger = logging.getLogger("apps.core")


# -----------------------------------------------------------------------------
# 1. ACTIVITY MASTER CATALOG LIST VIEW
# -----------------------------------------------------------------------------

@login_required
def activity_list_view(request):
    """
    Catalog of all approved ESG activities.
    Supports filtering by category, scope classification, and lifecycle status.
    """
    user = request.user
    if not user_can_view_activity_master(user):
        log_auth_event(
            user=user,
            event_type=AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            resource_accessed="/activity-master/",
            details="Unauthorized attempt to access Activity Master catalog.",
            success=False,
            request=request,
        )
        raise PermissionDenied("You do not have permission to view the ESG Activity Master catalog.")

    can_manage = user_can_manage_activity_master(user)
    include_inactive = can_manage or user.has_role(Role.Code.AUDITOR)

    activities = get_accessible_activity_masters(user, include_inactive=include_inactive)

    search_q = request.GET.get("q", "").strip()
    category_filter = request.GET.get("category", "").strip()
    scope_filter = request.GET.get("scope", "").strip()
    status_filter = request.GET.get("status", "").strip()

    if search_q:
        activities = activities.filter(
            Q(name__icontains=search_q)
            | Q(code__icontains=search_q)
            | Q(activity_type__icontains=search_q)
            | Q(description__icontains=search_q)
        )

    if category_filter and category_filter.isdigit():
        activities = activities.filter(category_id=int(category_filter))

    if scope_filter and scope_filter in ScopeClassification.values:
        activities = activities.filter(scope_classification=scope_filter)

    if status_filter and status_filter in MasterStatus.values:
        activities = activities.filter(status=status_filter)

    # Base counts for KPI statistics
    all_activities = ActivityMaster.objects.all()
    stats = {
        "total": all_activities.count(),
        "active": all_activities.filter(status=MasterStatus.ACTIVE).count(),
        "scope_1": all_activities.filter(scope_classification=ScopeClassification.SCOPE_1).count(),
        "scope_2": all_activities.filter(scope_classification=ScopeClassification.SCOPE_2).count(),
        "scope_3": all_activities.filter(scope_classification=ScopeClassification.SCOPE_3).count(),
        "non_ghg": all_activities.filter(scope_classification=ScopeClassification.NON_GHG).count(),
        "categories_count": ActivityCategory.objects.filter(status=MasterStatus.ACTIVE).count(),
        "units_count": UnitOfMeasure.objects.filter(status=MasterStatus.ACTIVE).count(),
    }

    categories = get_accessible_activity_categories(user, include_inactive=can_manage)

    context = {
        "page_title": "ESG Activity Master & Catalog",
        "page_subtitle": "Centralized Master Data Catalog, Scope Classification & Measurement Governance",
        "active_nav": "activity_master",
        "activities": activities,
        "categories": categories,
        "stats": stats,
        "can_manage": can_manage,
        "search_q": search_q,
        "category_filter": category_filter,
        "scope_filter": scope_filter,
        "status_filter": status_filter,
        "scope_choices": ScopeClassification.choices,
        "status_choices": MasterStatus.choices,
    }
    return render(request, "activity_master/list.html", context)


# -----------------------------------------------------------------------------
# 2. ACTIVITY DETAIL VIEW
# -----------------------------------------------------------------------------

@login_required
def activity_detail_view(request, activity_id):
    """
    Detailed master-data specification for a single ESG Activity.
    """
    user = request.user
    if not user_can_view_activity_master(user):
        log_auth_event(
            user=user,
            event_type=AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            resource_accessed=f"/activity-master/{activity_id}/",
            details="Unauthorized attempt to view Activity Master detail.",
            success=False,
            request=request,
        )
        raise PermissionDenied("You do not have permission to view the ESG Activity Master.")

    activity = get_object_or_404(
        ActivityMaster.objects.select_related("category", "base_unit", "created_by", "updated_by").prefetch_related("allowed_units"),
        pk=activity_id,
    )

    can_manage = user_can_manage_activity_master(user)

    # Inactive visibility guard: Site Managers and Subsidiary Managers cannot inspect inactive activities
    if activity.status == MasterStatus.INACTIVE and not (can_manage or user.has_role(Role.Code.AUDITOR)):
        log_auth_event(
            user=user,
            event_type=AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            resource_accessed=f"/activity-master/{activity_id}/",
            details=f"Unauthorized attempt to inspect inactive Activity Master '{activity.code}'.",
            success=False,
            request=request,
        )
        raise PermissionDenied("This activity definition is inactive and not available for reference.")

    # Fetch recent audit events for this activity
    audit_events = AuthAuditLog.objects.filter(
        resource_accessed__startswith=f"ActivityMaster:{activity.id}:"
    ).order_by("-created_at")[:10]

    context = {
        "page_title": f"{activity.name} [{activity.code}]",
        "page_subtitle": f"Controlled ESG Master Definition — {activity.category.name}",
        "active_nav": "activity_master",
        "activity": activity,
        "can_manage": can_manage,
        "audit_events": audit_events,
    }
    return render(request, "activity_master/detail.html", context)


# -----------------------------------------------------------------------------
# 3. ACTIVITY CREATE VIEW
# -----------------------------------------------------------------------------

@login_required
def activity_create_view(request):
    """
    Creates a new controlled ActivityMaster entry.
    Restricted to MEIL_OPERATOR, ESG_MANAGER, and superusers.
    """
    user = request.user
    if not user_can_manage_activity_master(user):
        log_auth_event(
            user=user,
            event_type=AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            resource_accessed="/activity-master/create/",
            details="Unauthorized attempt to create Activity Master entry.",
            success=False,
            request=request,
        )
        raise PermissionDenied("You do not have permission to create Activity Master definitions.")

    if request.method == "POST":
        form = ActivityMasterForm(request.POST)
        if form.is_valid():
            activity = form.save(commit=False)
            activity.created_by = user
            activity.updated_by = user
            activity.save()
            form.save_m2m()  # Saves allowed_units

            # Ensure base_unit is in allowed_units
            if activity.base_unit:
                activity.allowed_units.add(activity.base_unit)

            log_auth_event(
                user=user,
                event_type=AuthAuditLog.EventType.ACTIVITY_MASTER_CREATED,
                resource_accessed=f"ActivityMaster:{activity.id}:{activity.code}",
                details=f"Activity Master '{activity.name}' ({activity.code}) created.",
                success=True,
                request=request,
            )
            messages.success(request, f"Activity Master '{activity.name}' ({activity.code}) created successfully.")
            return redirect("core:activity_detail", activity_id=activity.id)
    else:
        form = ActivityMasterForm()

    context = {
        "page_title": "Create ESG Activity Master",
        "page_subtitle": "Define Authoritative ESG Activity Specification & Scope Lineage",
        "active_nav": "activity_master",
        "form": form,
        "is_create": True,
    }
    return render(request, "activity_master/form.html", context)


# -----------------------------------------------------------------------------
# 4. ACTIVITY EDIT VIEW
# -----------------------------------------------------------------------------

@login_required
def activity_edit_view(request, activity_id):
    """
    Modifies an existing ActivityMaster definition.
    Restricted to authorized master-data administrators.
    """
    user = request.user
    if not user_can_manage_activity_master(user):
        log_auth_event(
            user=user,
            event_type=AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            resource_accessed=f"/activity-master/{activity_id}/edit/",
            details="Unauthorized attempt to edit Activity Master entry.",
            success=False,
            request=request,
        )
        raise PermissionDenied("You do not have permission to modify Activity Master definitions.")

    activity = get_object_or_404(ActivityMaster, pk=activity_id)

    if request.method == "POST":
        form = ActivityMasterForm(request.POST, instance=activity)
        if form.is_valid():
            activity = form.save(commit=False)
            activity.updated_by = user
            activity.save()
            form.save_m2m()

            if activity.base_unit:
                activity.allowed_units.add(activity.base_unit)

            log_auth_event(
                user=user,
                event_type=AuthAuditLog.EventType.ACTIVITY_MASTER_UPDATED,
                resource_accessed=f"ActivityMaster:{activity.id}:{activity.code}",
                details=f"Activity Master '{activity.name}' ({activity.code}) updated.",
                success=True,
                request=request,
            )
            messages.success(request, f"Activity Master '{activity.name}' ({activity.code}) updated successfully.")
            return redirect("core:activity_detail", activity_id=activity.id)
    else:
        form = ActivityMasterForm(instance=activity)

    context = {
        "page_title": f"Edit Activity: {activity.name}",
        "page_subtitle": f"Code: {activity.code} | Category: {activity.category.name}",
        "active_nav": "activity_master",
        "form": form,
        "activity": activity,
        "is_create": False,
    }
    return render(request, "activity_master/form.html", context)


# -----------------------------------------------------------------------------
# 5. ACTIVITY SAFE DEACTIVATE / ACTIVATE VIEW (POST)
# -----------------------------------------------------------------------------

@login_required
@require_http_methods(["POST"])
def activity_deactivate_view(request, activity_id):
    """
    Toggles active/inactive status without hard-deleting historical records.
    """
    user = request.user
    if not user_can_manage_activity_master(user):
        log_auth_event(
            user=user,
            event_type=AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            resource_accessed=f"/activity-master/{activity_id}/deactivate/",
            details="Unauthorized attempt to alter Activity Master lifecycle state.",
            success=False,
            request=request,
        )
        raise PermissionDenied("You do not have permission to change the lifecycle state of this activity.")

    activity = get_object_or_404(ActivityMaster, pk=activity_id)

    if activity.status == MasterStatus.ACTIVE:
        safe_deactivate_activity_master(activity, user, request=request)
        messages.warning(
            request,
            f"Activity Master '{activity.name}' ({activity.code}) has been DEACTIVATED. Historical records remain intact.",
        )
    else:
        safe_activate_activity_master(activity, user, request=request)
        messages.success(
            request,
            f"Activity Master '{activity.name}' ({activity.code}) has been ACTIVATED and restored to the catalog.",
        )

    return redirect("core:activity_detail", activity_id=activity.id)


# -----------------------------------------------------------------------------
# 6. CATEGORIES LIST & DETAIL VIEWS
# -----------------------------------------------------------------------------

@login_required
def category_list_view(request):
    """
    Lists ESG activity categories and their activity counts.
    """
    user = request.user
    if not user_can_view_activity_master(user):
        raise PermissionDenied("You do not have permission to view ESG categories.")

    can_manage = user_can_manage_activity_master(user)
    categories = ActivityCategory.objects.annotate(
        active_activities_count=Count("activities", filter=Q(activities__status=MasterStatus.ACTIVE)),
        total_activities_count=Count("activities"),
    ).order_by("display_order", "name")

    context = {
        "page_title": "ESG Activity Categories",
        "page_subtitle": "Controlled Operational Categorization & Scope Classification Taxonomies",
        "active_nav": "activity_master",
        "categories": categories,
        "can_manage": can_manage,
    }
    return render(request, "activity_master/category_list.html", context)


@login_required
def category_create_view(request):
    """
    Creates an ESG activity category.
    """
    user = request.user
    if not user_can_manage_activity_master(user):
        raise PermissionDenied("You do not have permission to create categories.")

    if request.method == "POST":
        form = ActivityCategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.created_by = user
            category.updated_by = user
            category.save()
            log_auth_event(
                user=user,
                event_type=AuthAuditLog.EventType.ACTIVITY_CATEGORY_CREATED,
                resource_accessed=f"ActivityCategory:{category.id}:{category.code}",
                details=f"Category '{category.name}' ({category.code}) created.",
                success=True,
                request=request,
            )
            messages.success(request, f"Category '{category.name}' created successfully.")
            return redirect("core:category_list")
    else:
        form = ActivityCategoryForm()

    context = {
        "page_title": "Create Activity Category",
        "page_subtitle": "Define a High-Level ESG Categorization Taxonomy",
        "active_nav": "activity_master",
        "form": form,
    }
    return render(request, "activity_master/category_form.html", context)


@login_required
def category_detail_view(request, category_id):
    """
    Detail of an ESG category with associated master activities.
    """
    user = request.user
    if not user_can_view_activity_master(user):
        raise PermissionDenied("You do not have permission to view ESG categories.")

    category = get_object_or_404(ActivityCategory, pk=category_id)
    can_manage = user_can_manage_activity_master(user)

    activities = category.activities.select_related("base_unit")
    if not (can_manage or user.has_role(Role.Code.AUDITOR)):
        activities = activities.filter(status=MasterStatus.ACTIVE)

    context = {
        "page_title": f"Category: {category.name}",
        "page_subtitle": f"Code: {category.code} | Display Order: {category.display_order}",
        "active_nav": "activity_master",
        "category": category,
        "activities": activities,
        "can_manage": can_manage,
    }
    return render(request, "activity_master/category_detail.html", context)


# -----------------------------------------------------------------------------
# 7. UNITS OF MEASURE LIST & CREATE VIEWS
# -----------------------------------------------------------------------------

@login_required
def unit_list_view(request):
    """
    Lists standardized units of measure.
    """
    user = request.user
    if not user_can_view_activity_master(user):
        raise PermissionDenied("You do not have permission to view units of measure.")

    can_manage = user_can_manage_activity_master(user)
    units = UnitOfMeasure.objects.annotate(
        base_activities_count=Count("base_activities", filter=Q(base_activities__status=MasterStatus.ACTIVE)),
    ).order_by("dimension", "name")

    context = {
        "page_title": "Standard Units of Measure",
        "page_subtitle": "Authoritative Physical Dimensions & Measurement Units for Telemetry and Calculations",
        "active_nav": "activity_master",
        "units": units,
        "can_manage": can_manage,
    }
    return render(request, "activity_master/unit_list.html", context)


@login_required
def unit_create_view(request):
    """
    Creates a new standardized Unit of Measure.
    """
    user = request.user
    if not user_can_manage_activity_master(user):
        raise PermissionDenied("You do not have permission to create units of measure.")

    if request.method == "POST":
        form = UnitOfMeasureForm(request.POST)
        if form.is_valid():
            unit = form.save(commit=False)
            unit.created_by = user
            unit.updated_by = user
            unit.save()
            log_auth_event(
                user=user,
                event_type=AuthAuditLog.EventType.UNIT_CREATED,
                resource_accessed=f"UnitOfMeasure:{unit.id}:{unit.code}",
                details=f"Unit '{unit.name}' ({unit.symbol}) created.",
                success=True,
                request=request,
            )
            messages.success(request, f"Unit '{unit.name}' ({unit.symbol}) created successfully.")
            return redirect("core:unit_list")
    else:
        form = UnitOfMeasureForm()

    context = {
        "page_title": "Create Standard Unit of Measure",
        "page_subtitle": "Define Physical Measurement Unit and Regulatory Symbol",
        "active_nav": "activity_master",
        "form": form,
    }
    return render(request, "activity_master/unit_form.html", context)
