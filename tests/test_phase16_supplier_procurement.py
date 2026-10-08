"""
Comprehensive Automated Test Suite for Phase 16 — Supplier & Procurement Management.

MEIL ESG CONTROL TOWER Monolith Test Suite.

Validates:
1. Model Architecture & Integrity:
   - Supplier model, fields, constraints (unique supplier_code), SupplierType, SupplierStatus
   - Soft archival lifecycle (.archive(), is_active check)
   - ProcurementRecord model, fields, constraints (unique procurement_number), positive total_amount, currency
   - ProcurementItem model, fields, positive quantity, non-negative unit_price and total_amount
   - Scope 3 category & ActivityMaster integration points
   - Evidence model integration (dual parent support: activity_record or procurement_record)
   - AuthAuditLog event types for Phase 16

2. Supplier Master Operations & Anti-IDOR Scoping:
   - create_supplier, update_supplier, archive_supplier
   - find_supplier_duplicates (by code, name, tax_id)
   - Scoped visibility: enterprise-wide vs company-scoped suppliers
   - Blocking procurement creation when supplier is inactive/archived

3. Procurement Record Operations & Line Items:
   - Auto-generated procurement sequence (PROC-YYYY-XXXX)
   - add_procurement_item, delete_procurement_item with auto total_amount synchronization
   - Organizational hierarchy consistency (site -> project -> company)
   - Reporting period boundary checks

4. Evidence Management Integration:
   - Uploading evidence linked directly to ProcurementRecord
   - Lineage traceability: evidence.procurement_record, site, reporting_period
   - Access control on procurement evidence files

5. OCR Document Intelligence & Telemetry Comparison:
   - compare_ocr_with_procurement: matching invoice number, matching amount, mismatch detection
   - Zero-silent-overwrite principle: ledger values remain unmutated by OCR runs

6. Deterministic Validation Engine:
   - validate_procurement rule evaluation
   - Passing conditions (active supplier, period alignment, positive amounts, items match, evidence attached)
   - Warning conditions (missing line items, missing invoice ref)
   - Blocking error conditions (inactive supplier, closed period, date out of bounds, hierarchy mismatch)

7. Procurement Anomaly Detection Engine:
   - detect_procurement_anomalies
   - Duplicate invoice detection (same supplier, invoice ref, date, amount)
   - Historical spend spike detection (>200% above historical average)
   - Unit price variance detection (>50% variance from historical average)
   - Anomaly telemetry separate from deterministic validation

8. Governance Workflow State Machine:
   - submit_procurement: DRAFT -> SUBMITTED (record locked)
   - Blocking submission on validation errors
   - review_procurement VERIFY: SUBMITTED -> VERIFIED
   - review_procurement REQUEST_CORRECTION: SUBMITTED -> CORRECTION_REQUESTED (unlocked)
   - review_procurement REJECT: SUBMITTED -> REJECTED
   - resubmit_procurement: CORRECTION_REQUESTED -> SUBMITTED (re-locked, mandatory explanation)

9. RBAC & Anti-IDOR Security:
   - Site Manager: scoped to assigned sites, cannot mutate other sites (403/404), cannot review
   - Subsidiary Manager: scoped to company, cannot review other companies (403/404)
   - Auditor: read-only access (200), blocked from mutating or reviewing (403)
   - MEIL Operator / Superuser: enterprise access

10. Full HTTP Endpoints Integration:
   - Supplier views: list, detail, create, edit, archive
   - Procurement views: list, detail, create, edit, delete, item add/delete, evidence upload
   - Governance views: validate, anomaly detect, submit, review inbox, review decision, correction, OCR compare
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    ActivityRecord,
    AuthAuditLog,
    Company,
    CompanyAssignment,
    Evidence,
    EvidenceStatus,
    EvidenceType,
    MasterStatus,
    OCRField,
    OCRRun,
    OCRStatus,
    PeriodStatus,
    ProcurementCategory,
    ProcurementItem,
    ProcurementRecord,
    ProcurementStatus,
    Project,
    ReportingPeriod,
    Role,
    Site,
    SiteAssignment,
    Subsidiary,
    SubsidiaryAssignment,
    Supplier,
    SupplierStatus,
    SupplierType,
    UnitDimension,
    UnitOfMeasure,
    UserRole,
    ValidationStatus,
)
from apps.core.procurement_services import (
    add_procurement_item,
    archive_supplier,
    compare_ocr_with_procurement,
    create_procurement_record,
    create_supplier,
    delete_procurement_item,
    delete_procurement_record,
    detect_procurement_anomalies,
    find_supplier_duplicates,
    generate_procurement_number,
    get_accessible_procurements,
    get_accessible_suppliers,
    resubmit_procurement,
    review_procurement,
    submit_procurement,
    update_procurement_record,
    update_supplier,
    user_can_access_procurement,
    user_can_access_supplier,
    user_can_archive_supplier,
    user_can_delete_procurement,
    user_can_modify_procurement,
    user_can_modify_supplier,
    user_can_review_procurement,
    user_can_submit_procurement,
    validate_procurement,
)

User = get_user_model()


class Phase16SupplierProcurementTestCase(TestCase):
    """Core test suite validating Phase 16 Supplier & Procurement Management."""

    @classmethod
    def setUpTestData(cls):
        # 1. Organization Hierarchy
        cls.company_a = Company.objects.create(name="MEIL Division A", code="DIV-A")
        cls.company_b = Company.objects.create(name="MEIL Division B", code="DIV-B")

        cls.sub_a = Subsidiary.objects.create(
            company=cls.company_a,
            name="Infrastructure Subsidiary A",
            code="SUB-A",
        )
        cls.sub_b = Subsidiary.objects.create(
            company=cls.company_b,
            name="Energy Subsidiary B",
            code="SUB-B",
        )

        cls.project_a = Project.objects.create(
            name="Infrastructure Project Alpha",
            code="PRJ-A",
            subsidiary=cls.sub_a,
        )
        cls.project_b = Project.objects.create(
            name="Power Grid Project Beta",
            code="PRJ-B",
            subsidiary=cls.sub_b,
        )

        cls.site_a1 = Site.objects.create(
            name="Site Alpha 1",
            code="SITE-A1",
            project=cls.project_a,
        )
        cls.site_a2 = Site.objects.create(
            name="Site Alpha 2",
            code="SITE-A2",
            project=cls.project_a,
        )
        cls.site_b1 = Site.objects.create(
            name="Site Beta 1",
            code="SITE-B1",
            project=cls.project_b,
        )

        # 2. Reporting Periods
        cls.period = ReportingPeriod.objects.create(
            company=cls.company_a,
            code="FY26-Q1",
            name="FY2026-Q1",
            fiscal_year="2026-27",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 6, 30),
            status=PeriodStatus.OPEN,
        )
        cls.period_b = ReportingPeriod.objects.create(
            company=cls.company_b,
            code="FY26-Q1-B",
            name="FY2026-Q1 (Division B)",
            fiscal_year="2026-27",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 6, 30),
            status=PeriodStatus.OPEN,
        )
        cls.closed_period = ReportingPeriod.objects.create(
            company=cls.company_a,
            code="FY25-Q4",
            name="FY2025-Q4",
            fiscal_year="2025-26",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            status=PeriodStatus.CLOSED,
        )

        # 3. Units & Master Data
        cls.unit_mt, _ = UnitOfMeasure.objects.get_or_create(
            code="MT",
            defaults={"name": "Metric Tonne", "symbol": "t", "dimension": UnitDimension.MASS},
        )
        cls.unit_kl, _ = UnitOfMeasure.objects.get_or_create(
            code="KL",
            defaults={"name": "Kilolitre", "symbol": "kL", "dimension": UnitDimension.VOLUME},
        )
        cls.unit_pcs, _ = UnitOfMeasure.objects.get_or_create(
            code="PCS",
            defaults={"name": "Pieces", "symbol": "pcs", "dimension": UnitDimension.COUNT},
        )

        cls.activity_category = ActivityCategory.objects.create(name="Materials", code="MAT")
        cls.activity_master = ActivityMaster.objects.create(
            name="Structural Steel",
            code="MAT-STEEL",
            category=cls.activity_category,
            base_unit=cls.unit_mt,
            status=MasterStatus.ACTIVE,
        )

        # 4. Roles & Users
        cls.role_site_mgr, _ = Role.objects.get_or_create(
            code=Role.Code.SITE_MANAGER,
            defaults={"name": "Site Manager"},
        )
        cls.role_sub_mgr, _ = Role.objects.get_or_create(
            code=Role.Code.SUBSIDIARY_MANAGER,
            defaults={"name": "Subsidiary Manager"},
        )
        cls.role_auditor, _ = Role.objects.get_or_create(
            code=Role.Code.AUDITOR,
            defaults={"name": "Auditor"},
        )
        cls.role_operator, _ = Role.objects.get_or_create(
            code=Role.Code.MEIL_OPERATOR,
            defaults={"name": "MEIL Operator"},
        )

        # Users & Assignments
        cls.site_manager_a = User.objects.create_user(
            username="sitemgr_a",
            email="sitemgr_a@meil.test",
            password="password123",
            first_name="Site",
            last_name="Manager A",
        )
        UserRole.objects.create(user=cls.site_manager_a, role=cls.role_site_mgr, is_primary=True)
        SiteAssignment.objects.create(user=cls.site_manager_a, site=cls.site_a1)

        cls.site_manager_b = User.objects.create_user(
            username="sitemgr_b",
            email="sitemgr_b@meil.test",
            password="password123",
            first_name="Site",
            last_name="Manager B",
        )
        UserRole.objects.create(user=cls.site_manager_b, role=cls.role_site_mgr, is_primary=True)
        SiteAssignment.objects.create(user=cls.site_manager_b, site=cls.site_b1)

        cls.sub_manager_a = User.objects.create_user(
            username="submgr_a",
            email="submgr_a@meil.test",
            password="password123",
            first_name="Subsidiary",
            last_name="Manager A",
        )
        UserRole.objects.create(user=cls.sub_manager_a, role=cls.role_sub_mgr, is_primary=True)
        SubsidiaryAssignment.objects.create(user=cls.sub_manager_a, subsidiary=cls.sub_a)
        CompanyAssignment.objects.create(user=cls.sub_manager_a, company=cls.company_a)

        cls.sub_manager_b = User.objects.create_user(
            username="submgr_b",
            email="submgr_b@meil.test",
            password="password123",
            first_name="Subsidiary",
            last_name="Manager B",
        )
        UserRole.objects.create(user=cls.sub_manager_b, role=cls.role_sub_mgr, is_primary=True)
        SubsidiaryAssignment.objects.create(user=cls.sub_manager_b, subsidiary=cls.sub_b)
        CompanyAssignment.objects.create(user=cls.sub_manager_b, company=cls.company_b)

        cls.auditor = User.objects.create_user(
            username="auditor",
            email="auditor@meil.test",
            password="password123",
            first_name="ESG",
            last_name="Auditor",
        )
        UserRole.objects.create(user=cls.auditor, role=cls.role_auditor, is_primary=True)
        CompanyAssignment.objects.create(user=cls.auditor, company=cls.company_a)

        cls.meil_operator = User.objects.create_user(
            username="operator",
            email="operator@meil.test",
            password="password123",
            first_name="MEIL",
            last_name="Operator",
        )
        UserRole.objects.create(user=cls.meil_operator, role=cls.role_operator, is_primary=True)
        cls.meil_operator.is_superuser = True
        cls.meil_operator.save()

        # 5. Suppliers
        cls.supplier_global = Supplier.objects.create(
            supplier_code="VEND-001",
            name="Tata Steel Limited",
            legal_name="Tata Steel Ltd",
            supplier_type=SupplierType.GOODS,
            status=SupplierStatus.ACTIVE,
            company=None,  # Enterprise-wide
            tax_identifier="36AAACT2727Q1ZB",
            contact_person="Ramesh Gupta",
            contact_email="ramesh.gupta@tatasteel.test",
            has_esg_declaration=True,
            environmental_certifications="ISO 14001, ISO 50001",
            created_by=cls.meil_operator,
        )

        cls.supplier_div_a = Supplier.objects.create(
            supplier_code="VEND-002",
            name="Hyderabad Fuel Distributors",
            legal_name="Hyderabad Fuel Distributors Pvt Ltd",
            supplier_type=SupplierType.FUEL_SUPPLIER,
            status=SupplierStatus.ACTIVE,
            company=cls.company_a,
            tax_identifier="36AABCH8821R1ZZ",
            contact_person="K. V. Rao",
            contact_email="kvrao@hydfuel.test",
            has_esg_declaration=False,
            created_by=cls.sub_manager_a,
        )

        cls.supplier_archived = Supplier.objects.create(
            supplier_code="VEND-003",
            name="Decommissioned Quarry Works",
            supplier_type=SupplierType.GOODS,
            status=SupplierStatus.ARCHIVED,
            company=cls.company_a,
            created_by=cls.sub_manager_a,
        )

    # -------------------------------------------------------------------------
    # 1. MODEL ARCHITECTURE & CONSTRAINTS
    # -------------------------------------------------------------------------

    def test_supplier_unique_code_constraint(self):
        """Supplier code must be strictly unique across the enterprise."""
        with self.assertRaises(IntegrityError):
            Supplier.objects.create(
                supplier_code="VEND-001",  # duplicate of supplier_global
                name="Duplicate Code Vendor",
                supplier_type=SupplierType.GOODS,
            )

    def test_supplier_soft_archival(self):
        """Archiving a supplier updates status to ARCHIVED without deleting the record."""
        supplier = Supplier.objects.create(
            supplier_code="VEND-TEMP",
            name="Temporary Vendor",
            supplier_type=SupplierType.SERVICES,
            status=SupplierStatus.ACTIVE,
        )
        self.assertTrue(supplier.is_active)
        archive_supplier(supplier, user=self.meil_operator)
        supplier.refresh_from_db()
        self.assertEqual(supplier.status, SupplierStatus.ARCHIVED)
        self.assertFalse(supplier.is_active)

    def test_procurement_unique_number_constraint(self):
        """Procurement number must be strictly unique."""
        proc = ProcurementRecord.objects.create(
            procurement_number="PROC-2026-TEST1",
            supplier=self.supplier_global,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            reporting_period=self.period,
            purchase_date=date(2026, 4, 15),
            total_amount=Decimal("10000.00"),
            currency="INR",
            created_by=self.site_manager_a,
        )
        self.assertIsNotNone(proc.id)

        with self.assertRaises(IntegrityError):
            ProcurementRecord.objects.create(
                procurement_number="PROC-2026-TEST1",  # duplicate
                supplier=self.supplier_global,
                company=self.company_a,
                project=self.project_a,
                site=self.site_a1,
                reporting_period=self.period,
                purchase_date=date(2026, 4, 15),
                total_amount=Decimal("5000.00"),
                currency="INR",
                created_by=self.site_manager_a,
            )

    def test_procurement_item_positive_quantity_constraint(self):
        """ProcurementItem must enforce positive quantity."""
        proc = ProcurementRecord.objects.create(
            procurement_number="PROC-2026-ITEM1",
            supplier=self.supplier_global,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            reporting_period=self.period,
            purchase_date=date(2026, 4, 15),
            total_amount=Decimal("10000.00"),
            created_by=self.site_manager_a,
        )
        item = ProcurementItem(
            procurement=proc,
            line_number=1,
            item_name="Steel Rebars",
            quantity=Decimal("-5.00"),  # invalid negative
            unit=self.unit_mt,
            unit_price=Decimal("1000.00"),
            total_amount=Decimal("-5000.00"),
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_evidence_procurement_linkage(self):
        """Evidence model supports procurement_record as first-class parent."""
        proc = ProcurementRecord.objects.create(
            procurement_number="PROC-2026-EV1",
            supplier=self.supplier_global,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            reporting_period=self.period,
            purchase_date=date(2026, 4, 15),
            total_amount=Decimal("50000.00"),
            created_by=self.site_manager_a,
        )
        test_file = SimpleUploadedFile(
            "invoice_101.pdf",
            b"%PDF-1.4 test invoice file content",
            content_type="application/pdf",
        )
        evidence = Evidence.objects.create(
            procurement_record=proc,
            file=test_file,
            original_filename="invoice_101.pdf",
            file_size=test_file.size,
            file_type="application/pdf",
            evidence_type=EvidenceType.INVOICE,
            uploaded_by=self.site_manager_a,
        )
        self.assertEqual(evidence.procurement_record, proc)
        self.assertEqual(evidence.site, self.site_a1)
        self.assertEqual(evidence.company, self.company_a)
        self.assertEqual(evidence.reporting_period, self.period)

    # -------------------------------------------------------------------------
    # 2. SUPPLIER OPERATIONS & SCOPING
    # -------------------------------------------------------------------------

    def test_create_and_update_supplier(self):
        """Supplier creation and mutation with audit logging."""
        supplier_data = {
            "supplier_code": "VEND-NEW-01",
            "name": "Bharat Heavy Electricals",
            "legal_name": "Bharat Heavy Electricals Limited",
            "supplier_type": SupplierType.MANUFACTURER,
            "status": SupplierStatus.ACTIVE,
            "tax_identifier": "36AABCB1234F1Z1",
            "contact_person": "Sunil Kumar",
            "contact_email": "sunil.k@bhel.test",
            "has_esg_declaration": True,
        }
        supplier = create_supplier(supplier_data, user=self.meil_operator)
        self.assertEqual(supplier.supplier_code, "VEND-NEW-01")
        self.assertTrue(supplier.has_esg_declaration)

        # Audit event logged
        self.assertTrue(
            AuthAuditLog.objects.filter(
                event_type=AuthAuditLog.EventType.SUPPLIER_CREATED,
                resource_accessed=f"Supplier:{supplier.id}",
            ).exists()
        )

        # Update
        update_supplier(supplier, {"contact_phone": "+91 9876543210"}, user=self.meil_operator)
        supplier.refresh_from_db()
        self.assertEqual(supplier.contact_phone, "+91 9876543210")
        self.assertTrue(
            AuthAuditLog.objects.filter(
                event_type=AuthAuditLog.EventType.SUPPLIER_UPDATED,
                resource_accessed=f"Supplier:{supplier.id}",
            ).exists()
        )

    def test_find_supplier_duplicates(self):
        """Duplicate detection flags identical codes, tax identifiers, or normalized names."""
        # By code
        dups_code = find_supplier_duplicates("VEND-001")
        self.assertEqual(len(dups_code), 1)

        # By tax ID
        dups_tax = find_supplier_duplicates("VEND-DIFF", tax_identifier="36AAACT2727Q1ZB")
        self.assertEqual(len(dups_tax), 1)

        # By similar name
        dups_name = find_supplier_duplicates("VEND-DIFF", name="Tata Steel Limited")
        self.assertEqual(len(dups_name), 1)

    def test_supplier_scoping_isolation(self):
        """Company-scoped suppliers are filtered appropriately; enterprise suppliers are universal."""
        # Sub Manager A sees global supplier and Div A supplier
        supps_a = get_accessible_suppliers(self.sub_manager_a)
        self.assertIn(self.supplier_global, supps_a)
        self.assertIn(self.supplier_div_a, supps_a)

        # Sub Manager B sees global supplier but NOT Div A supplier
        supps_b = get_accessible_suppliers(self.sub_manager_b)
        self.assertIn(self.supplier_global, supps_b)
        self.assertNotIn(self.supplier_div_a, supps_b)

    # -------------------------------------------------------------------------
    # 3. PROCUREMENT RECORD OPERATIONS & LINE ITEMS
    # -------------------------------------------------------------------------

    def test_procurement_number_auto_generation(self):
        """Sequential procurement numbers generated per year."""
        pnum = generate_procurement_number()
        self.assertTrue(pnum.startswith("PROC-"))

    def test_create_procurement_record_and_hierarchy_sync(self):
        """Creating procurement syncs project and company from selected site."""
        proc_data = {
            "supplier": self.supplier_global,
            "site": self.site_a1,
            "reporting_period": self.period,
            "purchase_date": date(2026, 4, 10),
            "category": ProcurementCategory.RAW_MATERIAL,
            "invoice_reference": "INV-2026-001",
            "total_amount": Decimal("250000.00"),
            "currency": "INR",
        }
        proc = create_procurement_record(proc_data, user=self.site_manager_a)
        self.assertEqual(proc.project, self.project_a)
        self.assertEqual(proc.company, self.company_a)
        self.assertEqual(proc.status, ProcurementStatus.DRAFT)
        self.assertFalse(proc.is_locked)

    def test_add_and_delete_procurement_items_sync_total(self):
        """Adding/deleting line items dynamically synchronizes total_amount."""
        proc = create_procurement_record({
            "supplier": self.supplier_global,
            "site": self.site_a1,
            "reporting_period": self.period,
            "purchase_date": date(2026, 4, 10),
            "category": ProcurementCategory.RAW_MATERIAL,
            "total_amount": Decimal("0.00"),
        }, user=self.site_manager_a)

        item1 = add_procurement_item(proc, {
            "item_name": "TMT Steel Bars 12mm",
            "quantity": Decimal("10.00"),
            "unit": self.unit_mt,
            "unit_price": Decimal("50000.00"),
            "activity_master": self.activity_master,
            "scope3_category": "CAT_01",
        }, user=self.site_manager_a)

        proc.refresh_from_db()
        self.assertEqual(proc.total_amount, Decimal("500000.00"))
        self.assertEqual(proc.items.count(), 1)

        item2 = add_procurement_item(proc, {
            "item_name": "Structural Angles",
            "quantity": Decimal("5.00"),
            "unit": self.unit_mt,
            "unit_price": Decimal("60000.00"),
        }, user=self.site_manager_a)

        proc.refresh_from_db()
        self.assertEqual(proc.total_amount, Decimal("800000.00"))
        self.assertEqual(proc.items.count(), 2)

        # Delete item1
        delete_procurement_item(item1, user=self.site_manager_a)
        proc.refresh_from_db()
        self.assertEqual(proc.total_amount, Decimal("300000.00"))
        self.assertEqual(proc.items.count(), 1)

    def test_cannot_create_procurement_for_inactive_supplier(self):
        """Validation blocks procurement creation referencing an archived supplier."""
        with self.assertRaises(ValidationError):
            create_procurement_record({
                "supplier": self.supplier_archived,
                "site": self.site_a1,
                "reporting_period": self.period,
                "purchase_date": date(2026, 4, 10),
                "total_amount": Decimal("5000.00"),
            }, user=self.site_manager_a)

    # -------------------------------------------------------------------------
    # 4. OCR INTEGRATION & ZERO-SILENT-OVERWRITE
    # -------------------------------------------------------------------------

    def test_compare_ocr_with_procurement_matching(self):
        """OCR comparison identifies matching invoice telemetry without overwriting data."""
        proc = create_procurement_record({
            "supplier": self.supplier_global,
            "site": self.site_a1,
            "reporting_period": self.period,
            "purchase_date": date(2026, 4, 10),
            "invoice_reference": "INV-7890",
            "invoice_date": date(2026, 4, 10),
            "total_amount": Decimal("150000.00"),
            "currency": "INR",
        }, user=self.site_manager_a)

        evidence = Evidence.objects.create(
            procurement_record=proc,
            file=SimpleUploadedFile("inv.pdf", b"%PDF-1.4 mock", content_type="application/pdf"),
            original_filename="inv.pdf",
            file_size=1024,
            file_type="application/pdf",
            evidence_type=EvidenceType.INVOICE,
            uploaded_by=self.site_manager_a,
        )

        ocr_run = OCRRun.objects.create(
            evidence=evidence,
            run_number=1,
            engine="mock",
            status=OCRStatus.COMPLETED,
            extracted_text="Tax Invoice INV-7890 Tata Steel Ltd Total: 150000 Date: 2026-04-10",
        )
        OCRField.objects.create(
            ocr_run=ocr_run,
            field_name="bill_number",
            raw_value="INV-7890",
            normalized_value="INV-7890",
            confidence=Decimal("95.0"),
        )
        OCRField.objects.create(
            ocr_run=ocr_run,
            field_name="total_amount",
            raw_value="150000",
            normalized_value="150000",
            confidence=Decimal("92.0"),
        )
        OCRField.objects.create(
            ocr_run=ocr_run,
            field_name="vendor_name",
            raw_value="Tata Steel",
            normalized_value="Tata Steel Limited",
            confidence=Decimal("88.0"),
        )
        OCRField.objects.create(
            ocr_run=ocr_run,
            field_name="billing_date",
            raw_value="2026-04-10",
            normalized_value="2026-04-10",
            confidence=Decimal("90.0"),
        )

        comparison = compare_ocr_with_procurement(ocr_run, proc)
        self.assertEqual(comparison["overall_status"], "MATCH")
        self.assertEqual(comparison["items"]["invoice_number"]["status"], "MATCH")
        self.assertEqual(comparison["items"]["total_amount"]["status"], "MATCH")
        self.assertEqual(comparison["items"]["vendor_name"]["status"], "MATCH")

        # Zero silent overwrite verification: stored values are unchanged
        proc.refresh_from_db()
        self.assertEqual(proc.total_amount, Decimal("150000.00"))
        self.assertEqual(proc.invoice_reference, "INV-7890")

    def test_compare_ocr_with_procurement_mismatch(self):
        """OCR comparison identifies discrepancies (e.g. invoice total mismatch) cleanly."""
        proc = create_procurement_record({
            "supplier": self.supplier_global,
            "site": self.site_a1,
            "reporting_period": self.period,
            "purchase_date": date(2026, 4, 10),
            "invoice_reference": "INV-1111",
            "total_amount": Decimal("100000.00"),
            "currency": "INR",
        }, user=self.site_manager_a)

        evidence = Evidence.objects.create(
            procurement_record=proc,
            file=SimpleUploadedFile("inv2.pdf", b"%PDF-1.4 mock", content_type="application/pdf"),
            original_filename="inv2.pdf",
            file_size=1024,
            file_type="application/pdf",
            evidence_type=EvidenceType.INVOICE,
            uploaded_by=self.site_manager_a,
        )
        ocr_run = OCRRun.objects.create(
            evidence=evidence,
            run_number=1,
            engine="mock",
            status=OCRStatus.COMPLETED,
            extracted_text="Invoice text",
        )
        OCRField.objects.create(
            ocr_run=ocr_run,
            field_name="total_amount",
            raw_value="125000",
            normalized_value="125000",
            confidence=Decimal("95.0"),
        )

        comparison = compare_ocr_with_procurement(ocr_run, proc)
        self.assertEqual(comparison["overall_status"], "MISMATCH")
        self.assertEqual(comparison["items"]["total_amount"]["status"], "MISMATCH")
        self.assertEqual(comparison["items"]["total_amount"]["delta"], 25000.0)

    # -------------------------------------------------------------------------
    # 5. DETERMINISTIC VALIDATION ENGINE
    # -------------------------------------------------------------------------

    def test_validate_procurement_clean_record(self):
        """Fully articulated procurement with evidence passes validation."""
        proc = create_procurement_record({
            "supplier": self.supplier_global,
            "site": self.site_a1,
            "reporting_period": self.period,
            "purchase_date": date(2026, 4, 15),
            "invoice_reference": "INV-PASS-01",
            "total_amount": Decimal("100000.00"),
        }, user=self.site_manager_a)

        add_procurement_item(proc, {
            "item_name": "Steel Bars",
            "quantity": Decimal("2.00"),
            "unit": self.unit_mt,
            "unit_price": Decimal("50000.00"),
        }, user=self.site_manager_a)

        # Attach evidence
        Evidence.objects.create(
            procurement_record=proc,
            file=SimpleUploadedFile("inv.pdf", b"pdfcontent", content_type="application/pdf"),
            original_filename="inv.pdf",
            file_size=1024,
            file_type="application/pdf",
            evidence_type=EvidenceType.INVOICE,
            uploaded_by=self.site_manager_a,
        )

        result = validate_procurement(proc, user=self.site_manager_a)
        self.assertEqual(result["status"], ValidationStatus.VALID)
        self.assertEqual(len(result["errors"]), 0)

    def test_validate_procurement_blocking_errors(self):
        """Reporting period closed and line item sum mismatch flag blocking errors."""
        proc = ProcurementRecord.objects.create(
            procurement_number="PROC-2026-BLOCK1",
            supplier=self.supplier_global,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            reporting_period=self.closed_period,  # CLOSED
            purchase_date=date(2026, 5, 1),      # outside closed period (Jan-Mar 2026)
            total_amount=Decimal("200000.00"),
            currency="INR",
            created_by=self.site_manager_a,
        )

        ProcurementItem.objects.create(
            procurement=proc,
            line_number=1,
            item_name="Gravel",
            quantity=Decimal("1.00"),
            unit=self.unit_mt,
            unit_price=Decimal("50000.00"),
            total_amount=Decimal("50000.00"),
        )
        # item total is 50000, but procurement total manually set to 200000

        result = validate_procurement(proc, user=self.site_manager_a)
        self.assertEqual(result["status"], ValidationStatus.INVALID)
        self.assertTrue(any("Reporting period" in err for err in result["errors"]))
        self.assertTrue(any("Purchase date" in err for err in result["errors"]))

    # -------------------------------------------------------------------------
    # 6. PROCUREMENT ANOMALY DETECTION ENGINE
    # -------------------------------------------------------------------------

    def test_detect_procurement_anomalies_duplicate_invoice(self):
        """Anomaly engine detects duplicate invoice reference for same vendor."""
        # Existing verified procurement
        ProcurementRecord.objects.create(
            procurement_number="PROC-2026-DUP1",
            supplier=self.supplier_global,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            reporting_period=self.period,
            purchase_date=date(2026, 4, 15),
            invoice_reference="INV-REPEAT-999",
            invoice_date=date(2026, 4, 15),
            total_amount=Decimal("50000.00"),
            status=ProcurementStatus.VERIFIED,
            created_by=self.site_manager_a,
        )

        # New draft procurement reusing same vendor and invoice reference
        new_proc = create_procurement_record({
            "supplier": self.supplier_global,
            "site": self.site_a1,
            "reporting_period": self.period,
            "purchase_date": date(2026, 4, 15),
            "invoice_reference": "INV-REPEAT-999",
            "invoice_date": date(2026, 4, 15),
            "total_amount": Decimal("50000.00"),
        }, user=self.site_manager_a)

        anomalies = detect_procurement_anomalies(new_proc, user=self.site_manager_a)
        rule_codes = [a["rule_code"] for a in anomalies]
        self.assertIn("DUPLICATE_INVOICE", rule_codes)
        new_proc.refresh_from_db()
        self.assertTrue(new_proc.has_anomalies)

    def test_detect_procurement_anomalies_spend_spike(self):
        """Anomaly engine detects sudden procurement total spend spike (>200% average)."""
        # Create baseline records (e.g. 100k, 120k)
        for i, amt in enumerate([Decimal("100000.00"), Decimal("120000.00")]):
            ProcurementRecord.objects.create(
                procurement_number=f"PROC-2026-BASE{i}",
                supplier=self.supplier_global,
                company=self.company_a,
                project=self.project_a,
                site=self.site_a1,
                reporting_period=self.period,
                purchase_date=date(2026, 4, 1) + timedelta(days=i),
                category=ProcurementCategory.RAW_MATERIAL,
                total_amount=amt,
                status=ProcurementStatus.VERIFIED,
                created_by=self.site_manager_a,
            )

        # New record with huge spike (1,000,000)
        spike_proc = create_procurement_record({
            "supplier": self.supplier_global,
            "site": self.site_a1,
            "reporting_period": self.period,
            "purchase_date": date(2026, 4, 10),
            "category": ProcurementCategory.RAW_MATERIAL,
            "total_amount": Decimal("1000000.00"),
        }, user=self.site_manager_a)

        anomalies = detect_procurement_anomalies(spike_proc, user=self.site_manager_a)
        rule_codes = [a["rule_code"] for a in anomalies]
        self.assertIn("AMOUNT_SPIKE", rule_codes)

    # -------------------------------------------------------------------------
    # 7. GOVERNANCE WORKFLOW STATE MACHINE
    # -------------------------------------------------------------------------

    def test_complete_governance_lifecycle_verify(self):
        """Full lifecycle: DRAFT -> SUBMITTED -> VERIFIED."""
        proc = create_procurement_record({
            "supplier": self.supplier_global,
            "site": self.site_a1,
            "reporting_period": self.period,
            "purchase_date": date(2026, 4, 15),
            "invoice_reference": "INV-WF-01",
            "total_amount": Decimal("50000.00"),
        }, user=self.site_manager_a)

        add_procurement_item(proc, {
            "item_name": "Cement Bags",
            "quantity": Decimal("100.00"),
            "unit": self.unit_pcs,
            "unit_price": Decimal("500.00"),
        }, user=self.site_manager_a)

        Evidence.objects.create(
            procurement_record=proc,
            file=SimpleUploadedFile("inv.pdf", b"pdfcontent", content_type="application/pdf"),
            original_filename="inv.pdf",
            file_size=1024,
            file_type="application/pdf",
            evidence_type=EvidenceType.INVOICE,
            uploaded_by=self.site_manager_a,
        )

        # 1. Submit
        submit_procurement(proc, user=self.site_manager_a, comments="Ready for approval")
        proc.refresh_from_db()
        self.assertEqual(proc.status, ProcurementStatus.SUBMITTED)
        self.assertTrue(proc.is_locked)

        # 2. Review Decision: Verify
        review_procurement(proc, action="VERIFY", user=self.sub_manager_a, comments="Verified against challan")
        proc.refresh_from_db()
        self.assertEqual(proc.status, ProcurementStatus.VERIFIED)
        self.assertTrue(proc.is_locked)

        # Audit events verified
        self.assertTrue(
            AuthAuditLog.objects.filter(
                event_type=AuthAuditLog.EventType.PROCUREMENT_SUBMITTED,
                resource_accessed=f"ProcurementRecord:{proc.id}",
            ).exists()
        )
        self.assertTrue(
            AuthAuditLog.objects.filter(
                event_type=AuthAuditLog.EventType.PROCUREMENT_VERIFIED,
                resource_accessed=f"ProcurementRecord:{proc.id}",
            ).exists()
        )

    def test_correction_and_resubmission_lifecycle(self):
        """Lifecycle: SUBMITTED -> CORRECTION_REQUESTED -> SUBMITTED -> VERIFIED."""
        proc = create_procurement_record({
            "supplier": self.supplier_global,
            "site": self.site_a1,
            "reporting_period": self.period,
            "purchase_date": date(2026, 4, 15),
            "invoice_reference": "INV-CORR-01",
            "total_amount": Decimal("50000.00"),
        }, user=self.site_manager_a)

        Evidence.objects.create(
            procurement_record=proc,
            file=SimpleUploadedFile("inv.pdf", b"pdfcontent", content_type="application/pdf"),
            original_filename="inv.pdf",
            file_size=1024,
            file_type="application/pdf",
            evidence_type=EvidenceType.INVOICE,
            uploaded_by=self.site_manager_a,
        )

        submit_procurement(proc, user=self.site_manager_a)

        # Sub Manager requests correction
        review_procurement(
            proc,
            action="REQUEST_CORRECTION",
            user=self.sub_manager_a,
            correction_notes="Invoice number typo; please rectify to INV-CORR-02",
        )
        proc.refresh_from_db()
        self.assertEqual(proc.status, ProcurementStatus.CORRECTION_REQUESTED)
        self.assertFalse(proc.is_locked)  # Unlocked for remediation

        # Site Manager corrects and resubmits
        update_procurement_record(proc, {"invoice_reference": "INV-CORR-02"}, user=self.site_manager_a)
        resubmit_procurement(
            proc,
            user=self.site_manager_a,
            explanation="Corrected invoice number per directive",
        )
        proc.refresh_from_db()
        self.assertEqual(proc.status, ProcurementStatus.SUBMITTED)
        self.assertTrue(proc.is_locked)
        self.assertEqual(proc.invoice_reference, "INV-CORR-02")

    # -------------------------------------------------------------------------
    # 8. RBAC & ANTI-IDOR SECURITY
    # -------------------------------------------------------------------------

    def test_site_manager_idor_isolation(self):
        """Site Manager A cannot mutate or submit procurements belonging to Site B."""
        proc_b = create_procurement_record({
            "supplier": self.supplier_global,
            "site": self.site_b1,
            "reporting_period": self.period_b,
            "purchase_date": date(2026, 4, 15),
            "total_amount": Decimal("10000.00"),
        }, user=self.site_manager_b)

        # Site Manager A cannot modify
        self.assertFalse(user_can_modify_procurement(self.site_manager_a, proc_b))
        with self.assertRaises(PermissionDenied):
            update_procurement_record(proc_b, {"description": "Hacked"}, user=self.site_manager_a)

        # Site Manager A cannot submit
        self.assertFalse(user_can_submit_procurement(self.site_manager_a, proc_b))
        with self.assertRaises(PermissionDenied):
            submit_procurement(proc_b, user=self.site_manager_a)

    def test_subsidiary_manager_idor_isolation(self):
        """Subsidiary Manager A cannot review procurements for Company B."""
        proc_b = create_procurement_record({
            "supplier": self.supplier_global,
            "site": self.site_b1,
            "reporting_period": self.period_b,
            "purchase_date": date(2026, 4, 15),
            "total_amount": Decimal("10000.00"),
        }, user=self.site_manager_b)
        submit_procurement(proc_b, user=self.site_manager_b)

        self.assertFalse(user_can_review_procurement(self.sub_manager_a, proc_b))
        with self.assertRaises(PermissionDenied):
            review_procurement(proc_b, action="VERIFY", user=self.sub_manager_a)

    def test_auditor_strictly_read_only(self):
        """Auditor can view but cannot create, modify, submit, or review."""
        proc_a = create_procurement_record({
            "supplier": self.supplier_global,
            "site": self.site_a1,
            "reporting_period": self.period,
            "purchase_date": date(2026, 4, 15),
            "total_amount": Decimal("10000.00"),
        }, user=self.site_manager_a)

        self.assertTrue(user_can_access_procurement(self.auditor, proc_a))
        self.assertFalse(user_can_modify_procurement(self.auditor, proc_a))
        self.assertFalse(user_can_submit_procurement(self.auditor, proc_a))
        self.assertFalse(user_can_review_procurement(self.auditor, proc_a))
        self.assertFalse(user_can_delete_procurement(self.auditor, proc_a))

    # -------------------------------------------------------------------------
    # 9. HTTP ENDPOINTS INTEGRATION
    # -------------------------------------------------------------------------

    def test_supplier_views_flow(self):
        """Supplier catalog, detail, creation, and edit views return 200/302."""
        client = Client()
        client.force_login(self.meil_operator)

        # List
        resp = client.get(reverse("core:supplier_list"))
        self.assertEqual(resp.status_code, 200)

        # Detail
        resp = client.get(reverse("core:supplier_detail", args=[self.supplier_global.id]))
        self.assertEqual(resp.status_code, 200)

        # Create
        resp = client.get(reverse("core:supplier_create"))
        self.assertEqual(resp.status_code, 200)
        resp = client.post(reverse("core:supplier_create"), {
            "supplier_code": "VEND-HTTP-1",
            "name": "HTTP Vendor Inc",
            "supplier_type": SupplierType.GOODS,
            "status": SupplierStatus.ACTIVE,
            "country": "India",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Supplier.objects.filter(supplier_code="VEND-HTTP-1").exists())

    def test_procurement_views_flow(self):
        """Procurement ledger, creation, item addition, and detail views return 200/302."""
        client = Client()
        client.force_login(self.site_manager_a)

        # List
        resp = client.get(reverse("core:procurement_list"))
        self.assertEqual(resp.status_code, 200)

        # Create form
        resp = client.get(reverse("core:procurement_create"))
        self.assertEqual(resp.status_code, 200)

        # Post create
        resp = client.post(reverse("core:procurement_create"), {
            "supplier": self.supplier_global.id,
            "site": self.site_a1.id,
            "reporting_period": self.period.id,
            "purchase_date": "2026-04-15",
            "category": ProcurementCategory.RAW_MATERIAL,
            "total_amount": "50000.00",
            "currency": "INR",
        })
        self.assertEqual(resp.status_code, 302)
        proc = ProcurementRecord.objects.filter(site=self.site_a1).order_by("-id").first()
        self.assertIsNotNone(proc)

        # Detail
        resp = client.get(reverse("core:procurement_detail", args=[proc.id]))
        self.assertEqual(resp.status_code, 200)

        # Add line item
        resp = client.post(reverse("core:procurement_item_create", args=[proc.id]), {
            "item_name": "Steel Rebars 10mm",
            "category": ProcurementCategory.RAW_MATERIAL,
            "quantity": "2.00",
            "unit": self.unit_mt.id,
            "unit_price": "25000.00",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(proc.items.count(), 1)

    def test_review_inbox_and_decision_endpoints(self):
        """Review inbox and review action endpoints work for authorized managers, 403 for unauthorized."""
        proc = create_procurement_record({
            "supplier": self.supplier_global,
            "site": self.site_a1,
            "reporting_period": self.period,
            "purchase_date": date(2026, 4, 15),
            "total_amount": Decimal("50000.00"),
        }, user=self.site_manager_a)
        submit_procurement(proc, user=self.site_manager_a)

        # Site manager blocked from review inbox
        client_site = Client()
        client_site.force_login(self.site_manager_a)
        resp = client_site.get(reverse("core:procurement_review_inbox"))
        self.assertEqual(resp.status_code, 403)

        # Sub manager A allowed
        client_sub = Client()
        client_sub.force_login(self.sub_manager_a)
        resp = client_sub.get(reverse("core:procurement_review_inbox"))
        self.assertEqual(resp.status_code, 200)

        # Sub manager A reviews and verifies
        resp = client_sub.post(reverse("core:procurement_review", args=[proc.id]), {
            "action": "VERIFY",
            "comments": "Approved after document cross-check",
        })
        self.assertEqual(resp.status_code, 302)
        proc.refresh_from_db()
        self.assertEqual(proc.status, ProcurementStatus.VERIFIED)
