"""
Comprehensive Phase 09 Test Suite — Evidence Management & Audit Traceability.

Covers:
1. Model instantiation, constraints, properties, and scope derivations.
2. File validation (extension allowlist, MIME check, magic byte verification, max size, zero-byte rejection, SHA-256 hash).
3. Role-Based Access Control (Site Manager, Subsidiary Manager, ESG Manager, Auditor, MEIL Operator).
4. Insecure Direct Object Reference (IDOR) defense and URL tampering.
5. Lifecycle state machine (draft deletion, submitted protection, retirement with audit justification).
6. Secure binary download & preview endpoints with object authorization.
7. Audit event lineage verification (AuthAuditLog).
"""

import io
from datetime import date
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.core.evidence_services import (
    create_evidence_record,
    delete_evidence_record,
    get_accessible_evidence,
    retire_evidence_record,
    user_can_access_evidence,
    user_can_delete_evidence,
    user_can_download_evidence,
    user_can_modify_activity_record,
    user_can_retire_evidence,
    user_can_upload_evidence,
    validate_evidence_file,
)
from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    ActivityRecord,
    AuthAuditLog,
    Company,
    Evidence,
    EvidenceStatus,
    EvidenceType,
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


class Phase09EvidenceBaseTestCase(TestCase):
    """Base setup establishing organizational hierarchy, roles, periods, and activities."""

    def setUp(self):
        # 1. Create Roles
        self.role_operator = Role.objects.create(code=Role.Code.MEIL_OPERATOR, name="MEIL Operator")
        self.role_esg = Role.objects.create(code=Role.Code.ESG_MANAGER, name="ESG Manager")
        self.role_sub_mgr = Role.objects.create(code=Role.Code.SUBSIDIARY_MANAGER, name="Subsidiary Manager")
        self.role_site_mgr = Role.objects.create(code=Role.Code.SITE_MANAGER, name="Site Manager")
        self.role_auditor = Role.objects.create(code=Role.Code.AUDITOR, name="Auditor")

        # 2. Create Users
        self.user_operator = User.objects.create_user(username="test_operator", password="password123")
        UserRole.objects.create(user=self.user_operator, role=self.role_operator, is_primary=True)

        self.user_esg = User.objects.create_user(username="test_esg", password="password123")
        UserRole.objects.create(user=self.user_esg, role=self.role_esg, is_primary=True)

        self.user_sub_mgr = User.objects.create_user(username="test_sub_mgr", password="password123")
        UserRole.objects.create(user=self.user_sub_mgr, role=self.role_sub_mgr, is_primary=True)

        self.user_site_mgr = User.objects.create_user(username="test_site_mgr", password="password123")
        UserRole.objects.create(user=self.user_site_mgr, role=self.role_site_mgr, is_primary=True)

        self.user_other_site_mgr = User.objects.create_user(username="test_other_site_mgr", password="password123")
        UserRole.objects.create(user=self.user_other_site_mgr, role=self.role_site_mgr, is_primary=True)

        self.user_auditor = User.objects.create_user(username="test_auditor", password="password123")
        UserRole.objects.create(user=self.user_auditor, role=self.role_auditor, is_primary=True)

        # 3. Create Organization Hierarchy
        self.company = Company.objects.create(
            name="MEIL Enterprise Group",
            code="MEIL-CORP",
            status=OrganizationStatus.ACTIVE,
        )
        self.subsidiary1 = Subsidiary.objects.create(
            company=self.company,
            name="Hydro Power Division",
            code="MEIL-HYDRO",
            status=OrganizationStatus.ACTIVE,
        )
        self.subsidiary2 = Subsidiary.objects.create(
            company=self.company,
            name="Solar Energy Division",
            code="MEIL-SOLAR",
            status=OrganizationStatus.ACTIVE,
        )

        self.project1 = Project.objects.create(
            subsidiary=self.subsidiary1,
            name="Polavaram Hydro Project",
            code="PRJ-POL",
            status=OrganizationStatus.ACTIVE,
        )
        self.project2 = Project.objects.create(
            subsidiary=self.subsidiary2,
            name="Kurnool Solar Park",
            code="PRJ-KRN",
            status=OrganizationStatus.ACTIVE,
        )

        self.site1 = Site.objects.create(
            project=self.project1,
            name="Dam Inflow Site 01",
            code="SITE-POL-01",
            status=OrganizationStatus.ACTIVE,
        )
        self.site2 = Site.objects.create(
            project=self.project2,
            name="Inverter Yard Site 02",
            code="SITE-KRN-02",
            status=OrganizationStatus.ACTIVE,
        )

        # Assignments
        SiteAssignment.objects.create(user=self.user_site_mgr, site=self.site1)
        SiteAssignment.objects.create(user=self.user_other_site_mgr, site=self.site2)
        SubsidiaryAssignment.objects.create(user=self.user_sub_mgr, subsidiary=self.subsidiary1)

        # 4. Reporting Period
        self.open_period = ReportingPeriod.objects.create(
            company=self.company,
            code="FY2025-26",
            name="FY 2025-26 Annual ESG Cycle",
            fiscal_year="FY2025-26",
            start_date=date(2025, 4, 1),
            end_date=date(2026, 3, 31),
            status=PeriodStatus.OPEN,
        )

        self.closed_period = ReportingPeriod.objects.create(
            company=self.company,
            code="FY2024-25",
            name="FY 2024-25 Historic Cycle",
            fiscal_year="FY2024-25",
            start_date=date(2024, 4, 1),
            end_date=date(2025, 3, 31),
            status=PeriodStatus.CLOSED,
        )

        # 5. Activity Master Catalog
        self.cat_energy = ActivityCategory.objects.create(
            code="ENERGY",
            name="Stationary & Mobile Fuels",
            display_order=1,
            status=OrganizationStatus.ACTIVE,
        )
        self.unit_litres = UnitOfMeasure.objects.create(
            code="LITRE",
            name="Liters",
            symbol="L",
            dimension="VOLUME",
        )
        self.activity_diesel = ActivityMaster.objects.create(
            code="FUEL-DIESEL",
            name="Stationary Diesel Generator Consumption",
            category=self.cat_energy,
            activity_type="Stationary Combustion",
            base_unit=self.unit_litres,
            scope_classification=ScopeClassification.SCOPE_1,
            status=OrganizationStatus.ACTIVE,
        )

        # 6. Activity Record on Site 1
        self.record1 = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.open_period,
            activity=self.activity_diesel,
            measurement_date=date(2025, 6, 15),
            quantity=1500.0,
            unit=self.unit_litres,
            status=RecordStatus.DRAFT,
            created_by=self.user_site_mgr,
        )

        # Record on Site 2 (Foreign to user_site_mgr)
        self.record2 = ActivityRecord.objects.create(
            site=self.site2,
            reporting_period=self.open_period,
            activity=self.activity_diesel,
            measurement_date=date(2025, 6, 20),
            quantity=800.0,
            unit=self.unit_litres,
            status=RecordStatus.DRAFT,
            created_by=self.user_other_site_mgr,
        )

    def _create_sample_pdf(self, content=b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"):
        return SimpleUploadedFile(
            "sample_tax_invoice.pdf",
            content,
            content_type="application/pdf",
        )

    def _create_sample_png(self):
        # PNG signature
        content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        return SimpleUploadedFile(
            "meter_photo.png",
            content,
            content_type="image/png",
        )


class EvidenceModelAndValidationTests(Phase09EvidenceBaseTestCase):
    """Tests model instantiation, validation rules, constraints, and helpers."""

    def test_valid_evidence_creation(self):
        """Creates a valid Evidence record and verifies file metadata, hash, and status."""
        pdf_file = self._create_sample_pdf()
        evidence = create_evidence_record(
            activity_record=self.record1,
            uploaded_file=pdf_file,
            evidence_type=EvidenceType.INVOICE,
            description="Indian Oil Corporation delivery invoice INV-001",
            user=self.user_site_mgr,
        )

        self.assertEqual(evidence.activity_record, self.record1)
        self.assertEqual(evidence.evidence_type, EvidenceType.INVOICE)
        self.assertEqual(evidence.original_filename, "sample_tax_invoice.pdf")
        self.assertEqual(evidence.status, EvidenceStatus.ACTIVE)
        self.assertTrue(len(evidence.file_hash) == 64)  # SHA-256
        self.assertEqual(evidence.uploaded_by, self.user_site_mgr)
        self.assertTrue(evidence.is_active)
        self.assertFalse(evidence.is_retired)
        self.assertTrue(evidence.is_pdf)
        self.assertTrue(evidence.is_previewable)
        self.assertIn("B", evidence.file_size_formatted)

    def test_evidence_organizational_scope_derivation(self):
        """Verifies derived properties company, subsidiary, project, site, reporting_period."""
        pdf_file = self._create_sample_pdf()
        evidence = create_evidence_record(
            activity_record=self.record1,
            uploaded_file=pdf_file,
            evidence_type=EvidenceType.FUEL_CHALLAN,
            user=self.user_site_mgr,
        )

        self.assertEqual(evidence.site, self.site1)
        self.assertEqual(evidence.project, self.project1)
        self.assertEqual(evidence.subsidiary, self.subsidiary1)
        self.assertEqual(evidence.company, self.company)
        self.assertEqual(evidence.reporting_period, self.open_period)

    def test_multiple_evidence_files_per_record(self):
        """Verifies attaching multiple supporting documents to a single ActivityRecord."""
        pdf_file = self._create_sample_pdf()
        png_file = self._create_sample_png()

        ev1 = create_evidence_record(self.record1, pdf_file, EvidenceType.INVOICE, user=self.user_site_mgr)
        ev2 = create_evidence_record(self.record1, png_file, EvidenceType.METER_READING, user=self.user_site_mgr)

        self.assertEqual(self.record1.evidence_files.count(), 2)
        self.assertEqual(self.record1.evidence_count, 2)
        self.assertTrue(self.record1.has_evidence)
        self.assertIn(ev1, self.record1.evidence_files.all())
        self.assertIn(ev2, self.record1.evidence_files.all())

    def test_unsupported_file_extension_rejected(self):
        """Verifies rejected executable or non-allowlisted file formats."""
        bad_file = SimpleUploadedFile("script.py", b"print('malicious')", content_type="text/x-python")
        with self.assertRaises(ValidationError) as ctx:
            validate_evidence_file(bad_file)
        self.assertIn("not supported", str(ctx.exception))

        exe_file = SimpleUploadedFile("virus.exe", b"MZ\x90\x00", content_type="application/octet-stream")
        with self.assertRaises(ValidationError) as ctx:
            validate_evidence_file(exe_file)
        self.assertIn("not supported", str(ctx.exception))

    def test_empty_zero_byte_file_rejected(self):
        """Verifies 0-byte uploads are rejected."""
        empty_file = SimpleUploadedFile("empty.pdf", b"", content_type="application/pdf")
        with self.assertRaises(ValidationError) as ctx:
            validate_evidence_file(empty_file)
        self.assertIn("empty", str(ctx.exception).lower())

    def test_magic_byte_mismatch_rejected(self):
        """Verifies spoofed file header signatures are caught."""
        fake_pdf = SimpleUploadedFile("fake.pdf", b"This is plain text, not a PDF!", content_type="application/pdf")
        with self.assertRaises(ValidationError) as ctx:
            validate_evidence_file(fake_pdf)
        self.assertIn("not contain a valid PDF signature", str(ctx.exception))

    def test_oversized_file_rejected(self):
        """Verifies file size exceeding maximum limit is rejected."""
        # Create a mock file object with size > 25MB
        oversized = SimpleUploadedFile("huge.pdf", b"%PDF-1.4 dummy", content_type="application/pdf")
        oversized.size = 26 * 1024 * 1024
        with self.assertRaises(ValidationError) as ctx:
            validate_evidence_file(oversized)
        self.assertIn("exceeds maximum permitted limit", str(ctx.exception))

    def test_evidence_retirement_lifecycle(self):
        """Verifies retirement changes status to RETIRED and requires audit justification."""
        pdf_file = self._create_sample_pdf()
        evidence = create_evidence_record(self.record1, pdf_file, EvidenceType.INVOICE, user=self.user_site_mgr)

        # Attempt retirement without reason
        with self.assertRaises(ValidationError):
            retire_evidence_record(evidence, self.user_site_mgr, reason="")

        # Valid retirement
        retire_evidence_record(evidence, self.user_site_mgr, reason="Superseded by revised invoice INV-001-B")
        evidence.refresh_from_db()
        self.assertEqual(evidence.status, EvidenceStatus.RETIRED)
        self.assertTrue(evidence.is_retired)
        self.assertEqual(evidence.retired_by, self.user_site_mgr)
        self.assertIsNotNone(evidence.retired_at)
        self.assertEqual(evidence.retirement_reason, "Superseded by revised invoice INV-001-B")
        self.assertEqual(self.record1.evidence_count, 0)  # active count decreases
        self.assertEqual(self.record1.total_evidence_count, 1)

    def test_draft_evidence_deletion_allowed(self):
        """Verifies that evidence for a DRAFT activity record can be deleted."""
        pdf_file = self._create_sample_pdf()
        evidence = create_evidence_record(self.record1, pdf_file, EvidenceType.INVOICE, user=self.user_site_mgr)
        ev_id = evidence.id

        delete_evidence_record(evidence, self.user_site_mgr)
        self.assertFalse(Evidence.objects.filter(id=ev_id).exists())

    def test_submitted_evidence_deletion_forbidden(self):
        """Verifies that evidence cannot be hard-deleted once record is submitted or ready."""
        pdf_file = self._create_sample_pdf()
        evidence = create_evidence_record(self.record1, pdf_file, EvidenceType.INVOICE, user=self.user_site_mgr)

        # Transition record to READY
        self.record1.status = RecordStatus.READY
        self.record1.save()

        self.assertFalse(user_can_delete_evidence(self.user_site_mgr, evidence))
        with self.assertRaises(PermissionDenied):
            delete_evidence_record(evidence, self.user_site_mgr)


class EvidencePermissionsAndIDORTests(Phase09EvidenceBaseTestCase):
    """Tests server-side scoping, role enforcement, and anti-IDOR defense."""

    def setUp(self):
        super().setUp()
        self.client = Client()

        # Seed an evidence document on site 1
        self.ev1 = create_evidence_record(
            self.record1,
            self._create_sample_pdf(),
            EvidenceType.INVOICE,
            user=self.user_site_mgr,
        )

        # Seed an evidence document on site 2 (foreign to site_mgr)
        self.ev2 = create_evidence_record(
            self.record2,
            self._create_sample_png(),
            EvidenceType.METER_READING,
            user=self.user_other_site_mgr,
        )

    def test_site_manager_scoped_queryset(self):
        """Site Manager sees strictly evidence from assigned sites."""
        qs = get_accessible_evidence(self.user_site_mgr)
        self.assertIn(self.ev1, qs)
        self.assertNotIn(self.ev2, qs)

    def test_auditor_universal_read_only(self):
        """Auditor can view and download all evidence but cannot upload or retire."""
        qs = get_accessible_evidence(self.user_auditor)
        self.assertIn(self.ev1, qs)
        self.assertIn(self.ev2, qs)

        self.assertTrue(user_can_access_evidence(self.user_auditor, self.ev1))
        self.assertTrue(user_can_download_evidence(self.user_auditor, self.ev1))
        self.assertFalse(user_can_upload_evidence(self.user_auditor, self.record1))
        self.assertFalse(user_can_retire_evidence(self.user_auditor, self.ev1))
        self.assertFalse(user_can_delete_evidence(self.user_auditor, self.ev1))

    def test_site_manager_idor_direct_access_forbidden(self):
        """Site Manager attempting direct access to unassigned evidence returns 403 Forbidden."""
        self.client.force_login(self.user_site_mgr)

        # Direct detail inspection of foreign evidence
        resp = self.client.get(reverse("core:evidence_detail", kwargs={"evidence_id": self.ev2.id}))
        self.assertEqual(resp.status_code, 403)

        # Direct download of foreign evidence
        resp = self.client.get(reverse("core:evidence_download", kwargs={"evidence_id": self.ev2.id}))
        self.assertEqual(resp.status_code, 403)

        # Direct preview of foreign evidence
        resp = self.client.get(reverse("core:evidence_preview", kwargs={"evidence_id": self.ev2.id}))
        self.assertEqual(resp.status_code, 403)

        # Direct retire attempt of foreign evidence
        resp = self.client.get(reverse("core:evidence_retire", kwargs={"evidence_id": self.ev2.id}))
        self.assertEqual(resp.status_code, 403)

        # Direct upload to foreign record
        resp = self.client.get(reverse("core:evidence_upload", kwargs={"record_id": self.record2.id}))
        self.assertEqual(resp.status_code, 403)

    def test_site_manager_upload_happy_path(self):
        """Site Manager can upload evidence to assigned activity record."""
        self.client.force_login(self.user_site_mgr)
        url = reverse("core:evidence_upload", kwargs={"record_id": self.record1.id})

        new_file = self._create_sample_png()
        data = {
            "evidence_type": EvidenceType.METER_READING,
            "file": new_file,
            "description": "Morning turbine meter telemetry snap",
        }
        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 302)  # Redirects to record detail

        # Check evidence was created
        created = Evidence.objects.filter(description="Morning turbine meter telemetry snap").first()
        self.assertIsNotNone(created)
        self.assertEqual(created.activity_record, self.record1)

    def test_download_endpoint_streams_file_with_audit_log(self):
        """Authorized download streams binary file and records AuthAuditLog event."""
        self.client.force_login(self.user_site_mgr)
        url = reverse("core:evidence_download", kwargs={"evidence_id": self.ev1.id})

        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('attachment; filename="sample_tax_invoice.pdf"', resp.headers.get("Content-Disposition", ""))

        # Verify audit log
        audit = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.EVIDENCE_DOWNLOADED,
            user=self.user_site_mgr,
        ).first()
        self.assertIsNotNone(audit)

    def test_unauthenticated_access_redirects_to_login(self):
        """Unauthenticated requests to evidence endpoints redirect to login."""
        endpoints = [
            reverse("core:evidence_list"),
            reverse("core:evidence_detail", kwargs={"evidence_id": self.ev1.id}),
            reverse("core:evidence_download", kwargs={"evidence_id": self.ev1.id}),
            reverse("core:evidence_preview", kwargs={"evidence_id": self.ev1.id}),
            reverse("core:evidence_upload", kwargs={"record_id": self.record1.id}),
        ]
        for url in endpoints:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302)
            self.assertIn("/auth/login/", resp.url)

    def test_upload_to_closed_period_blocked(self):
        """Uploading evidence to an activity record in a closed reporting period is blocked."""
        # Create a record in closed period
        closed_rec = ActivityRecord.objects.create(
            site=self.site1,
            reporting_period=self.closed_period,
            activity=self.activity_diesel,
            measurement_date=date(2024, 6, 15),
            quantity=500.0,
            unit=self.unit_litres,
            status=RecordStatus.DRAFT,
            created_by=self.user_site_mgr,
        )

        self.assertFalse(user_can_upload_evidence(self.user_site_mgr, closed_rec))
        self.client.force_login(self.user_site_mgr)
        resp = self.client.get(reverse("core:evidence_upload", kwargs={"record_id": closed_rec.id}))
        self.assertEqual(resp.status_code, 403)
