"""
Scope 3 Value Chain Views for MEIL ESG CONTROL TOWER.

Fulfills Phase 23 Requirements:
- Comprehensive 15-Category Scope 3 GHG Inventory Center
- Upstream (Categories 1-8) and Downstream (Categories 9-15) separation
- Explicit 'Data Required' and 'Requires Configuration' states (zero synthetic numbers)
- Granular Category Detail with registered activities, factors, and verified records
- Strict RBAC: ESG Manager governance, Auditor read-only assurance mode
- Full multi-tenant and role-based queryset scoping
"""

import logging
from typing import Any, Dict, Optional

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.core.auth_services import log_auth_event, role_required
from apps.core.models import (
    AuthAuditLog,
    Role,
    Scope3Category,
)
from apps.core.scope3_services import (
    get_scope3_category_detail,
    get_scope3_inventory_summary,
)

logger = logging.getLogger("apps.core")


@login_required
@role_required(Role.Code.MEIL_OPERATOR, Role.Code.ESG_MANAGER, Role.Code.AUDITOR, Role.Code.SUBSIDIARY_MANAGER)
def scope3_inventory_view(request: HttpRequest) -> HttpResponse:
    """
    Renders the Corporate Scope 3 Value Chain Emissions Inventory Dashboard.
    Provides complete visibility across all 15 official GHG Protocol categories.
    """
    period_id_raw = request.GET.get("period")
    subsidiary_id_raw = request.GET.get("subsidiary")

    period_id = int(period_id_raw) if period_id_raw and period_id_raw.isdigit() else None
    subsidiary_id = int(subsidiary_id_raw) if subsidiary_id_raw and subsidiary_id_raw.isdigit() else None

    # Retrieve scoped Scope 3 inventory
    inventory_summary = get_scope3_inventory_summary(
        user=request.user,
        period_id=period_id,
        subsidiary_id=subsidiary_id,
    )

    is_auditor = request.user.has_role(Role.Code.AUDITOR)

    # Audit log access
    log_auth_event(
        AuthAuditLog.EventType.SCOPE3_INVENTORY_VIEWED,
        user=request.user,
        resource_accessed="Scope3Inventory:Corporate",
        details=f"Scope 3 inventory viewed for period {inventory_summary['current_period']}. Total Scope 3: {inventory_summary['total_scope3_tco2e']} tCO2e.",
        success=True,
    )

    context = {
        "page_title": "Scope 3 Value Chain Emissions Inventory",
        "page_subtitle": "GHG Protocol 15-Category Upstream & Downstream Accounting, Baselines & Factor Governance",
        "active_nav": "scope3_inventory",
        "is_auditor": is_auditor,
        "is_read_only": is_auditor,
        "summary": inventory_summary,
        "total_scope3_tco2e": inventory_summary["total_scope3_tco2e"],
        "total_upstream_tco2e": inventory_summary["total_upstream_tco2e"],
        "total_downstream_tco2e": inventory_summary["total_downstream_tco2e"],
        "active_categories_count": inventory_summary["active_categories_count"],
        "requires_config_count": inventory_summary["requires_config_count"],
        "data_required_count": inventory_summary["data_required_count"],
        "upstream_categories": inventory_summary["upstream_categories"],
        "downstream_categories": inventory_summary["downstream_categories"],
        "all_categories": inventory_summary["all_categories"],
        "accessible_periods": inventory_summary["accessible_periods"],
        "accessible_subsidiaries": inventory_summary["accessible_subsidiaries"],
        "current_period": inventory_summary["current_period"],
        "selected_subsidiary_id": subsidiary_id,
    }

    return render(request, "scope3/inventory.html", context)


@login_required
@role_required(Role.Code.MEIL_OPERATOR, Role.Code.ESG_MANAGER, Role.Code.AUDITOR, Role.Code.SUBSIDIARY_MANAGER)
def scope3_category_detail_view(request: HttpRequest, category_number: int) -> HttpResponse:
    """
    Renders detailed specifications, configured factors, and verified records for a single Scope 3 category.
    """
    if category_number < 1 or category_number > 15:
        raise Http404("Invalid Scope 3 Category index. GHG Protocol defines Categories 1 through 15.")

    period_id_raw = request.GET.get("period")
    subsidiary_id_raw = request.GET.get("subsidiary")

    period_id = int(period_id_raw) if period_id_raw and period_id_raw.isdigit() else None
    subsidiary_id = int(subsidiary_id_raw) if subsidiary_id_raw and subsidiary_id_raw.isdigit() else None

    detail_data = get_scope3_category_detail(
        user=request.user,
        category_number=category_number,
        period_id=period_id,
        subsidiary_id=subsidiary_id,
    )

    category = detail_data["category"]
    cat_summary = detail_data["category_summary"]
    is_auditor = request.user.has_role(Role.Code.AUDITOR)

    context = {
        "page_title": f"Category {category.category_number}: {category.name}",
        "page_subtitle": f"Scope 3 Value Chain ({category.get_direction_display()}) — Telemetry, Emission Factors & Trace Lineage",
        "active_nav": "scope3_inventory",
        "is_auditor": is_auditor,
        "is_read_only": is_auditor,
        "category": category,
        "cat_summary": cat_summary,
        "factors": detail_data["factors"],
        "activities": detail_data["activities"],
        "records": detail_data["records"],
        "accessible_periods": detail_data["accessible_periods"],
        "accessible_subsidiaries": detail_data["accessible_subsidiaries"],
        "current_period": detail_data["current_period"],
        "selected_subsidiary_id": subsidiary_id,
    }

    return render(request, "scope3/category_detail.html", context)
