"""
Custom template tags and filters for MEIL ESG CONTROL TOWER UI Components.
Provides reusable tags for workflow badges, ESG presentation indicators, alerts, and deltas.
"""

from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape

register = template.Library()

# -----------------------------------------------------------------------------
# WORKFLOW & ESG STATUS CONFIGURATION
# -----------------------------------------------------------------------------

STATUS_CONFIG = {
    # Phase 01: 12 Core Workflow States
    "draft": {
        "class": "badge-secondary",
        "wf_class": "badge-wf-draft",
        "label": "Draft",
        "icon": "icon-note",
        "symbol": "✎",
        "dot_class": "bg-secondary",
    },
    "pending": {
        "class": "badge-warning",
        "wf_class": "badge-wf-pending",
        "label": "Pending",
        "icon": "icon-clock",
        "symbol": "⏳",
        "dot_class": "bg-warning",
    },
    "submitted": {
        "class": "badge-info",
        "wf_class": "badge-wf-submitted",
        "label": "Submitted",
        "icon": "icon-paper-plane",
        "symbol": "↗",
        "dot_class": "bg-info",
    },
    "under_review": {
        "class": "badge-primary",
        "wf_class": "badge-wf-under_review",
        "label": "Under Review",
        "icon": "icon-eye",
        "symbol": "👁",
        "dot_class": "bg-primary",
    },
    "correction_required": {
        "class": "badge-warning",
        "wf_class": "badge-wf-correction_required",
        "label": "Correction Required",
        "icon": "icon-wrench",
        "symbol": "⚠",
        "dot_class": "bg-warning",
    },
    "verified": {
        "class": "badge-success",
        "wf_class": "badge-wf-verified",
        "label": "Verified",
        "icon": "icon-check",
        "symbol": "✓",
        "dot_class": "bg-success",
    },
    "rejected": {
        "class": "badge-danger",
        "wf_class": "badge-wf-rejected",
        "label": "Rejected",
        "icon": "icon-close",
        "symbol": "✕",
        "dot_class": "bg-danger",
    },
    "escalated": {
        "class": "badge-danger",
        "wf_class": "badge-wf-escalated",
        "label": "Escalated",
        "icon": "icon-fire",
        "symbol": "⚡",
        "dot_class": "bg-danger",
    },
    "approved": {
        "class": "badge-success",
        "wf_class": "badge-wf-approved",
        "label": "Approved",
        "icon": "icon-badge",
        "symbol": "★",
        "dot_class": "bg-success",
    },
    "finalized": {
        "class": "badge-info",
        "wf_class": "badge-wf-finalized",
        "label": "Finalized",
        "icon": "icon-lock",
        "symbol": "🔒",
        "dot_class": "bg-info",
    },
    "locked": {
        "class": "badge-dark",
        "wf_class": "badge-wf-locked",
        "label": "Locked",
        "icon": "icon-lock",
        "symbol": "🔒",
        "dot_class": "bg-dark",
    },
    "failed": {
        "class": "badge-danger",
        "wf_class": "badge-wf-failed",
        "label": "Failed",
        "icon": "icon-ban",
        "symbol": "✕",
        "dot_class": "bg-danger",
    },
    # General Compliance & Operational Indicators
    "compliant": {
        "class": "badge-success",
        "wf_class": "badge-wf-verified",
        "label": "Compliant",
        "icon": "icon-check",
        "symbol": "✓",
        "dot_class": "bg-success",
    },
    "breach": {
        "class": "badge-danger",
        "wf_class": "badge-wf-rejected",
        "label": "Breach / Critical",
        "icon": "icon-close",
        "symbol": "!",
        "dot_class": "bg-danger",
    },
    "critical": {
        "class": "badge-danger",
        "wf_class": "badge-wf-escalated",
        "label": "Critical Alert",
        "icon": "icon-fire",
        "symbol": "!",
        "dot_class": "bg-danger",
    },
    "warning": {
        "class": "badge-warning",
        "wf_class": "badge-wf-correction_required",
        "label": "Action Needed",
        "icon": "icon-exclamation",
        "symbol": "⚠",
        "dot_class": "bg-warning",
    },
    "in_progress": {
        "class": "badge-primary",
        "wf_class": "badge-wf-under_review",
        "label": "In Progress",
        "icon": "icon-refresh",
        "symbol": "⟳",
        "dot_class": "bg-primary",
    },
}


@register.simple_tag
def status_badge(status, custom_label=None, pill=True):
    """
    Renders an ESG status badge with pulse indicator dot and label.
    Example: {% status_badge 'compliant' %}
    """
    key = str(status).lower().strip().replace(" ", "_")
    config = STATUS_CONFIG.get(
        key,
        {
            "class": "badge-secondary",
            "wf_class": "badge-wf-draft",
            "label": str(custom_label or status).title(),
            "icon": "icon-info",
            "symbol": "•",
            "dot_class": "bg-secondary",
        },
    )

    label_text = escape(custom_label if custom_label is not None else config["label"])
    badge_type_class = "badge-pill" if pill else ""
    badge_class = config["class"]
    dot_class = config["dot_class"]

    html = f"""
    <span class="badge {badge_class} {badge_type_class} d-inline-flex align-items-center gap-1 px-2 py-1 esg-status-badge">
        <span class="status-indicator-dot {dot_class} me-1"></span>
        <span>{label_text}</span>
    </span>
    """.strip()
    return mark_safe(html)


@register.simple_tag
def workflow_badge(status, custom_label=None):
    """
    Renders an enterprise workflow status badge for any of the 12 lifecycle states.
    Example: {% workflow_badge 'CORRECTION_REQUIRED' %}
    """
    key = str(status).lower().strip().replace(" ", "_")
    config = STATUS_CONFIG.get(
        key,
        {
            "class": "badge-secondary",
            "wf_class": "badge-wf-draft",
            "label": str(custom_label or status).upper().replace("_", " "),
            "icon": "icon-info",
            "symbol": "•",
            "dot_class": "bg-secondary",
        },
    )

    label_text = escape(custom_label if custom_label is not None else config["label"].upper())
    wf_class = config.get("wf_class", "badge-wf-draft")
    icon_class = config.get("icon", "icon-info")
    symbol = config.get("symbol", "")

    html = f"""
    <span class="badge-workflow {wf_class}" title="Workflow Status: {label_text}">
        <i class="{icon_class} me-1" aria-hidden="true"></i>
        <span class="sr-only">[{symbol}] </span>
        <span>{label_text}</span>
    </span>
    """.strip()
    return mark_safe(html)


@register.simple_tag
def ui_badge(text, variant="primary", pill=False, icon=None):
    """
    Renders a standard Bootstrap badge.
    Example: {% ui_badge 'Q3 Audit' variant='info' pill=True %}
    """
    safe_text = escape(text)
    pill_class = "badge-pill" if pill else ""
    icon_html = f'<i class="{escape(icon)} me-1"></i>' if icon else ""

    html = f'<span class="badge badge-{escape(variant)} {pill_class}">{icon_html}{safe_text}</span>'
    return mark_safe(html)


@register.simple_tag
def ui_alert(message, variant="info", dismissible=True, title=None, icon=None):
    """
    Renders an accessible Bootstrap alert with semantic icon and dismiss button.
    Example: {% ui_alert 'Audit completed successfully' variant='success' title='Notice' %}
    """
    icon_map = {
        "success": "icon-check",
        "danger": "icon-close",
        "warning": "icon-exclamation",
        "info": "icon-info",
        "primary": "icon-bell",
    }
    symbol_map = {
        "success": "[✓]",
        "danger": "[!]",
        "warning": "[⚠]",
        "info": "[i]",
        "primary": "[*]",
    }
    chosen_icon = icon or icon_map.get(variant, "icon-info")
    chosen_symbol = symbol_map.get(variant, "")
    dismiss_button = (
        '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>'
        if dismissible
        else ""
    )
    title_html = f'<strong class="d-block mb-1">{escape(title)}</strong>' if title else ""

    html = f"""
    <div class="alert alert-{escape(variant)} alert-dismissible fade show d-flex align-items-start gap-2" role="alert">
        <div class="alert-icon-wrap mt-1"><i class="{escape(chosen_icon)} fs-5" aria-hidden="true"></i><span class="sr-only">{chosen_symbol} </span></div>
        <div class="flex-grow-1">
            {title_html}
            <span>{escape(message)}</span>
        </div>
        {dismiss_button}
    </div>
    """.strip()
    return mark_safe(html)


@register.filter
def esg_kpi_delta(val):
    """
    Renders a formatted percentage delta with up/down arrows.
    Example: 12.5 -> +12.5% (green), -4.2 -> -4.2% (red)
    """
    try:
        fval = float(val)
        if fval > 0:
            return mark_safe(f'<span class="text-success"><i class="icon-arrow-up-circle me-1" aria-hidden="true"></i>+{fval:.1f}%</span>')
        elif fval < 0:
            return mark_safe(f'<span class="text-danger"><i class="icon-arrow-down-circle me-1" aria-hidden="true"></i>{fval:.1f}%</span>')
        else:
            return mark_safe('<span class="text-muted">0.0%</span>')
    except (ValueError, TypeError):
        return str(val)


# -----------------------------------------------------------------------------
# ESG PRESENTATION INDICATORS (PHASE 01)
# -----------------------------------------------------------------------------

@register.simple_tag
def evidence_indicator(count=1, verified=False):
    """
    Renders evidence presentation indicator:
    Evidence: ✓ {count} Documents
    """
    icon = "icon-check" if verified else "icon-paper-clip"
    symbol = "✓" if verified else "📎"
    text = f"{count} Document{'s' if count != 1 else ''}"
    html = f"""
    <span class="esg-indicator indicator-evidence" title="{text} Attached">
        <i class="{icon} me-1" aria-hidden="true"></i>
        <span class="sr-only">[{symbol}] Evidence: </span>
        <span class="fw-semibold">{text}</span>
    </span>
    """.strip()
    return mark_safe(html)


@register.simple_tag
def verification_indicator(verified=True, label="Verified"):
    """
    Renders verification presentation indicator:
    Verified ✓
    """
    icon = "icon-check" if verified else "icon-clock"
    symbol = "✓" if verified else "⏳"
    status_class = "indicator-verified" if verified else "indicator-evidence"
    html = f"""
    <span class="esg-indicator {status_class}" title="Verification Status: {escape(label)}">
        <span class="fw-semibold me-1">{escape(label)}</span>
        <i class="{icon}" aria-hidden="true"></i>
        <span class="sr-only">[{symbol}]</span>
    </span>
    """.strip()
    return mark_safe(html)


@register.simple_tag
def anomaly_indicator(count=1, label="Anomaly"):
    """
    Renders anomaly presentation indicator:
    Anomaly !
    """
    html = f"""
    <span class="esg-indicator indicator-anomaly" title="Anomaly Detected: {count} issue(s)">
        <i class="icon-exclamation me-1" aria-hidden="true"></i>
        <span class="sr-only">[!] </span>
        <span class="fw-semibold">{escape(label)} ({count})</span>
    </span>
    """.strip()
    return mark_safe(html)


@register.simple_tag
def calculation_indicator(calculated=True, label="Calculated"):
    """
    Renders calculation presentation indicator:
    Calculated ✓
    """
    icon = "icon-calculator" if calculated else "icon-refresh"
    symbol = "✓" if calculated else "⟳"
    html = f"""
    <span class="esg-indicator indicator-calculated" title="GHG Calculation Status">
        <i class="{icon} me-1" aria-hidden="true"></i>
        <span class="sr-only">[{symbol}] </span>
        <span class="fw-semibold">{escape(label)}</span>
    </span>
    """.strip()
    return mark_safe(html)


@register.simple_tag
def lineage_indicator(traceable=True, label="Traceable"):
    """
    Renders audit lineage presentation indicator:
    Traceable →
    """
    html = f"""
    <span class="esg-indicator indicator-lineage" title="Data Lineage Trail">
        <span class="fw-semibold me-1">{escape(label)}</span>
        <i class="icon-arrow-right" aria-hidden="true"></i>
        <span class="sr-only">[→]</span>
    </span>
    """.strip()
    return mark_safe(html)
