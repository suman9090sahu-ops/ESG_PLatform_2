"""
Tests for MEIL ESG CONTROL TOWER UI Components and Showcase.
Validates the rendering of all 15 required Bootstrap 5.x reusable components.
"""

from django.test import Client, SimpleTestCase
from django.template.loader import render_to_string
from django.urls import reverse
from apps.core.templatetags.esg_tags import status_badge, ui_badge, ui_alert, esg_kpi_delta


class UIComponentsTests(SimpleTestCase):
    """Test suite ensuring all 15 UI components render cleanly."""

    def setUp(self):
        self.client = Client()

    def test_dashboard_index_renders_successfully(self):
        """Index dashboard renders with 200 OK and site title."""
        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MEIL ESG CONTROL TOWER")
        self.assertContains(response, "Executive ESG Dashboard")

    def test_components_showcase_renders_successfully(self):
        """Showcase page renders with 200 OK and demonstrates components."""
        response = self.client.get(reverse("core:components_showcase"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "UI Components Showcase")
        self.assertContains(response, "15 of 15 Components Verified")

    # -------------------------------------------------------------------------
    # INDIVIDUAL REUSABLE COMPONENTS VERIFICATION (ALL 15 REQUIRED)
    # -------------------------------------------------------------------------

    def test_component_01_navbar(self):
        """1. Navbar component renders with brand and profile controls."""
        rendered = render_to_string("components/navbar.html", {"SITE_NAME": "MEIL ESG CONTROL TOWER"})
        self.assertIn("brand-esg-title", rendered)
        self.assertIn("main-navbar", rendered)

    def test_component_02_sidebar(self):
        """2. Sidebar component renders with navigation structure."""
        rendered = render_to_string("components/sidebar.html", {"active_nav": "dashboard"})
        self.assertIn('id="sidebar"', rendered)
        self.assertIn("ESG Dashboard", rendered)

    def test_component_03_breadcrumb(self):
        """3. Breadcrumb component renders active breadcrumb trails."""
        rendered = render_to_string("components/breadcrumb.html", {"current_page": "Scope 1 Emissions"})
        self.assertIn("breadcrumb", rendered)
        self.assertIn("Scope 1 Emissions", rendered)

    def test_component_04_alert(self):
        """4. Alert component renders message and variant styling."""
        rendered = render_to_string("components/alert.html", {
            "variant": "success",
            "title": "Saved",
            "message": "Operation completed.",
            "dismissible": True,
        })
        self.assertIn("alert-success", rendered)
        self.assertIn("Operation completed.", rendered)

    def test_component_05_badge(self):
        """5. Badge component renders standard badge."""
        rendered = render_to_string("components/badge.html", {
            "text": "Audit Passed",
            "variant": "primary",
            "pill": True,
        })
        self.assertIn("badge-primary", rendered)
        self.assertIn("badge-pill", rendered)
        self.assertIn("Audit Passed", rendered)

    def test_component_06_card(self):
        """6. Card component renders title, subtitle, and body content."""
        rendered = render_to_string("components/card.html", {
            "title": "Emissions Summary",
            "subtitle": "Scope 1 Details",
            "body_html": "<p>Content goes here</p>",
        })
        self.assertIn("card", rendered)
        self.assertIn("Emissions Summary", rendered)
        self.assertIn("Content goes here", rendered)

    def test_component_07_table(self):
        """7. Table component renders headers, rows, and striped styles."""
        headers = ["Facility", "Emissions", "Status"]
        rows = [["Plant 1", "50 tCO2e", "Compliant"], ["Plant 2", "70 tCO2e", "Audited"]]
        rendered = render_to_string("components/table.html", {"headers": headers, "rows": rows})
        self.assertIn("table-striped", rendered)
        self.assertIn("Plant 1", rendered)
        self.assertIn("50 tCO2e", rendered)

    def test_component_08_pagination(self):
        """8. Pagination component renders page controls."""
        rendered = render_to_string("components/pagination.html", {
            "current_page": 2,
            "total_pages": 5,
            "has_previous": True,
            "has_next": True,
        })
        self.assertIn("pagination", rendered)
        self.assertIn("Previous", rendered)
        self.assertIn("Next", rendered)

    def test_component_09_modal(self):
        """9. Modal component renders modal structure with title and body."""
        rendered = render_to_string("components/modal.html", {
            "modal_id": "testModal",
            "modal_title": "Facility Audit",
            "body_html": "<p>Audit Details</p>",
        })
        self.assertIn('id="testModal"', rendered)
        self.assertIn("Facility Audit", rendered)

    def test_component_10_form_field(self):
        """10. Form-field component renders label, input, and validation state."""
        rendered = render_to_string("components/form_field.html", {
            "label": "Meter Reading",
            "name": "reading",
            "type": "number",
            "required": True,
        })
        self.assertIn("Meter Reading", rendered)
        self.assertIn('name="reading"', rendered)
        self.assertIn("required", rendered)

    def test_component_11_file_upload(self):
        """11. File-upload component renders drag and drop container."""
        rendered = render_to_string("components/file_upload.html", {
            "field_id": "auditFile",
            "name": "audit_doc",
            "title": "Drop Evidence Document Here",
        })
        self.assertIn("esg-file-dropzone", rendered)
        self.assertIn("Drop Evidence Document Here", rendered)

    def test_component_12_status_badge(self):
        """12. Status-badge component renders pulse indicator and semantic class."""
        rendered_compliant = render_to_string("components/status_badge.html", {"status": "compliant"})
        self.assertIn("badge-success", rendered_compliant)
        self.assertIn("status-indicator-dot", rendered_compliant)

        rendered_breach = render_to_string("components/status_badge.html", {"status": "breach"})
        self.assertIn("badge-danger", rendered_breach)

    def test_component_13_empty_state(self):
        """13. Empty-state component renders empty illustration and action."""
        rendered = render_to_string("components/empty_state.html", {
            "title": "No Incidents",
            "description": "Zero incidents reported.",
            "action_label": "Create Report",
        })
        self.assertIn("esg-empty-state", rendered)
        self.assertIn("No Incidents", rendered)
        self.assertIn("Create Report", rendered)

    def test_component_14_loading_state(self):
        """14. Loading-state component renders spinner and skeleton placeholders."""
        rendered_spinner = render_to_string("components/loading_state.html", {"message": "Syncing..."})
        self.assertIn("spinner-border", rendered_spinner)
        self.assertIn("Syncing...", rendered_spinner)

        rendered_skeleton = render_to_string("components/loading_state.html", {"skeleton": True})
        self.assertIn("placeholder-glow", rendered_skeleton)

    def test_component_15_confirmation_dialog(self):
        """15. Confirmation-dialog component renders modal with destructive action confirmation."""
        rendered = render_to_string("components/confirmation_dialog.html", {
            "modal_id": "confirmDelete",
            "dialog_title": "Confirm Delete",
            "message": "Are you sure you want to delete?",
            "confirm_label": "Yes, Delete",
        })
        self.assertIn('id="confirmDelete"', rendered)
        self.assertIn("Confirm Delete", rendered)
        self.assertIn("Yes, Delete", rendered)

    # -------------------------------------------------------------------------
    # TEMPLATE TAGS TESTS
    # -------------------------------------------------------------------------

    def test_template_tags_status_badge(self):
        """status_badge template tag output."""
        out = status_badge("compliant")
        self.assertIn("badge-success", str(out))
        self.assertIn("Compliant", str(out))

    def test_template_tags_ui_badge(self):
        """ui_badge template tag output."""
        out = ui_badge("Test Badge", variant="info", pill=True)
        self.assertIn("badge-info", str(out))
        self.assertIn("Test Badge", str(out))

    def test_template_tags_ui_alert(self):
        """ui_alert template tag output."""
        out = ui_alert("Alert message text", variant="warning", title="Warning Title")
        self.assertIn("alert-warning", str(out))
        self.assertIn("Warning Title", str(out))
        self.assertIn("Alert message text", str(out))

    def test_template_tags_esg_kpi_delta(self):
        """esg_kpi_delta filter output."""
        pos = esg_kpi_delta(5.5)
        neg = esg_kpi_delta(-3.2)
        zero = esg_kpi_delta(0.0)
        self.assertIn("+5.5%", str(pos))
        self.assertIn("-3.2%", str(neg))
        self.assertIn("0.0%", str(zero))
