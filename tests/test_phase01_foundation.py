"""
Phase 01 UI Foundation & Bootstrap Design System Test Suite.
Verifies all template layouts, modular components, workflow lifecycle badges,
ESG indicators, and the /ui-preview/ showcase route.
"""

from django.test import Client, SimpleTestCase
from django.template.loader import render_to_string
from django.urls import reverse
from apps.core.templatetags.esg_tags import (
    workflow_badge,
    evidence_indicator,
    verification_indicator,
    anomaly_indicator,
    calculation_indicator,
    lineage_indicator,
)


class Phase01FoundationTests(SimpleTestCase):
    """Test suite ensuring Phase 01 layouts, modular components, and tags render cleanly."""

    def setUp(self):
        self.client = Client()

    # -------------------------------------------------------------------------
    # 1. LAYOUTS & BASE SHELL TESTS
    # -------------------------------------------------------------------------

    def test_base_template_structure(self):
        """base/base.html renders with navbar, sidebar, footer, and shell container."""
        rendered = render_to_string("base/base.html", {"SITE_NAME": "MEIL ESG CONTROL TOWER"})
        self.assertIn("container-scroller", rendered)
        self.assertIn("main-panel", rendered)
        self.assertIn("esg-footer", rendered)
        self.assertIn("esgConfirmationModal", rendered)

    def test_dashboard_layout(self):
        """layouts/dashboard.html renders with page header, title, and section blocks."""
        rendered = render_to_string("layouts/dashboard.html", {
            "page_title": "Site Manager Dashboard",
            "SITE_NAME": "MEIL ESG CONTROL TOWER",
        })
        self.assertIn("Site Manager Dashboard", rendered)
        self.assertIn("dashboard-layout", rendered)

    def test_auth_layout(self):
        """layouts/auth.html renders with centered card and branding."""
        rendered = render_to_string("layouts/auth.html", {
            "auth_title": "Portal Sign In",
            "SITE_NAME": "MEIL ESG CONTROL TOWER",
        })
        self.assertIn("auth-page-wrapper", rendered)
        self.assertIn("auth-card", rendered)
        self.assertIn("Portal Sign In", rendered)

    def test_blank_layout(self):
        """layouts/blank.html renders clean canvas."""
        rendered = render_to_string("layouts/blank.html", {"SITE_NAME": "MEIL ESG CONTROL TOWER"})
        self.assertIn("blank-layout-wrapper", rendered)

    def test_ui_preview_route_renders_200(self):
        """/ui-preview/ endpoint renders successfully with 200 OK and showcase sections."""
        response = self.client.get(reverse("core:ui_preview"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "UI Component Library &amp; Design System")
        self.assertContains(response, "1. Buttons")
        self.assertContains(response, "2. Workflow Lifecycle Status Badges")
        self.assertContains(response, "3. ESG Presentation Indicators")
        self.assertContains(response, "4. Reusable Cards")
        self.assertContains(response, "5. Feedback &amp; Alert Notifications")
        self.assertContains(response, "6. Responsive Tables")
        self.assertContains(response, "7. Forms")
        self.assertContains(response, "8. Modals")

    # -------------------------------------------------------------------------
    # 2. MODULAR ALERT COMPONENTS
    # -------------------------------------------------------------------------

    def test_alerts_success(self):
        """Alerts: success.html renders with icon and message."""
        rendered = render_to_string("components/alerts/success.html", {"message": "Audit verified."})
        self.assertIn("alert-success", rendered)
        self.assertIn("Audit verified.", rendered)

    def test_alerts_error(self):
        """Alerts: error.html renders with danger alert styling."""
        rendered = render_to_string("components/alerts/error.html", {"message": "Sensor offline."})
        self.assertIn("alert-danger", rendered)
        self.assertIn("Sensor offline.", rendered)

    def test_alerts_warning(self):
        """Alerts: warning.html renders with warning alert styling."""
        rendered = render_to_string("components/alerts/warning.html", {"message": "Tolerance exceeded."})
        self.assertIn("alert-warning", rendered)
        self.assertIn("Tolerance exceeded.", rendered)

    def test_alerts_info(self):
        """Alerts: info.html renders with info alert styling."""
        rendered = render_to_string("components/alerts/info.html", {"message": "Filing window open."})
        self.assertIn("alert-info", rendered)
        self.assertIn("Filing window open.", rendered)

    def test_alerts_validation(self):
        """Alerts: validation.html renders validation error summary."""
        errors = {"site": ["Required field."], "reading": ["Must be positive."]}
        rendered = render_to_string("components/alerts/validation.html", {"errors": errors})
        self.assertIn("Site:", rendered)
        self.assertIn("Required field.", rendered)

    # -------------------------------------------------------------------------
    # 3. BUTTON COMPONENTS
    # -------------------------------------------------------------------------

    def test_buttons(self):
        """Buttons: primary, secondary, danger, icon render correctly."""
        primary = render_to_string("components/buttons/primary.html", {"text": "Save Data"})
        self.assertIn("btn-esg-primary", primary)
        self.assertIn("Save Data", primary)

        secondary = render_to_string("components/buttons/secondary.html", {"text": "Cancel"})
        self.assertIn("btn-esg-secondary", secondary)

        danger = render_to_string("components/buttons/danger.html", {"text": "Delete Entry"})
        self.assertIn("btn-esg-danger", danger)

        icon = render_to_string("components/buttons/icon.html", {"icon": "icon-pencil", "title": "Edit"})
        self.assertIn("btn-esg-icon", icon)
        self.assertIn("icon-pencil", icon)

    # -------------------------------------------------------------------------
    # 4. CARD COMPONENTS (STAT, STANDARD, STATUS, METRIC)
    # -------------------------------------------------------------------------

    def test_cards_stat(self):
        """Cards: stat.html renders title, value, and unit."""
        rendered = render_to_string("components/cards/stat.html", {
            "title": "Active Sensors",
            "value": "1,420",
            "unit": "IoT nodes",
        })
        self.assertIn("Active Sensors", rendered)
        self.assertIn("1,420", rendered)
        self.assertIn("IoT nodes", rendered)

    def test_cards_standard(self):
        """Cards: standard.html renders title and body content."""
        rendered = render_to_string("components/cards/standard.html", {
            "title": "Governance Policy",
            "body_html": "<p>BRSR Core Mandated</p>",
        })
        self.assertIn("Governance Policy", rendered)
        self.assertIn("BRSR Core Mandated", rendered)

    def test_cards_status(self):
        """Cards: status.html renders metric value and border variant."""
        rendered = render_to_string("components/cards/status.html", {
            "label": "Grid Emission Factor",
            "metric_value": "0.716",
            "border_variant": "success",
            "status_text": "Active",
        })
        self.assertIn("0.716", rendered)
        self.assertIn("border-success", rendered)

    def test_cards_metric(self):
        """Cards: metric.html renders ESG metric card with delta."""
        rendered = render_to_string("components/cards/metric.html", {
            "title": "Scope 1 Emissions",
            "value": "12,450",
            "unit": "tCO₂e",
            "delta_type": "increase",
            "delta_text": "4.2%",
        })
        self.assertIn("Scope 1 Emissions", rendered)
        self.assertIn("12,450", rendered)
        self.assertIn("tCO₂e", rendered)
        self.assertIn("4.2%", rendered)

    # -------------------------------------------------------------------------
    # 5. TABLE & PAGINATION COMPONENTS
    # -------------------------------------------------------------------------

    def test_tables_responsive(self):
        """Tables: responsive.html renders headers and rows."""
        headers = ["Facility", "Emissions"]
        rows = [["Hyderabad Plant", "450 tCO2e"]]
        rendered = render_to_string("components/tables/responsive.html", {
            "headers": headers,
            "rows": rows,
        })
        self.assertIn("Hyderabad Plant", rendered)
        self.assertIn("table-responsive", rendered)

    def test_tables_empty(self):
        """Tables: empty.html renders empty data message."""
        rendered = render_to_string("components/tables/empty.html", {"message": "Zero records."})
        self.assertIn("Zero records.", rendered)

    def test_pagination(self):
        """Pagination: pagination.html renders accessible page navigation."""
        rendered = render_to_string("components/pagination/pagination.html", {
            "current_page": 1,
            "total_pages": 4,
            "has_next": True,
        })
        self.assertIn("Page 1 of 4", rendered)
        self.assertIn("Next", rendered)

    # -------------------------------------------------------------------------
    # 6. FORM COMPONENTS
    # -------------------------------------------------------------------------

    def test_forms_field(self):
        """Forms: field.html renders label, input, and required star."""
        rendered = render_to_string("components/forms/field.html", {
            "label": "Plant Code",
            "name": "plant_code",
            "required": True,
        })
        self.assertIn("Plant Code", rendered)
        self.assertIn('name="plant_code"', rendered)
        self.assertIn("required", rendered)

    def test_forms_select(self):
        """Forms: select.html renders options and selected value."""
        options = [{"value": "diesel", "label": "Diesel Fuel"}]
        rendered = render_to_string("components/forms/select.html", {
            "label": "Fuel Type",
            "name": "fuel_type",
            "options": options,
            "selected_value": "diesel",
        })
        self.assertIn("Diesel Fuel", rendered)
        self.assertIn('value="diesel"', rendered)

    def test_forms_date(self):
        """Forms: date.html renders date input."""
        rendered = render_to_string("components/forms/date.html", {
            "label": "Reading Date",
            "name": "reading_date",
            "value": "2026-10-06",
        })
        self.assertIn('type="date"', rendered)
        self.assertIn('value="2026-10-06"', rendered)

    def test_forms_textarea(self):
        """Forms: textarea.html renders textarea input."""
        rendered = render_to_string("components/forms/textarea.html", {
            "label": "Audit Notes",
            "name": "notes",
            "value": "Calibration complete.",
        })
        self.assertIn("Calibration complete.", rendered)
        self.assertIn("<textarea", rendered)

    def test_forms_actions(self):
        """Forms: actions.html renders submit and cancel buttons."""
        rendered = render_to_string("components/forms/actions.html", {
            "submit_label": "Save Changes",
            "cancel_label": "Discard",
        })
        self.assertIn("Save Changes", rendered)
        self.assertIn("Discard", rendered)

    # -------------------------------------------------------------------------
    # 7. WORKFLOW STATUS BADGES (ALL 12 STATES)
    # -------------------------------------------------------------------------

    def test_all_12_workflow_badge_states(self):
        """workflow_badge renders all 12 defined governance lifecycle states."""
        states = [
            "DRAFT",
            "PENDING",
            "SUBMITTED",
            "UNDER_REVIEW",
            "CORRECTION_REQUIRED",
            "VERIFIED",
            "REJECTED",
            "ESCALATED",
            "APPROVED",
            "FINALIZED",
            "LOCKED",
            "FAILED",
        ]
        for state in states:
            out = workflow_badge(state)
            self.assertIn(f"badge-wf-{state.lower()}", str(out))
            self.assertIn(state.replace("_", " "), str(out))

    # -------------------------------------------------------------------------
    # 8. ESG PRESENTATION INDICATORS
    # -------------------------------------------------------------------------

    def test_esg_evidence_indicator(self):
        """evidence_indicator renders document count and checkmark."""
        out = evidence_indicator(count=3, verified=True)
        self.assertIn("3 Documents", str(out))
        self.assertIn("indicator-evidence", str(out))

    def test_esg_verification_indicator(self):
        """verification_indicator renders verified status."""
        out = verification_indicator(verified=True)
        self.assertIn("Verified", str(out))
        self.assertIn("indicator-verified", str(out))

    def test_esg_anomaly_indicator(self):
        """anomaly_indicator renders anomaly alert."""
        out = anomaly_indicator(count=2, label="Anomaly")
        self.assertIn("Anomaly (2)", str(out))
        self.assertIn("indicator-anomaly", str(out))

    def test_esg_calculation_indicator(self):
        """calculation_indicator renders calculated status."""
        out = calculation_indicator(calculated=True)
        self.assertIn("Calculated", str(out))
        self.assertIn("indicator-calculated", str(out))

    def test_esg_lineage_indicator(self):
        """lineage_indicator renders traceability arrow."""
        out = lineage_indicator(traceable=True)
        self.assertIn("Traceable", str(out))
        self.assertIn("indicator-lineage", str(out))

    # -------------------------------------------------------------------------
    # 9. FEEDBACK & ERROR STATES
    # -------------------------------------------------------------------------

    def test_feedback_permission_denied(self):
        """Permission denied state component renders lock icon and message."""
        rendered = render_to_string("components/feedback/permission_denied.html", {
            "title": "Access Restricted",
            "message": "Site Manager role required.",
        })
        self.assertIn("Access Restricted", rendered)
        self.assertIn("Site Manager role required.", rendered)

    def test_feedback_server_error(self):
        """Server error state component renders error message and retry button."""
        rendered = render_to_string("components/feedback/server_error.html", {
            "title": "Computation Error",
            "message": "Calculation service unavailable.",
        })
        self.assertIn("Computation Error", rendered)
        self.assertIn("Calculation service unavailable.", rendered)
