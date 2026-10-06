"""
Global context processors for MEIL ESG CONTROL TOWER.
"""

from datetime import datetime
from django.conf import settings
from django.utils import timezone


from apps.core.auth_services import get_role_sidebar_menu


def global_context(request):
    """
    Exposes platform-level constants, RBAC identity, and navigation state to all templates.
    """
    now = timezone.now() if settings.USE_TZ else datetime.now()

    ctx = {
        "SITE_NAME": "MEIL ESG CONTROL TOWER",
        "SITE_SHORT_NAME": "MEIL ESG",
        "SITE_SUBTITLE": "Enterprise ESG Monitoring & Reporting Platform",
        "APP_VERSION": "1.0.0-phase02",
        "CURRENT_YEAR": now.year,
        "DEBUG": settings.DEBUG,
        "TIME_ZONE": settings.TIME_ZONE,
        "ENVIRONMENT": "development" if settings.DEBUG else "production",
        "user_role_initials": "CT",
        "user_role_title": "Control Tower",
        "user_role_subtitle": "Governance & Compliance",
        "sidebar_menu": None,
        "user_primary_role": None,
    }

    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        ctx["user_role_initials"] = getattr(user, "role_initials", "CT")
        ctx["user_role_title"] = getattr(user, "role_display_title", "Control Tower User")
        ctx["user_role_subtitle"] = getattr(user, "role_display_subtitle", "Governance & Compliance")
        ctx["user_primary_role"] = user.get_primary_role() if hasattr(user, "get_primary_role") else None
        ctx["sidebar_menu"] = get_role_sidebar_menu(user)

    return ctx

