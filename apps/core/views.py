"""
Core platform views, health check endpoint, UI preview, and custom error handlers
for MEIL ESG CONTROL TOWER.
"""

import logging
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import JsonResponse, HttpResponseServerError
from django.shortcuts import render
from django.utils import timezone
from django.utils.safestring import mark_safe

logger = logging.getLogger("apps.core")


def health_check(request):
    """
    Health check endpoint for production monitoring, uptime probes, and load balancers.
    Checks database connection and core service readiness.
    """
    db_status = "connected"
    status_code = 200
    overall_status = "healthy"

    try:
        connection.ensure_connection()
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Health check database connection failed: {exc}")
        db_status = f"unhealthy: {exc.__class__.__name__}: {str(exc)}"
        overall_status = "degraded"
        status_code = 503

    payload = {
        "status": overall_status,
        "service": "MEIL ESG CONTROL TOWER",
        "timestamp": timezone.now().isoformat(),
        "database": db_status,
        "db_name": str(settings.DATABASES["default"]["NAME"]),
        "environment": "development" if settings.DEBUG else "production",
        "version": "1.0.0-phase01",
        "timezone": settings.TIME_ZONE,
    }

    return JsonResponse(payload, status=status_code)


def landing_page_view(request):
    """
    Public Sustainability Landing Page.
    Renders an image-first, clean, modern, public-facing sustainability homepage
    featuring the sustainable architecture tower, minimal text, and prominent
    Login and Sign Up access controls. No authentication required.
    """
    context = {
        "page_title": "Building a Sustainable Future | MEIL ESG Platform",
        "headline": "Building a Sustainable Future.",
        "supporting_text": "One platform for responsible growth, environmental performance, and ESG accountability.",
        "hero_image": "images/landing/sustainable_hero.jpg",
    }
    return render(request, "landing/index.html", context)


def index_view(request):
    """
    Root URL '/' handler.
    Serves the public sustainability landing page.
    """
    return landing_page_view(request)


@login_required
def control_tower_dashboard(request):
    """
    MEIL ESG CONTROL TOWER primary executive dashboard.
    Protected view accessible only to authenticated users.
    Renders executive ESG metrics, recent activity, data status, and pending actions.
    """
    context = {
        "page_title": "Executive ESG Control Tower",
        "page_subtitle": "Continuous ESG Governance, BRSR Core Disclosures & Compliance Audit",
        "active_nav": "dashboard",
        "is_live_monitoring": True,
    }
    return render(request, "core/index.html", context)


def ui_preview(request):
    """
    Interactive UI preview showcasing all reusable Bootstrap 5.x design system components,
    workflow status badges, and ESG presentation indicators.
    """
    demo_table_headers = [
        {"label": "Facility Site", "sortable": True},
        {"label": "Emission Scope", "sortable": False},
        {"label": "Telemetry Reading", "sortable": True},
        {"label": "Workflow Status", "sortable": False},
        {"label": "Evidence Documents", "sortable": False},
    ]

    demo_table_rows = [
        [
            "<strong>Polavaram Dam Project</strong>",
            "Scope 1 (Diesel Generators)",
            "142.5 kL",
            mark_safe('<span class="badge-workflow badge-wf-verified"><i class="icon-check me-1" aria-hidden="true"></i>VERIFIED</span>'),
            mark_safe('<span class="esg-indicator indicator-evidence"><i class="icon-check me-1" aria-hidden="true"></i>3 Documents</span>'),
        ],
        [
            "<strong>Hyderabad Central Unit</strong>",
            "Scope 2 (Grid Electricity)",
            "2,450 MWh",
            mark_safe('<span class="badge-workflow badge-wf-under_review"><i class="icon-eye me-1" aria-hidden="true"></i>UNDER REVIEW</span>'),
            mark_safe('<span class="esg-indicator indicator-evidence"><i class="icon-check me-1" aria-hidden="true"></i>1 Document</span>'),
        ],
        [
            "<strong>Z-Morh Tunnel Site</strong>",
            "Scope 1 (Explosives & Blasting)",
            "18.2 tCO₂e",
            mark_safe('<span class="badge-workflow badge-wf-correction_required"><i class="icon-wrench me-1" aria-hidden="true"></i>CORRECTION REQUIRED</span>'),
            mark_safe('<span class="esg-indicator indicator-anomaly"><i class="icon-exclamation me-1" aria-hidden="true"></i>Mismatch Flag</span>'),
        ],
        [
            "<strong>Bhadradri Thermal Unit</strong>",
            "Scope 1 (Coal Combustion)",
            "4,120 tCO₂e",
            mark_safe('<span class="badge-workflow badge-wf-approved"><i class="icon-badge me-1" aria-hidden="true"></i>APPROVED</span>'),
            mark_safe('<span class="esg-indicator indicator-evidence"><i class="icon-check me-1" aria-hidden="true"></i>5 Documents</span>'),
        ],
    ]

    demo_scope_options = [
        {"value": "scope1", "label": "Scope 1 - Direct Fuel & Process Emissions"},
        {"value": "scope2", "label": "Scope 2 - Indirect Purchased Electricity"},
        {"value": "scope3", "label": "Scope 3 - Upstream & Downstream Value Chain"},
    ]

    validation_demo_errors = {
        "facility_code": ["Facility code must follow MEIL division standard (e.g., MEIL-HYD-04)."],
        "fuel_consumed": ["Fuel volume must be a valid positive numerical reading."],
    }

    context = {
        "page_title": "UI Component Library & Design System",
        "page_subtitle": "Phase 01 UI Foundation Showcase & Interactive Components Gallery",
        "active_nav": "ui_preview",
        "demo_table_headers": demo_table_headers,
        "demo_table_rows": demo_table_rows,
        "demo_scope_options": demo_scope_options,
        "validation_demo_errors": validation_demo_errors,
    }
    return render(request, "core/ui_preview.html", context)


def components_showcase(request):
    """
    Preserved Phase 00 documentation & showcase view for backwards compatibility.
    """
    context = {
        "page_title": "UI Components Showcase (15/15)",
        "active_nav": "components",
    }
    return render(request, "core/components_showcase.html", context)


# -----------------------------------------------------------------------------
# CUSTOM HTTP ERROR HANDLERS (400, 403, 404, 500)
# -----------------------------------------------------------------------------

def handler400(request, exception=None):
    """Custom 400 Bad Request handler."""
    context = {
        "error_code": "400",
        "error_title": "Bad Request",
        "error_message": "The server could not understand the request due to invalid syntax or parameters.",
        "exception": str(exception) if exception and settings.DEBUG else None,
    }
    return render(request, "errors/400.html", context, status=400)


def handler403(request, exception=None):
    """Custom 403 Forbidden / Access Denied handler."""
    context = {
        "error_code": "403",
        "error_title": "Access Forbidden",
        "error_message": "You do not have permission to access the requested ESG platform resource.",
        "exception": str(exception) if exception and settings.DEBUG else None,
    }
    return render(request, "errors/403.html", context, status=403)


def handler404(request, exception=None):
    """Custom 404 Not Found handler."""
    context = {
        "error_code": "404",
        "error_title": "Resource Not Found",
        "error_message": "The ESG data view or resource you requested could not be found.",
        "exception": str(exception) if exception and settings.DEBUG else None,
    }
    return render(request, "errors/404.html", context, status=404)


def handler500(request):
    """Custom 500 Internal Server Error handler."""
    context = {
        "error_code": "500",
        "error_title": "Internal Server Error",
        "error_message": "An unexpected error occurred in the MEIL ESG CONTROL TOWER core engine.",
    }
    try:
        return render(request, "errors/500.html", context, status=500)
    except Exception as exc:  # noqa: BLE001
        logger.critical(f"Critical error rendering 500 template: {exc}")
        return HttpResponseServerError(
            "<h1>500 Internal Server Error</h1><p>A critical server error occurred.</p>",
            content_type="text/html",
        )
