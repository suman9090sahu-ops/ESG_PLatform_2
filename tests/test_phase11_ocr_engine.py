"""
Phase 11 OCR Engine & Document Intelligence Test Suite.

Covers:
1. OCRRun & OCRField Model Instantiation, Constraints, Indexes, and Lifecycle.
2. OCR Result Multi-Run Versioning (preserving immutable history).
3. Evidence Model OCR Integration Properties.
4. Provider Abstraction (PyPDFTextProvider, Tesseract graceful error handling, MockOCRProvider).
5. Deterministic Structured Field Extraction & Normalization.
6. OCR vs. Activity Record Comparison Engine (Quantity, Unit, Date, Document Reference).
7. Strict Non-Auto-Correction Guarantee (authoritative operational data immutability).
8. Transaction-Safe Execution Runner & Audit Event Lineage.
9. RBAC & Anti-IDOR Security (Site Manager, Sub Manager, ESG Manager, Operator, Auditor Read-Only).
10. Dual-Mode View Handlers (HTTP Redirection & Reactive AJAX JSON payloads).
"""

import io
from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    ActivityRecord,
    AuthAuditLog,
    Company,
    Evidence,
    EvidenceStatus,
    EvidenceType,
    OCRField,
    OCRRun,
    OCRStatus,
    OrganizationStatus,
    PeriodStatus,
    Project,
    RecordStatus,
    ReportingPeriod,
    Role,
    ScopeClassification,
    Site,
    SiteAssignment,
    Subsidiary,
    SubsidiaryAssignment,
    UnitOfMeasure,
    User,
    UserRole,
)
from apps.core.ocr_services import (
    MockOCRProvider,
    OCREngineUnavailableError,
    OCRError,
    PyPDFTextProvider,
    TesseractOCRProvider,
    UnsupportedDocumentTypeError,
    compare_ocr_with_activity_record,
    execute_ocr_run,
    extract_structured_fields,
    get_ocr_provider,
    user_can_process_ocr,
    user_can_view_ocr,
)


def create_sample_pdf_bytes(text: str = "TAX INVOICE Invoice No: INV-2026-901 Units: 1250 kWh") -> bytes:
    """Creates a genuine, valid 1-page PDF byte string containing the specified text."""
    from pypdf import PdfWriter, PdfReader
    lines = text.strip().split("\n")
    stream_ops = [b"BT\n/F1 12 Tf\n50 720 Td\n"]
    for i, line in enumerate(lines):
        clean_line = line.replace("(", "").replace(")", "").encode("latin-1", errors="replace")
        if i == 0:
            stream_ops.append(b"(" + clean_line + b") Tj\n")
        else:
            stream_ops.append(b"0 -18 Td\n(" + clean_line + b") Tj\n")
    stream_ops.append(b"ET\n")
    stream_content = b"".join(stream_ops)
    stream_len = len(stream_content)

    pdf_raw = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >> endobj\n"
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"5 0 obj << /Length " + str(stream_len).encode("ascii") + b" >> stream\n"
        + stream_content +
        b"endstream\nendobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000236 00000 n \n"
        b"0000000305 00000 n \n"
        b"trailer << /Size 6 /Root 1 0 R >>\n"
        b"startxref\n500\n%%EOF"
    )
    try:
        reader = PdfReader(io.BytesIO(pdf_raw))
        writer = PdfWriter()
        writer.add_page(reader.pages[0])
        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue()
    except Exception:
        return pdf_raw


class Phase11OCRBaseTestCase(TestCase):
    """Base setup for Phase 11 testing."""

    def setUp(self):
        # 1. Create Roles
        self.role_operator = Role.objects.create(code=Role.Code.MEIL_OPERATOR, name="MEIL Operator")
        self.role_esg = Role.objects.create(code=Role.Code.ESG_MANAGER, name="ESG Manager")
        self.role_sub_mgr = Role.objects.create(code=Role.Code.SUBSIDIARY_MANAGER, name="Subsidiary Manager")
        self.role_site_mgr = Role.objects.create(code=Role.Code.SITE_MANAGER, name="Site Manager")
        self.role_auditor = Role.objects.create(code=Role.Code.AUDITOR, name="Auditor")

        # 2. Create Users
        self.user_operator = User.objects.create_user(username="ocr_operator", password="password123")
        UserRole.objects.create(user=self.user_operator, role=self.role_operator, is_primary=True)

        self.user_esg = User.objects.create_user(username="ocr_esg", password="password123")
        UserRole.objects.create(user=self.user_esg, role=self.role_esg, is_primary=True)

        self.user_sub_mgr = User.objects.create_user(username="ocr_sub_mgr", password="password123")
        UserRole.objects.create(user=self.user_sub_mgr, role=self.role_sub_mgr, is_primary=True)

        self.user_site_mgr = User.objects.create_user(username="ocr_site_mgr", password="password123")
        UserRole.objects.create(user=self.user_site_mgr, role=self.role_site_mgr, is_primary=True)

        self.user_other_site_mgr = User.objects.create_user(username="ocr_other_site_mgr", password="password123")
        UserRole.objects.create(user=self.user_other_site_mgr, role=self.role_site_mgr, is_primary=True)

        self.user_auditor = User.objects.create_user(username="ocr_auditor", password="password123")
        UserRole.objects.create(user=self.user_auditor, role=self.role_auditor, is_primary=True)

        # 3. Hierarchy
        self.company = Company.objects.create(name="MEIL Corp", code="MEIL-CORP", status=OrganizationStatus.ACTIVE)
        self.subsidiary1 = Subsidiary.objects.create(company=self.company, name="Hydro Division", code="MEIL-HYDRO", status=OrganizationStatus.ACTIVE)
        self.subsidiary2 = Subsidiary.objects.create(company=self.company, name="Solar Division", code="MEIL-SOLAR", status=OrganizationStatus.ACTIVE)

        self.project1 = Project.objects.create(subsidiary=self.subsidiary1, name="Dam Project", code="PRJ-DAM-01", status=OrganizationStatus.ACTIVE)
        self.project2 = Project.objects.create(subsidiary=self.subsidiary2, name="Solar Park", code="PRJ-SOL-02", status=OrganizationStatus.ACTIVE)

        self.site1 = Site.objects.create(project=self.project1, name="Site 101", code="SITE-101", status=OrganizationStatus.ACTIVE)
        self.site2 = Site.objects.create(project=self.project2, name="Site 202", code="SITE-202", status=OrganizationStatus.ACTIVE)

        # Assignments
        SiteAssignment.objects.create(user=self.user_site_mgr, site=self.site1)
        SiteAssignment.objects.create(user=self.user_other_site_mgr, site=self.site2)
        SubsidiaryAssignment.objects.create(user=self.user_sub_mgr, subsidiary=self.subsidiary1)

        # 4. Period & Masters
        self.period = ReportingPeriod.objects.create(
            company=self.company,
            code="FY2025-26",
            name="Financial Year 2025-26",
            fiscal_year=2026,
            start_date="2025-04-01",
            end_date="2026-03-31",
            status=PeriodStatus.OPEN,
        )

        self.cat_scope2 = ActivityCategory.objects.create(name="Purchased Electricity", code="ELEC", display_order=1)
        self.unit_kwh = UnitOfMeasure.objects.create(name="Kilowatt Hour", code="KWH", symbol="kWh")
        self.activity_grid = ActivityMaster.objects.create(
            name="Grid Electricity",
            code="ACT-GRID-01",
            category=self.cat_scope2,
            activity_type="Purchased Electricity",
            scope_classification=ScopeClassification.SCOPE_2,
            base_unit=self.unit_kwh,
            evidence_requirement_hint="Utility Bill / Tax Invoice",
        )
        self.activity_grid.allowed_units.add(self.unit_kwh)

        # 5. Activity Record
        self.record1 = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.period,
            activity=self.activity_grid,
            quantity=Decimal("1250.00"),
            unit=self.unit_kwh,
            measurement_date="2026-03-15",
            evidence_reference="INV-2026-901",
            status=RecordStatus.DRAFT,
            created_by=self.user_site_mgr,
        )

        self.record2 = ActivityRecord.objects.create(
            site=self.site2,
            reporting_period=self.period,
            activity=self.activity_grid,
            quantity=Decimal("500.00"),
            unit=self.unit_kwh,
            measurement_date="2026-03-10",
            evidence_reference="INV-SOLAR-55",
            status=RecordStatus.DRAFT,
            created_by=self.user_other_site_mgr,
        )

        # 6. Evidence with Real Sample PDF
        pdf_bytes = create_sample_pdf_bytes(
            "TAX INVOICE\n"
            "Supplier: Southern Power Distribution Co\n"
            "Invoice No: INV-2026-901\n"
            "Invoice Date: 2026-03-15\n"
            "Billing Period: Mar 2026\n"
            "Units Consumed: 1,250.00 kWh\n"
            "Total Amount: INR 9,375.00\n"
            "Meter No: MTR-MEIL-901\n"
        )
        upload_pdf = SimpleUploadedFile("utility_invoice.pdf", pdf_bytes, content_type="application/pdf")
        self.evidence1 = Evidence.objects.create(
            activity_record=self.record1,
            file=upload_pdf,
            evidence_type=EvidenceType.UTILITY_BILL,
            original_filename="utility_invoice.pdf",
            file_type="application/pdf",
            file_size=len(pdf_bytes),
            file_hash="fakehash123",
            description="March electricity invoice",
            status=EvidenceStatus.ACTIVE,
            uploaded_by=self.user_site_mgr,
        )

        # Evidence for Site 2
        self.evidence2 = Evidence.objects.create(
            activity_record=self.record2,
            file=SimpleUploadedFile("solar_slip.pdf", pdf_bytes, content_type="application/pdf"),
            evidence_type=EvidenceType.INVOICE,
            original_filename="solar_slip.pdf",
            file_type="application/pdf",
            file_size=len(pdf_bytes),
            file_hash="fakehash456",
            status=EvidenceStatus.ACTIVE,
            uploaded_by=self.user_other_site_mgr,
        )


class TestOCRModels(Phase11OCRBaseTestCase):
    """Unit tests for OCRRun and OCRField models, constraints, and relationships."""

    def test_ocr_run_creation(self):
        run = OCRRun.objects.create(
            evidence=self.evidence1,
            run_number=1,
            status=OCRStatus.COMPLETED,
            engine="pypdf-text-extractor",
            page_count=1,
            extracted_text="Sample text",
            confidence=Decimal("95.50"),
            processed_by=self.user_site_mgr,
        )
        self.assertEqual(run.run_number, 1)
        self.assertTrue(run.is_completed)
        self.assertFalse(run.is_failed)
        self.assertEqual(run.badge_class, "badge-success")
        self.assertEqual(str(run), f"OCR Run #1 for Evidence #{self.evidence1.id} (COMPLETED)")

    def test_ocr_run_unique_constraint(self):
        OCRRun.objects.create(evidence=self.evidence1, run_number=1, status=OCRStatus.COMPLETED)
        with self.assertRaises(IntegrityError):
            OCRRun.objects.create(evidence=self.evidence1, run_number=1, status=OCRStatus.PENDING)

    def test_ocr_run_versioning(self):
        run1 = OCRRun.objects.create(evidence=self.evidence1, run_number=1, status=OCRStatus.FAILED, is_latest=False)
        run2 = OCRRun.objects.create(evidence=self.evidence1, run_number=2, status=OCRStatus.COMPLETED, is_latest=True)

        self.assertEqual(self.evidence1.ocr_runs.count(), 2)
        self.assertEqual(self.evidence1.latest_ocr_run.id, run2.id)
        self.assertEqual(self.evidence1.ocr_status, OCRStatus.COMPLETED)
        self.assertEqual(self.evidence1.ocr_badge_class, "badge-success")

    def test_ocr_field_creation_and_cascade(self):
        run = OCRRun.objects.create(evidence=self.evidence1, run_number=1, status=OCRStatus.COMPLETED)
        field = OCRField.objects.create(
            ocr_run=run,
            field_name="quantity",
            raw_value="1,250.00 kWh",
            normalized_value="1250.00",
            unit="kWh",
            confidence=Decimal("98.00"),
            extraction_method="REGEX_PATTERN",
        )
        self.assertEqual(field.normalized_value, "1250.00")
        self.assertEqual(field.unit, "kWh")
        self.assertEqual(run.fields.count(), 1)

        # Cascade check
        run.delete()
        self.assertFalse(OCRField.objects.filter(id=field.id).exists())

    def test_evidence_ocr_properties(self):
        self.assertTrue(self.evidence1.is_ocr_supported)
        self.assertEqual(self.evidence1.ocr_status, "NOT_PROCESSED")
        self.assertFalse(self.evidence1.has_ocr_run)

        # Add a run
        OCRRun.objects.create(evidence=self.evidence1, run_number=1, status=OCRStatus.PROCESSING, is_latest=True)
        self.assertTrue(self.evidence1.has_ocr_run)
        self.assertEqual(self.evidence1.ocr_status, OCRStatus.PROCESSING)
        self.assertEqual(self.evidence1.ocr_badge_class, "badge-info")


class TestOCRServicesAndProviders(Phase11OCRBaseTestCase):
    """Unit tests for OCR service providers, field extractor, and comparison engine."""

    def test_pypdf_text_provider_success(self):
        provider = PyPDFTextProvider()
        self.assertTrue(provider.can_process(".pdf"))
        self.assertFalse(provider.can_process(".png"))

        result = provider.extract(self.evidence1.file.path)
        self.assertGreaterEqual(result.page_count, 1)
        self.assertIn("TAX INVOICE", result.extracted_text)
        self.assertIn("INV-2026-901", result.extracted_text)
        self.assertGreaterEqual(result.confidence, Decimal("70.00"))

    def test_tesseract_graceful_handling(self):
        provider = TesseractOCRProvider()
        self.assertTrue(provider.can_process(".jpg"))
        self.assertTrue(provider.can_process(".png"))

        # When tesseract binary is not installed, it must raise OCREngineUnavailableError without crashing
        if not provider.is_available():
            with self.assertRaises(OCREngineUnavailableError) as ctx:
                provider.extract("non_existent_file.jpg")
            self.assertIn("Tesseract", str(ctx.exception))

    def test_mock_provider_success_and_failure(self):
        mock_p = MockOCRProvider(text="CUSTOM OCR INVOICE 999", confidence=Decimal("99.00"))
        res = mock_p.extract("any_path.pdf")
        self.assertEqual(res.extracted_text, "CUSTOM OCR INVOICE 999")
        self.assertEqual(res.confidence, Decimal("99.00"))

        mock_fail = MockOCRProvider(should_fail=True, error_message="Engine Corrupted")
        with self.assertRaises(OCRError) as ctx:
            mock_fail.extract("any_path.pdf")
        self.assertEqual(str(ctx.exception), "Engine Corrupted")

    def test_extract_structured_fields(self):
        run = OCRRun.objects.create(evidence=self.evidence1, run_number=1, status=OCRStatus.COMPLETED)
        sample_doc = (
            "TAX INVOICE\n"
            "Supplier: Southern Power Distribution Co\n"
            "Invoice No: INV-2026-901\n"
            "Invoice Date: 15/03/2026\n"
            "Billing Period: Mar 2026\n"
            "Units Consumed: 1,250.00 kWh\n"
            "Total Amount: INR 9,375.00\n"
            "Meter No: MTR-MEIL-901\n"
        )
        fields = extract_structured_fields(run, sample_doc)
        fields_by_name = {f.field_name: f for f in fields}

        self.assertIn("invoice_number", fields_by_name)
        self.assertEqual(fields_by_name["invoice_number"].normalized_value, "INV-2026-901")

        self.assertIn("quantity", fields_by_name)
        self.assertEqual(fields_by_name["quantity"].normalized_value, "1250.00")
        self.assertEqual(fields_by_name["quantity"].unit, "kWh")

        self.assertIn("invoice_date", fields_by_name)
        self.assertEqual(fields_by_name["invoice_date"].normalized_value, "2026-03-15")

        self.assertIn("total_amount", fields_by_name)
        self.assertEqual(fields_by_name["total_amount"].normalized_value, "9375.00")
        self.assertEqual(fields_by_name["total_amount"].unit, "INR")

    def test_compare_ocr_with_activity_record_match(self):
        run = OCRRun.objects.create(evidence=self.evidence1, run_number=1, status=OCRStatus.COMPLETED)
        # Record quantity is 1250.00 kWh, date is 2026-03-15, ref is INV-2026-901
        OCRField.objects.create(ocr_run=run, field_name="quantity", raw_value="1,250.00 kWh", normalized_value="1250.00", unit="kWh")
        OCRField.objects.create(ocr_run=run, field_name="invoice_date", raw_value="15/03/2026", normalized_value="2026-03-15")
        OCRField.objects.create(ocr_run=run, field_name="invoice_number", raw_value="INV-2026-901", normalized_value="INV-2026-901")

        comparison = compare_ocr_with_activity_record(run)
        self.assertEqual(comparison["overall_status"], "MATCH")
        self.assertEqual(comparison["items"]["quantity"]["status"], "MATCH")
        self.assertEqual(comparison["items"]["quantity"]["delta"], 0.0)
        self.assertEqual(comparison["items"]["unit"]["status"], "MATCH")
        self.assertEqual(comparison["items"]["date"]["status"], "MATCH")
        self.assertEqual(comparison["items"]["reference"]["status"], "MATCH")

    def test_compare_ocr_with_activity_record_mismatch(self):
        run = OCRRun.objects.create(evidence=self.evidence1, run_number=1, status=OCRStatus.COMPLETED)
        # Mismatching quantity: 980 kWh instead of 1250 kWh
        OCRField.objects.create(ocr_run=run, field_name="quantity", raw_value="980.00 kWh", normalized_value="980.00", unit="kWh")
        OCRField.objects.create(ocr_run=run, field_name="invoice_number", raw_value="INV-DIFF-999", normalized_value="INV-DIFF-999")

        comparison = compare_ocr_with_activity_record(run)
        self.assertEqual(comparison["overall_status"], "MISMATCH")
        self.assertEqual(comparison["items"]["quantity"]["status"], "MISMATCH")
        self.assertEqual(comparison["items"]["quantity"]["delta"], -270.0)
        self.assertEqual(comparison["items"]["reference"]["status"], "MISMATCH")

    def test_ocr_does_not_mutate_activity_record(self):
        """CRITICAL: Running OCR must never silently overwrite authoritative operational data."""
        original_qty = self.record1.quantity
        original_status = self.record1.status
        original_ref = self.record1.evidence_reference

        # Run OCR with mismatching mock provider
        mock_p = MockOCRProvider(text="Units: 9999 kWh Invoice No: OTHER-999")
        ocr_run = execute_ocr_run(self.evidence1, user=self.user_site_mgr, provider_override=mock_p)

        self.record1.refresh_from_db()
        self.assertEqual(self.record1.quantity, original_qty)
        self.assertEqual(self.record1.status, original_status)
        self.assertEqual(self.record1.evidence_reference, original_ref)

    def test_unsupported_file_type_rejection(self):
        self.evidence1.original_filename = "data_sheet.xlsx"
        self.evidence1.save()

        with self.assertRaises(UnsupportedDocumentTypeError):
            execute_ocr_run(self.evidence1, user=self.user_site_mgr)

    def test_execute_ocr_run_success_and_retry(self):
        # Run 1
        run1 = execute_ocr_run(self.evidence1, user=self.user_site_mgr)
        self.assertEqual(run1.run_number, 1)
        self.assertEqual(run1.status, OCRStatus.COMPLETED)
        self.assertTrue(run1.is_latest)
        self.assertGreater(run1.fields.count(), 0)

        # Run 2 (Retry)
        run2 = execute_ocr_run(self.evidence1, user=self.user_site_mgr)
        self.assertEqual(run2.run_number, 2)
        self.assertEqual(run2.status, OCRStatus.COMPLETED)
        self.assertTrue(run2.is_latest)

        # Check historical preservation
        run1.refresh_from_db()
        self.assertFalse(run1.is_latest)
        self.assertEqual(self.evidence1.ocr_runs.count(), 2)

        # Check AuthAuditLog
        logs = AuthAuditLog.objects.filter(resource_accessed__contains=f"Evidence:{self.evidence1.id}")
        event_types = [l.event_type for l in logs]
        self.assertIn(AuthAuditLog.EventType.OCR_STARTED, event_types)
        self.assertIn(AuthAuditLog.EventType.OCR_COMPLETED, event_types)
        self.assertIn(AuthAuditLog.EventType.OCR_RETRIED, event_types)


class TestOCRSecurityAndRBAC(Phase11OCRBaseTestCase):
    """Tests for authorization guards, Anti-IDOR, and Auditor read-only restrictions."""

    def setUp(self):
        super().setUp()
        self.client = Client()

    def test_unauthenticated_blocked(self):
        url = reverse("core:evidence_ocr_process", args=[self.evidence1.id])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/auth/login/", resp.url)

    def test_site_manager_authorized_scope(self):
        self.client.force_login(self.user_site_mgr)
        url = reverse("core:evidence_ocr_process", args=[self.evidence1.id])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.evidence1.ocr_runs.count(), 1)

    def test_site_manager_idor_defense(self):
        """Site manager 1 attempting to run OCR on Site 2's evidence is blocked with 403."""
        self.client.force_login(self.user_site_mgr)
        url = reverse("core:evidence_ocr_process", args=[self.evidence2.id])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.evidence2.ocr_runs.count(), 0)

        # Verify security audit log recorded
        audit = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.UNAUTHORIZED_ACCESS_ATTEMPT,
            resource_accessed=f"Evidence:{self.evidence2.id}/ocr/process",
        ).first()
        self.assertIsNotNone(audit)

    def test_auditor_read_only_strictly_enforced(self):
        """Auditor can inspect evidence and OCR, but CANNOT mutate or process OCR."""
        # 1. Auditor can view OCR status API
        self.client.force_login(self.user_auditor)
        status_url = reverse("core:evidence_ocr_status", args=[self.evidence1.id])
        resp = self.client.get(status_url)
        self.assertEqual(resp.status_code, 200)

        # 2. Auditor attempting POST to trigger OCR is blocked with 403 Forbidden
        process_url = reverse("core:evidence_ocr_process", args=[self.evidence1.id])
        resp = self.client.post(process_url)
        self.assertEqual(resp.status_code, 403)

    def test_subsidiary_manager_scope(self):
        self.client.force_login(self.user_sub_mgr)
        # Subsidiary manager manages Hydro Division (evidence1)
        url1 = reverse("core:evidence_ocr_process", args=[self.evidence1.id])
        resp1 = self.client.post(url1)
        self.assertEqual(resp1.status_code, 302)

        # But blocked from Solar Division (evidence2)
        url2 = reverse("core:evidence_ocr_process", args=[self.evidence2.id])
        resp2 = self.client.post(url2)
        self.assertEqual(resp2.status_code, 403)


class TestOCRViews(Phase11OCRBaseTestCase):
    """Tests for HTTP views, AJAX JSON responses, and inspection detail pages."""

    def setUp(self):
        super().setUp()
        self.client = Client()

    def test_ocr_process_post_ajax(self):
        self.client.force_login(self.user_site_mgr)
        url = reverse("core:evidence_ocr_process", args=[self.evidence1.id])
        resp = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "COMPLETED")
        self.assertEqual(data["run_number"], 1)
        self.assertIn("comparison", data)

    def test_ocr_status_api(self):
        self.client.force_login(self.user_site_mgr)
        url = reverse("core:evidence_ocr_status", args=[self.evidence1.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["has_run"])

        # Execute OCR
        execute_ocr_run(self.evidence1, user=self.user_site_mgr)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["has_run"])
        self.assertEqual(resp.json()["status"], "COMPLETED")

    def test_ocr_run_detail_view(self):
        run = execute_ocr_run(self.evidence1, user=self.user_site_mgr)
        self.client.force_login(self.user_site_mgr)
        url = reverse("core:ocr_run_detail", args=[self.evidence1.id, run.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f"OCR Run #{run.run_number}")
        self.assertContains(resp, "Document Text Content")

    def test_ocr_run_detail_idor_defense(self):
        run = execute_ocr_run(self.evidence2, user=self.user_other_site_mgr)
        self.client.force_login(self.user_site_mgr)
        # Site manager 1 attempting to view site 2's OCR run
        url = reverse("core:ocr_run_detail", args=[self.evidence2.id, run.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)

    def test_ocr_retry_view(self):
        run1 = execute_ocr_run(self.evidence1, user=self.user_site_mgr)
        self.client.force_login(self.user_site_mgr)
        url = reverse("core:ocr_run_retry", args=[self.evidence1.id, run1.id])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.evidence1.ocr_runs.count(), 2)
