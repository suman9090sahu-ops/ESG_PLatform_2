# MEIL ESG CONTROL TOWER — UI Component Library Guide
## Phase 01: UI Foundation & Bootstrap Design System

This guide documents the enterprise Bootstrap 5.x design system and reusable template components developed for the **MEIL ESG CONTROL TOWER**.

All components follow a strict design token hierarchy, semantic HTML, WCAG accessibility conventions, and modular Django template include/inheritance mechanics.

---

## Architecture & Directory Structure

```text
templates/
├── base/
│   ├── base.html              # Main application shell
│   ├── _head.html             # Stylesheets & meta tags
│   ├── _navbar.html           # Reusable top navbar
│   ├── _sidebar.html          # Collapsible/dynamic role-injected sidebar
│   ├── _footer.html           # Standard platform footer
│   └── _scripts.html          # Core scripts & utilities
│
├── layouts/
│   ├── dashboard.html         # Standard dashboard layout
│   ├── auth.html              # Centered authentication shell
│   └── blank.html             # Clean canvas / export template
│
└── components/
    ├── alerts/                # Feedback alerts (success, error, warning, info, validation)
    ├── buttons/               # Accessible buttons (primary, secondary, danger, icon)
    ├── cards/                 # Stat cards, metric cards, status cards, standard cards
    ├── tables/                # Responsive data tables, empty states, row actions
    ├── forms/                 # Form fields, selects, dates, textareas, drag-drop file upload
    ├── badges/                # Status badges & 12 lifecycle workflow states
    ├── modals/                # Confirmation dialog modals
    ├── breadcrumbs/           # Accessible breadcrumb trails
    ├── loading/               # Spinner & skeleton placeholder loaders
    ├── empty_states/          # Zero-data presentation containers
    ├── pagination/            # Accessible pagination controls
    ├── esg/                   # ESG-specific presentation indicators
    └── feedback/              # Permission denied (403) and server error (500) states
```

---

## 1. Application Shell & Layouts

### Dashboard Layout (`templates/layouts/dashboard.html`)
Inherits from `base/base.html` and partitions the view into modular blocks:

```django
{% extends "layouts/dashboard.html" %}

{% block title %}Site Manager Dashboard{% endblock %}

{% block page_actions %}
  <button class="btn btn-esg-primary btn-sm">Upload CEMS Telemetry</button>
{% endblock %}

{% block kpi_section %}
  <div class="row">
    <!-- Stat / Metric Cards -->
  </div>
{% endblock %}

{% block main_panel %}
  <!-- Activity / Tables -->
{% endblock %}

{% block side_panel %}
  <!-- Pending Actions / Alerts -->
{% endblock %}
```

### Authentication Layout (`templates/layouts/auth.html`)
Standalone centered layout for authentication and security workflows:

```django
{% extends "layouts/auth.html" %}

{% block auth_title %}Sign In to ESG Portal{% endblock %}
{% block auth_subtitle %}SEBI BRSR Governance & Telemetry Control Tower{% endblock %}

{% block auth_content %}
  <form method="post">
    {% csrf_token %}
    <!-- Form fields -->
  </form>
{% endblock %}
```

---

## 2. Alerts & Feedback

Located in `templates/components/alerts/`:

| Component | Path | Key Parameters |
| :--- | :--- | :--- |
| **Success Alert** | `components/alerts/success.html` | `title`, `message`, `dismissible=True` |
| **Error Alert** | `components/alerts/error.html` | `title`, `message`, `dismissible=True` |
| **Warning Alert** | `components/alerts/warning.html` | `title`, `message`, `dismissible=True` |
| **Info Alert** | `components/alerts/info.html` | `title`, `message`, `dismissible=True` |
| **Validation Summary** | `components/alerts/validation.html` | `title`, `errors` (dict or list) |

### Usage Example:
```django
{% include "components/alerts/success.html" with title="Audit Verified" message="Scope 1 stationary combustion verified by Lead Auditor." %}
{% include "components/alerts/validation.html" with errors=form.errors %}
```

---

## 3. Buttons & Actions

Located in `templates/components/buttons/`:

| Button Variant | Path | Parameters |
| :--- | :--- | :--- |
| **Primary** | `components/buttons/primary.html` | `text`, `icon`, `type="button"`, `disabled=False`, `id`, `extra_class` |
| **Secondary** | `components/buttons/secondary.html` | `text`, `icon`, `type="button"`, `disabled=False` |
| **Danger** | `components/buttons/danger.html` | `text`, `icon`, `type="button"`, `disabled=False` |
| **Icon Button** | `components/buttons/icon.html` | `icon`, `title`, `aria_label`, `disabled=False` |

### Usage Example:
```django
{% include "components/buttons/primary.html" with text="Submit Disclosure" icon="icon-check" %}
{% include "components/buttons/icon.html" with icon="icon-pencil" title="Edit Record" %}
```

---

## 4. Cards & Metric Displays

Located in `templates/components/cards/`:

### ESG Metric Card (`components/cards/metric.html`)
Presents ESG indicators according to MEIL governance standards:
```django
{% include "components/cards/metric.html" with title="Scope 1 Emissions" value="12,450" unit="tCO₂e" delta_type="increase" delta_text="↑ 4.2%" comparison_label="vs previous period" %}
```

### Stat Card (`components/cards/stat.html`)
```django
{% include "components/cards/stat.html" with title="Active Sensors" value="1,420" unit="IoT nodes" delta="<span class='text-success'>+14.2%</span>" icon="icon-globe" %}
```

### Status Card (`components/cards/status.html`)
```django
{% include "components/cards/status.html" with label="Emission Factor" metric_value="0.716" description="CEA Baseline v19" border_variant="success" status_text="Active" %}
```

### Standard Card (`components/cards/standard.html`)
```django
{% include "components/cards/standard.html" with title="Governance Policy" subtitle="SEBI Mandated" body_html="<p>BRSR Core Mandated</p>" %}
```

---

## 5. Responsive Tables & Empty States

Located in `templates/components/tables/`:

```django
{% include "components/tables/responsive.html" with headers=table_headers rows=table_rows show_actions=True %}
```

When no data exists:
```django
{% include "components/tables/empty.html" with title="No Discrepancies" message="Zero discrepancies flagged in current period." %}
```

---

## 6. Form Controls

Located in `templates/components/forms/`:

### Standard Form Field
```django
{% include "components/forms/field.html" with label="Plant ID" name="plant_code" value="MEIL-HYD-04" required=True help_text="Unique facility code." errors=form.plant_code.errors %}
```

### Select Field
```django
{% include "components/forms/select.html" with label="Scope Category" name="scope" options=scope_options selected_value="scope1" required=True %}
```

### Date Field
```django
{% include "components/forms/date.html" with label="Reading Date" name="reading_date" value="2026-10-06" required=True %}
```

### Textarea Field
```django
{% include "components/forms/textarea.html" with label="Audit Observations" name="notes" rows=3 placeholder="Enter auditor remarks..." %}
```

### File Upload Drag & Drop
```django
{% include "components/forms/file_upload.html" with label="Evidence Document" field_id="evidence_doc" name="file" required=True help_text="Supports PDF, XLSX, CSV, JPG (Max 25MB)." %}
```

### Form Action Bar
```django
{% include "components/forms/actions.html" with submit_label="Save Record" cancel_label="Cancel" cancel_url="/dashboard/" %}
```

---

## 7. Workflow Lifecycle Badges (All 12 States)

The `{% workflow_badge %}` tag renders visual tokens across the 12 platform governance states:

```django
{% load esg_tags %}

{% workflow_badge 'DRAFT' %}
{% workflow_badge 'PENDING' %}
{% workflow_badge 'SUBMITTED' %}
{% workflow_badge 'UNDER_REVIEW' %}
{% workflow_badge 'CORRECTION_REQUIRED' %}
{% workflow_badge 'VERIFIED' %}
{% workflow_badge 'REJECTED' %}
{% workflow_badge 'ESCALATED' %}
{% workflow_badge 'APPROVED' %}
{% workflow_badge 'FINALIZED' %}
{% workflow_badge 'LOCKED' %}
{% workflow_badge 'FAILED' %}
```

Each badge outputs semantic HTML, an icon, screen-reader text (`[✓]`, `[!]`, etc.), and distinctive color tokens.

---

## 8. ESG Presentation Indicators

Located in `templates/components/esg/` and exposed via template tags in `esg_tags`:

### Evidence Indicator
```django
{% load esg_tags %}
{% evidence_indicator count=3 verified=True %}
<!-- Renders: [✓] 3 Documents -->
```

### Verification Indicator
```django
{% verification_indicator verified=True label="Verified" %}
<!-- Renders: Verified ✓ -->
```

### Anomaly Indicator
```django
{% anomaly_indicator count=1 label="Anomaly" %}
<!-- Renders: Anomaly ! -->
```

### Calculation Indicator
```django
{% calculation_indicator calculated=True label="Calculated" %}
<!-- Renders: Calculated ✓ -->
```

### Lineage Indicator
```django
{% lineage_indicator traceable=True label="Traceable" %}
<!-- Renders: Traceable → -->
```

---

## 9. Modals & Confirmation Dialogs

Located in `templates/components/modals/confirmation.html`:

Accessible Bootstrap modal with CSRF protection:
```django
{% include "components/modals/confirmation.html" with modal_id="deleteModal" dialog_title="Confirm Record Deletion" message="Are you sure you wish to delete this entry?" confirm_label="Delete" confirm_variant="btn-danger" %}
```

Can also be opened dynamically via vanilla JS data attributes:
```html
<button type="button"
        class="btn btn-outline-danger"
        data-esg-confirm="true"
        data-esg-confirm-title="Revoke Approval"
        data-esg-confirm-message="Revoke sign-off for Scope 1 report?"
        data-esg-confirm-btn="Revoke"
        data-esg-confirm-variant="btn-danger">
  Revoke
</button>
```

---

## 10. Loading, Empty & Feedback States

### Spinner & Skeleton Loader (`components/loading/spinner.html`)
```django
{% include "components/loading/spinner.html" with message="Aggregating telemetry..." %}
{% include "components/loading/spinner.html" with skeleton=True %}
```

### Empty State (`components/empty_states/default.html`)
```django
{% include "components/empty_states/default.html" with title="No Anomalies Found" description="All parameters are within normal variance thresholds." action_label="View Thresholds" action_url="/thresholds/" %}
```

### Permission Denied (403) (`components/feedback/permission_denied.html`)
```django
{% include "components/feedback/permission_denied.html" with title="Site Manager Only" message="This configuration is restricted to facility supervisors." %}
```

### Server Error (500) (`components/feedback/server_error.html`)
```django
{% include "components/feedback/server_error.html" with title="Computation Failed" message="External emission registry query timed out." %}
```

---

## 11. Design Tokens & CSS Architecture

Stylesheets are split cleanly into:
1. `static/css/layout.css`: Layout dimensions, sidebar widths, navbar heights, z-index stack, responsive breakpoints.
2. `static/css/utilities.css`: Semantic color tokens, typography font stacks, pulsing status dots, accessible focus rings.
3. `static/css/components.css`: Buttons, cards, tables, forms, workflow badges, and ESG indicators.
4. `static/css/app.css`: Central aggregator stylesheet.

---

## 12. Accessibility (WCAG Compliance)

1. **Focus States:** Every button, link, and input features a visible `3px` focus ring token (`--esg-focus-ring`).
2. **Color Contrast:** Text and status badges use tested foreground/background color combinations with contrast >= 4.5:1.
3. **Screen Readers:** Icons are paired with `.sr-only` text symbols (`[✓]`, `[!]`, `[→]`).
4. **Keyboard Support:** Modals and mobile offcanvas drawers trap focus and dismiss smoothly on `Escape`.

---

## 13. Authentication & Role-Aware Navigation (Phase 02)

### Auth Layout (`templates/layouts/auth.html`)
Used for `/auth/login/`, `/auth/password-change/`, and `/auth/password-reset/`:
```django
{% extends "layouts/auth.html" %}

{% block auth_title %}Sign In to ESG Control Tower{% endblock %}
{% block auth_subtitle %}SEBI BRSR Core Governance Portal{% endblock %}

{% block auth_content %}
  <form method="post" action="{% url 'core:login' %}">
    {% csrf_token %}
    <!-- Form fields -->
  </form>
{% endblock %}
```

### Role-Aware Sidebar Navigation Injection
The global context processor automatically injects `sidebar_menu`, `user_role_title`, and `user_role_initials` based on the authenticated user's primary functional role. In templates, the sidebar renders:
```django
{% if sidebar_menu %}
  {% for section in sidebar_menu %}
    <li class="nav-item nav-category"><span class="nav-link">{{ section.title|upper }}</span></li>
    {% for item in section.items %}
      <li class="nav-item {% if item.is_active or active_nav == item.nav_id %}active{% endif %}">
        <a class="nav-link" href="{{ item.url }}">
          <span class="menu-title">{{ item.label }}</span>
          <i class="{{ item.icon }} menu-icon"></i>
        </a>
      </li>
    {% endfor %}
  {% endfor %}
{% endif %}
```

