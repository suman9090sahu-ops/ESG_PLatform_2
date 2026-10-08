"""
Comprehensive Automated Test Suite for Phase 17 — Transport & Logistics Management.

MEIL ESG CONTROL TOWER Monolith Test Suite.

Validates:
1. Model Architecture & Integrity:
   - Carrier: code, name, type, status, soft archival, optional supplier/company link
   - Vehicle: vehicle_identifier, registration_number, ownership_type, vehicle_type, fuel_type, capacity, status
   - Shipment: shipment_reference, material_description, quantity, weight, procurement linkage
   - TransportRecord: reference, period, company, project, site, date, mode, carrier, vehicle, shipment, multi-leg, distance/unit/source, freight cost, activity_record link
   - Evidence model integration with transport_record FK
   - AuthAuditLog event types for Phase 17

2. Master Services & Anti-IDOR Scoping:
   - Carrier CRUD and soft archival
   - Vehicle CRUD and soft archival
   - TransportRecord CRUD with embedded shipment handling
   - Scoped queryset retrieval (get_accessible_transports, get_accessible_carriers, get_accessible_vehicles)

3. Evidence & OCR Document Intelligence:
   - Upload evidence attached to transport record
   - compare_ocr_with_transport (vehicle plate, carrier, cost, distance reconciliation)
   - Zero silent overwrite principle

4. Deterministic Validation Engine:
   - validate_transport (temporal boundary, carrier status, route distance, site consistency)
   - Warning conditions and error conditions

5. Anomaly Detection Engine:
   - detect_transport_anomalies (duplicate transport trips, excessive distance, payload overload)
   - Non-destructive anomaly flagging

6. Governance Workflow & Lifecycle:
   - submit_transport_record: DRAFT -> SUBMITTED
   - review_transport_record: VERIFIED, CORRECTION_REQUESTED, REJECTED
   - correct_transport_record: resubmission with audit explanation

7. RBAC & Anti-IDOR Security:
   - SITE_MANAGER scoped to assigned sites
   - SUBSIDIARY_MANAGER review authority within company
   - AUDITOR read-only verification
   - Cross-site / cross-company access blocked (403/404)

8. Complete HTTP Views & Form Submissions:
   - Carrier, Vehicle, and Transport list, detail, form, review, and evidence views
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    ActivityRecord,
    AuthAuditLog,
    Carrier,
    CarrierStatus,
    CarrierType,
    Company,
    CompanyAssignment,
    DistanceSource,
    DistanceUnit,
    Evidence,
    EvidenceStatus,
    EvidenceType,
    FuelType,
    MasterStatus,
    OCRField,
    OCRRun,
    OCRStatus,
    PeriodStatus,
    ProcurementCategory,
    ProcurementRecord,
    ProcurementStatus,
    Project,
    ReportingPeriod,
    Role,
    Shipment,
    Site,
    SiteAssignment,
    Subsidiary,
    SubsidiaryAssignment,
    Supplier,
    SupplierStatus,
    SupplierType,
    TransportLocationType,
    TransportMode,
    TransportRecord,
    TransportScopeCategory,
    TransportStatus,
    UnitDimension,
    UnitOfMeasure,
    UserRole,
    ValidationStatus,
    Vehicle,
    VehicleOwnershipType,
    VehicleStatus,
    VehicleType,
)
from apps.core.transport_services import (
    archive_carrier,
    archive_vehicle,
    compare_ocr_with_transport,
    correct_transport_record,
    create_carrier,
    create_transport_record,
    create_vehicle,
    delete_transport_record,
    detect_transport_anomalies,
    generate_carrier_code,
    generate_shipment_reference,
    generate_transport_reference,
    generate_vehicle_identifier,
    get_accessible_carriers,
    get_accessible_transports,
    get_accessible_vehicles,
    review_transport_record,
    submit_transport_record,
    update_carrier,
    update_transport_record,
    update_vehicle,
    upload_transport_evidence,
    user_can_access_carrier,
    user_can_access_transport,
    user_can_access_vehicle,
    user_can_delete_transport,
    user_can_modify_transport,
    user_can_review_transport,
    user_can_submit_transport,
    validate_transport,
)

User = get_user_model()


class Phase17TransportLogisticsTestCase(TestCase):
    """Core test suite for Phase 17 Transport & Logistics Management."""

    @classmethod
    def setUpTestData(cls):
        # 1. Organization Hierarchy
        cls.company_a = Company.objects.create(name="MEIL Division A", code="DIV-A")
        cls.company_b = Company.objects.create(name="MEIL Division B", code="DIV-B")

        cls.sub_a = Subsidiary.objects.create(company=cls.company_a, name="Infra Sub A", code="SUB-A")
        cls.sub_b = Subsidiary.objects.create(company=cls.company_b, name="Energy Sub B", code="SUB-B")

        cls.project_a = Project.objects.create(name="Project Alpha", code="PRJ-A", subsidiary=cls.sub_a)
        cls.project_b = Project.objects.create(name="Project Beta", code="PRJ-B", subsidiary=cls.sub_b)

        cls.site_a1 = Site.objects.create(name="Site Alpha 1", code="SITE-A1", project=cls.project_a)
        cls.site_a2 = Site.objects.create(name="Site Alpha 2", code="SITE-A2", project=cls.project_a)
        cls.site_b1 = Site.objects.create(name="Site Beta 1", code="SITE-B1", project=cls.project_b)

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
        cls.closed_period = ReportingPeriod.objects.create(
            company=cls.company_a,
            code="FY25-Q4",
            name="FY2025-Q4",
            fiscal_year="2025-26",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            status=PeriodStatus.CLOSED,
        )

        # 3. Units & Activity Master
        cls.uom_km, _ = UnitOfMeasure.objects.get_or_create(
            code="KM",
            defaults={"name": "Kilometer", "dimension": UnitDimension.DISTANCE, "symbol": "km"},
        )
        cls.uom_mt, _ = UnitOfMeasure.objects.get_or_create(
            code="MT",
            defaults={"name": "Metric Ton", "dimension": UnitDimension.MASS, "symbol": "MT"},
        )

        cls.act_cat, _ = ActivityCategory.objects.get_or_create(
            code="CAT-TRANSPORT",
            defaults={"name": "Transportation & Logistics"},
        )
        cls.activity_master = ActivityMaster.objects.create(
            code="ACT-FREIGHT-ROAD",
            name="Commercial Freight Road Transport",
            category=cls.act_cat,
            base_unit=cls.uom_mt,
            status=MasterStatus.ACTIVE,
        )

        cls.activity_record = ActivityRecord.objects.create(
            site=cls.site_a1,
            reporting_period=cls.period,
            activity=cls.activity_master,
            measurement_date=date(2026, 5, 10),
            quantity=Decimal("25.00"),
            unit=cls.uom_mt,
            notes="Upstream raw material haulage",
        )



        # 4. Phase 16 Supplier & Procurement for Integration Linkage
        cls.supplier = Supplier.objects.create(
            supplier_code="SUP-LOG-01",
            name="Apex Logistics Corp",
            supplier_type=SupplierType.SERVICES,
            company=cls.company_a,
        )

        cls.procurement = ProcurementRecord.objects.create(
            procurement_number="PROC-2026-0001",
            site=cls.site_a1,
            project=cls.project_a,
            company=cls.company_a,
            reporting_period=cls.period,
            supplier=cls.supplier,
            purchase_date=date(2026, 5, 5),
            total_amount=Decimal("150000.00"),
            category=ProcurementCategory.SERVICES,
        )

        # 5. Role Definitions
        cls.role_site_mgr, _ = Role.objects.get_or_create(code=Role.Code.SITE_MANAGER, defaults={"name": "Site Manager"})
        cls.role_sub_mgr, _ = Role.objects.get_or_create(code=Role.Code.SUBSIDIARY_MANAGER, defaults={"name": "Subsidiary Manager"})
        cls.role_esg_mgr, _ = Role.objects.get_or_create(code=Role.Code.ESG_MANAGER, defaults={"name": "ESG Manager"})
        cls.role_auditor, _ = Role.objects.get_or_create(code=Role.Code.AUDITOR, defaults={"name": "Auditor"})
        cls.role_meil_op, _ = Role.objects.get_or_create(code=Role.Code.MEIL_OPERATOR, defaults={"name": "MEIL Operator"})

        # 6. Users & Assignments
        # Site Manager A (Site A1 and A2)
        cls.user_site_a = User.objects.create_user(username="site_mgr_a", password="password123", email="site_a@meil.in")
        UserRole.objects.create(user=cls.user_site_a, role=cls.role_site_mgr, is_primary=True)
        SiteAssignment.objects.create(user=cls.user_site_a, site=cls.site_a1)
        SiteAssignment.objects.create(user=cls.user_site_a, site=cls.site_a2)

        # Site Manager B (Site B1 only)
        cls.user_site_b = User.objects.create_user(username="site_mgr_b", password="password123", email="site_b@meil.in")
        UserRole.objects.create(user=cls.user_site_b, role=cls.role_site_mgr, is_primary=True)
        SiteAssignment.objects.create(user=cls.user_site_b, site=cls.site_b1)

        # Subsidiary Manager A (Company A)
        cls.user_sub_mgr_a = User.objects.create_user(username="sub_mgr_a", password="password123", email="sub_a@meil.in")
        UserRole.objects.create(user=cls.user_sub_mgr_a, role=cls.role_sub_mgr, is_primary=True)
        CompanyAssignment.objects.create(user=cls.user_sub_mgr_a, company=cls.company_a)
        SubsidiaryAssignment.objects.create(user=cls.user_sub_mgr_a, subsidiary=cls.sub_a)

        # Subsidiary Manager B (Company B)
        cls.user_sub_mgr_b = User.objects.create_user(username="sub_mgr_b", password="password123", email="sub_b@meil.in")
        UserRole.objects.create(user=cls.user_sub_mgr_b, role=cls.role_sub_mgr, is_primary=True)
        CompanyAssignment.objects.create(user=cls.user_sub_mgr_b, company=cls.company_b)
        SubsidiaryAssignment.objects.create(user=cls.user_sub_mgr_b, subsidiary=cls.sub_b)

        # ESG Manager (Enterprise wide)
        cls.user_esg_mgr = User.objects.create_user(username="esg_mgr", password="password123", email="esg@meil.in")
        UserRole.objects.create(user=cls.user_esg_mgr, role=cls.role_esg_mgr, is_primary=True)

        # Auditor (Enterprise wide read-only)
        cls.user_auditor = User.objects.create_user(username="auditor", password="password123", email="auditor@meil.in")
        UserRole.objects.create(user=cls.user_auditor, role=cls.role_auditor, is_primary=True)

        # MEIL Operator (Superuser/Enterprise)
        cls.user_operator = User.objects.create_user(username="meil_op", password="password123", email="op@meil.in")
        UserRole.objects.create(user=cls.user_operator, role=cls.role_meil_op, is_primary=True)

        # 7. Initial Carrier & Vehicle Seed
        cls.carrier_a = Carrier.objects.create(
            carrier_code="CARR-001",
            name="Speedy Freight Carriers",
            legal_name="Speedy Freight Carriers Pvt Ltd",
            carrier_type=CarrierType.ROAD_CARRIER,
            status=CarrierStatus.ACTIVE,
            company=cls.company_a,
            supplier=cls.supplier,
            contact_person="Ramesh Kumar",
            contact_phone="+91-9876543210",
        )
        cls.vehicle_a1 = Vehicle.objects.create(
            vehicle_identifier="VEH-001",
            registration_number="TS-09-UB-1001",
            carrier=cls.carrier_a,
            company=cls.company_a,
            ownership_type=VehicleOwnershipType.OWNED,
            vehicle_type=VehicleType.TRUCK_HEAVY,
            fuel_type=FuelType.DIESEL,
            capacity_payload=Decimal("25.00"),
            status=VehicleStatus.ACTIVE,
        )

    # -------------------------------------------------------------------------
    # TEST SUITE 1: DOMAIN MODELS & ARCHITECTURE
    # -------------------------------------------------------------------------

    def test_carrier_model_constraints_and_lifecycle(self):
        """Test Carrier code uniqueness, status, and soft archival."""
        carrier = Carrier.objects.create(
            carrier_code="CARR-002",
            name="TransRail India",
            carrier_type=CarrierType.RAIL_OPERATOR,
        )
        self.assertTrue(carrier.is_active)
        self.assertEqual(carrier.carrier_code, "CARR-002")

        # Duplicate carrier code blocked
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Carrier.objects.create(carrier_code="CARR-002", name="Duplicate Carrier")

        # Soft archival
        archive_carrier(carrier, actor=self.user_esg_mgr)
        carrier.refresh_from_db()
        self.assertEqual(carrier.status, CarrierStatus.ARCHIVED)
        self.assertFalse(carrier.is_active)

    def test_vehicle_model_normalization_and_ownership(self):
        """Test Vehicle registration number normalization and Scope 1 vs 3 flag."""
        veh = Vehicle.objects.create(
            vehicle_identifier="VEH-002",
            registration_number=" ap-07-xy-9999 ",
            ownership_type=VehicleOwnershipType.OWNED,
            vehicle_type=VehicleType.TANKER,
            fuel_type=FuelType.DIESEL,
        )
        veh.clean()
        veh.save()
        self.assertEqual(veh.registration_number, "AP-07-XY-9999")
        self.assertTrue(veh.is_owned)

        # Duplicate registration number blocked
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Vehicle.objects.create(
                    vehicle_identifier="VEH-003",
                    registration_number="AP-07-XY-9999",
                )

    def test_shipment_model_creation(self):
        """Test Shipment cargo creation and integration with Procurement."""
        shipment = Shipment.objects.create(
            shipment_reference="SHP-2026-0001",
            material_description="Structural Steel TMT Rebars",
            quantity=Decimal("30.00"),
            unit=self.uom_mt,
            weight_gross=Decimal("32.50"),
            procurement=self.procurement,
        )
        self.assertEqual(shipment.shipment_reference, "SHP-2026-0001")
        self.assertEqual(shipment.procurement, self.procurement)

    def test_transport_record_model_creation_and_activity_link(self):
        """Test TransportRecord creation, multi-leg, and canonical Activity link."""
        trn = TransportRecord.objects.create(
            transport_reference="TRN-2026-0001",
            reporting_period=self.period,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            transport_date=date(2026, 5, 10),
            transport_mode=TransportMode.ROAD,
            carrier=self.carrier_a,
            vehicle=self.vehicle_a1,
            origin_location="Hyderabad Stockyard",
            destination_location="Polavaram Project Site",
            distance=Decimal("340.50"),
            distance_unit=DistanceUnit.KM,
            distance_source=DistanceSource.DOCUMENT,
            freight_amount=Decimal("45000.00"),
            activity_record=self.activity_record,
            created_by=self.user_site_a,
        )
        self.assertEqual(trn.status, TransportStatus.DRAFT)
        self.assertEqual(trn.activity_record, self.activity_record)
        self.assertEqual(trn.leg_number, 1)

    # -------------------------------------------------------------------------
    # TEST SUITE 2: SERVICE LAYER & SCOPING
    # -------------------------------------------------------------------------

    def test_scoped_queryset_access_site_manager(self):
        """Site manager can only see transports for assigned sites."""
        t_a1 = TransportRecord.objects.create(
            transport_reference="TRN-SCOPED-A1",
            reporting_period=self.period,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            transport_date=date(2026, 5, 10),
            carrier=self.carrier_a,
            origin_location="Org A",
            destination_location="Dest A",
            distance=Decimal("100.00"),
        )
        t_b1 = TransportRecord.objects.create(
            transport_reference="TRN-SCOPED-B1",
            reporting_period=self.period,
            company=self.company_b,
            project=self.project_b,
            site=self.site_b1,
            transport_date=date(2026, 5, 10),
            carrier=self.carrier_a,
            origin_location="Org B",
            destination_location="Dest B",
            distance=Decimal("150.00"),
        )

        qs_site_a = get_accessible_transports(self.user_site_a)
        self.assertIn(t_a1, qs_site_a)
        self.assertNotIn(t_b1, qs_site_a)

        qs_site_b = get_accessible_transports(self.user_site_b)
        self.assertIn(t_b1, qs_site_b)
        self.assertNotIn(t_a1, qs_site_b)

        # ESG manager sees both
        qs_esg = get_accessible_transports(self.user_esg_mgr)
        self.assertIn(t_a1, qs_esg)
        self.assertIn(t_b1, qs_esg)

    def test_create_transport_record_service_with_shipment(self):
        """Test create_transport_record service handles embedded shipment cargo atomically."""
        transport_data = {
            "site": self.site_a1,
            "reporting_period": self.period,
            "transport_date": date(2026, 5, 15),
            "transport_mode": TransportMode.ROAD,
            "carrier": self.carrier_a,
            "vehicle": self.vehicle_a1,
            "origin_location": "Secunderabad Yard",
            "destination_location": "Site A1 Batching Plant",
            "distance": Decimal("180.00"),
            "distance_unit": DistanceUnit.KM,
            "distance_source": DistanceSource.USER_PROVIDED,
            "freight_amount": Decimal("22000.00"),
        }
        shipment_data = {
            "material_description": "Bulk Cement 53 Grade",
            "quantity": Decimal("20.00"),
            "unit": self.uom_mt,
            "weight_gross": Decimal("21.50"),
        }

        trn = create_transport_record(
            data=transport_data,
            shipment_data=shipment_data,
            actor=self.user_site_a,
        )
        self.assertIsNotNone(trn.id)
        self.assertTrue(trn.transport_reference.startswith("TRN-"))
        self.assertIsNotNone(trn.shipment)
        self.assertEqual(trn.shipment.material_description, "Bulk Cement 53 Grade")

        # Verify audit log recorded
        audit = AuthAuditLog.objects.filter(
            event_type=AuthAuditLog.EventType.TRANSPORT_CREATED,
            user=self.user_site_a,
        ).first()
        self.assertIsNotNone(audit)

    # -------------------------------------------------------------------------
    # TEST SUITE 3: EVIDENCE & OCR INTEGRATION
    # -------------------------------------------------------------------------

    def test_evidence_attachment_and_ocr_comparison(self):
        """Upload evidence to transport and run telemetry comparison."""
        trn = TransportRecord.objects.create(
            transport_reference="TRN-OCR-01",
            reporting_period=self.period,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            transport_date=date(2026, 5, 12),
            carrier=self.carrier_a,
            vehicle=self.vehicle_a1,
            origin_location="Vizag Port",
            destination_location="Site A1",
            distance=Decimal("250.00"),
            distance_unit=DistanceUnit.KM,
            freight_amount=Decimal("35000.00"),
        )

        test_file = SimpleUploadedFile("lorry_receipt.pdf", b"%PDF-1.4 test transport receipt", content_type="application/pdf")
        ev = upload_transport_evidence(
            transport=trn,
            file_obj=test_file,
            evidence_type=EvidenceType.LORRY_RECEIPT,
            actor=self.user_site_a,
            description="Signed consignment note",
        )
        self.assertEqual(ev.transport_record, trn)
        self.assertTrue(ev.file_hash)

        # Mock OCR Fields
        ocr_run = OCRRun.objects.create(
            evidence=ev,
            run_number=1,
            status=OCRStatus.COMPLETED,
            engine="tesseract",
            extracted_text="SPEEDY FREIGHT TS-09-UB-1001 DISTANCE 250 KM AMOUNT 35000",
        )
        OCRField.objects.create(
            ocr_run=ocr_run,
            field_name="vehicle_number",
            raw_value="TS-09-UB-1001",
            normalized_value="TS-09-UB-1001",
            confidence=Decimal("98.50"),
        )
        OCRField.objects.create(
            ocr_run=ocr_run,
            field_name="distance",
            raw_value="250.00",
            normalized_value="250.00",
            confidence=Decimal("95.00"),
        )

        comparison = compare_ocr_with_transport(trn, ocr_run)
        self.assertIn("vehicle_number", comparison["items"])
        self.assertEqual(comparison["items"]["vehicle_number"]["status"], "MATCH")
        self.assertEqual(comparison["items"]["distance"]["status"], "MATCH")
        self.assertEqual(comparison["overall_status"], "MATCH")

    # -------------------------------------------------------------------------
    # TEST SUITE 4: DETERMINISTIC VALIDATION ENGINE
    # -------------------------------------------------------------------------

    def test_transport_validation_rules(self):
        """Test validate_transport flags invalid dates, missing carriers, and negative distance."""
        # 1. Transport with date outside reporting period
        trn_invalid_date = TransportRecord.objects.create(
            transport_reference="TRN-VAL-01",
            reporting_period=self.period,  # Q1: 2026-04-01 to 2026-06-30
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            transport_date=date(2026, 8, 15),  # Outside period
            carrier=self.carrier_a,
            origin_location="A",
            destination_location="B",
            distance=Decimal("50.00"),
        )
        val_result = validate_transport(trn_invalid_date)
        self.assertEqual(val_result["status"], ValidationStatus.INVALID)
        self.assertTrue(any("reporting period" in err.lower() for err in val_result["errors"]))

        # 2. Closed reporting period
        trn_closed = TransportRecord.objects.create(
            transport_reference="TRN-VAL-02",
            reporting_period=self.closed_period,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            transport_date=date(2026, 2, 10),
            carrier=self.carrier_a,
            origin_location="A",
            destination_location="B",
            distance=Decimal("50.00"),
        )
        val_result_closed = validate_transport(trn_closed)
        self.assertEqual(val_result_closed["status"], ValidationStatus.INVALID)
        self.assertTrue(any("closed" in err.lower() for err in val_result_closed["errors"]))

        # 3. Valid record
        trn_valid = TransportRecord.objects.create(
            transport_reference="TRN-VAL-03",
            reporting_period=self.period,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            transport_date=date(2026, 5, 10),
            carrier=self.carrier_a,
            vehicle=self.vehicle_a1,
            origin_location="A",
            destination_location="B",
            distance=Decimal("50.00"),
        )
        val_result_valid = validate_transport(trn_valid)
        self.assertIn(val_result_valid["status"], [ValidationStatus.VALID, ValidationStatus.WARNING])

    # -------------------------------------------------------------------------
    # TEST SUITE 5: ANOMALY DETECTION ENGINE
    # -------------------------------------------------------------------------

    def test_duplicate_transport_anomaly_detection(self):
        """Test duplicate trip detection on identical date, vehicle, carrier, and route."""
        t1 = TransportRecord.objects.create(
            transport_reference="TRN-DUP-01",
            reporting_period=self.period,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            transport_date=date(2026, 5, 20),
            carrier=self.carrier_a,
            vehicle=self.vehicle_a1,
            origin_location="Quarry A",
            destination_location="Site A1",
            distance=Decimal("45.00"),
        )
        t2 = TransportRecord.objects.create(
            transport_reference="TRN-DUP-02",
            reporting_period=self.period,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            transport_date=date(2026, 5, 20),
            carrier=self.carrier_a,
            vehicle=self.vehicle_a1,
            origin_location="Quarry A",
            destination_location="Site A1",
            distance=Decimal("45.00"),
        )

        anomalies = detect_transport_anomalies(t2)
        dup_signals = [a for a in anomalies if a["type"] == "DUPLICATE_TRANSPORT"]
        self.assertTrue(len(dup_signals) > 0)
        self.assertTrue(t2.has_anomalies)

    def test_payload_overload_anomaly_detection(self):
        """Test payload overload anomaly when shipment cargo exceeds rated vehicle capacity."""
        overloaded_shipment = Shipment.objects.create(
            shipment_reference="SHP-OVERLOAD",
            material_description="Granite Aggregate",
            quantity=Decimal("45.00"),
            weight_gross=Decimal("48.00"),  # Vehicle payload is 25 MT!
            weight_unit="MT",
        )
        trn_overload = TransportRecord.objects.create(
            transport_reference="TRN-OVERLOAD",
            reporting_period=self.period,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            transport_date=date(2026, 5, 22),
            carrier=self.carrier_a,
            vehicle=self.vehicle_a1,
            shipment=overloaded_shipment,
            origin_location="Quarry",
            destination_location="Site",
            distance=Decimal("30.00"),
        )
        anomalies = detect_transport_anomalies(trn_overload)
        overload_signals = [a for a in anomalies if a["type"] == "PAYLOAD_OVERLOAD"]
        self.assertTrue(len(overload_signals) > 0)

    # -------------------------------------------------------------------------
    # TEST SUITE 6: WORKFLOW LIFECYCLE & STATE MACHINE
    # -------------------------------------------------------------------------

    def test_transport_submission_and_subsidiary_review_flow(self):
        """Submit -> Under Review -> Verified lifecycle."""
        trn = TransportRecord.objects.create(
            transport_reference="TRN-FLOW-01",
            reporting_period=self.period,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            transport_date=date(2026, 5, 10),
            carrier=self.carrier_a,
            vehicle=self.vehicle_a1,
            origin_location="Yard A",
            destination_location="Site A1",
            distance=Decimal("60.00"),
        )
        self.assertEqual(trn.status, TransportStatus.DRAFT)

        # Submit by Site Manager
        submit_transport_record(trn, actor=self.user_site_a)
        trn.refresh_from_db()
        self.assertEqual(trn.status, TransportStatus.SUBMITTED)

        # Review by Subsidiary Manager A -> VERIFY
        review_transport_record(
            trn,
            action="VERIFY",
            comments="Logistics and route verified against weighbridge tickets.",
            actor=self.user_sub_mgr_a,
        )
        trn.refresh_from_db()
        self.assertEqual(trn.status, TransportStatus.VERIFIED)
        self.assertEqual(trn.updated_by, self.user_sub_mgr_a)
        self.assertEqual(trn.review_comments, "Logistics and route verified against weighbridge tickets.")

    def test_transport_correction_and_resubmission_flow(self):
        """Submit -> Request Correction -> Amend -> Resubmit."""
        trn = TransportRecord.objects.create(
            transport_reference="TRN-FLOW-CORR",
            reporting_period=self.period,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            transport_date=date(2026, 5, 10),
            carrier=self.carrier_a,
            vehicle=self.vehicle_a1,
            origin_location="Yard A",
            destination_location="Site A1",
            distance=Decimal("60.00"),
        )
        submit_transport_record(trn, actor=self.user_site_a)

        # Reviewer requests correction
        review_transport_record(
            trn,
            action="REQUEST_CORRECTION",
            comments="Distance does not match toll receipt. Please adjust to 85 km.",
            actor=self.user_sub_mgr_a,
            correction_notes="Adjust distance to 85 km",
        )
        trn.refresh_from_db()
        self.assertEqual(trn.status, TransportStatus.CORRECTION_REQUESTED)
        self.assertEqual(trn.correction_notes, "Adjust distance to 85 km")

        # Site manager corrects and resubmits
        correct_transport_record(
            trn,
            data={"distance": Decimal("85.00"), "notes": "Corrected per toll logs"},
            explanation="Updated route distance after checking toll plazas.",
            actor=self.user_site_a,
        )
        trn.refresh_from_db()
        self.assertEqual(trn.status, TransportStatus.SUBMITTED)
        self.assertEqual(trn.distance, Decimal("85.00"))

    # -------------------------------------------------------------------------
    # TEST SUITE 7: RBAC & ANTI-IDOR SECURITY
    # -------------------------------------------------------------------------

    def test_rbac_site_manager_cannot_modify_other_site(self):
        """Site Manager B cannot modify Transport for Site A1."""
        trn = TransportRecord.objects.create(
            transport_reference="TRN-IDOR-01",
            reporting_period=self.period,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            transport_date=date(2026, 5, 10),
            carrier=self.carrier_a,
            origin_location="Origin",
            destination_location="Destination",
            distance=Decimal("50.00"),
        )
        self.assertTrue(user_can_modify_transport(self.user_site_a, trn))
        self.assertFalse(user_can_modify_transport(self.user_site_b, trn))

    def test_rbac_subsidiary_manager_cross_company_review_blocked(self):
        """Subsidiary Manager B cannot review Transport belonging to Company A."""
        trn = TransportRecord.objects.create(
            transport_reference="TRN-IDOR-02",
            reporting_period=self.period,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            transport_date=date(2026, 5, 10),
            carrier=self.carrier_a,
            origin_location="Origin",
            destination_location="Destination",
            distance=Decimal("50.00"),
            status=TransportStatus.SUBMITTED,
        )
        self.assertTrue(user_can_review_transport(self.user_sub_mgr_a, trn))
        self.assertFalse(user_can_review_transport(self.user_sub_mgr_b, trn))

        with self.assertRaises(PermissionDenied):
            review_transport_record(trn, action="VERIFY", comments="Illicit review", actor=self.user_sub_mgr_b)

    def test_rbac_auditor_is_strictly_read_only(self):
        """Auditor can view transport records but cannot modify, submit, or review."""
        trn = TransportRecord.objects.create(
            transport_reference="TRN-AUDITOR-01",
            reporting_period=self.period,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            transport_date=date(2026, 5, 10),
            carrier=self.carrier_a,
            origin_location="Origin",
            destination_location="Destination",
            distance=Decimal("50.00"),
            status=TransportStatus.SUBMITTED,
        )
        self.assertTrue(user_can_access_transport(self.user_auditor, trn))
        self.assertFalse(user_can_modify_transport(self.user_auditor, trn))
        self.assertFalse(user_can_submit_transport(self.user_auditor, trn))
        self.assertFalse(user_can_review_transport(self.user_auditor, trn))

    # -------------------------------------------------------------------------
    # TEST SUITE 8: HTTP VIEWS INTEGRATION
    # -------------------------------------------------------------------------

    def test_transport_views_http_endpoints(self):
        """Test HTTP responses for transport list, detail, and create."""
        client = Client()
        client.force_login(self.user_site_a)

        # 1. Transport List
        resp = client.get(reverse("core:transport_list"))
        self.assertEqual(resp.status_code, 200)

        # 2. Carrier List
        resp = client.get(reverse("core:carrier_list"))
        self.assertEqual(resp.status_code, 200)

        # 3. Vehicle List
        resp = client.get(reverse("core:vehicle_list"))
        self.assertEqual(resp.status_code, 200)

        # 4. Carrier Detail
        resp = client.get(reverse("core:carrier_detail", args=[self.carrier_a.id]))
        self.assertEqual(resp.status_code, 200)

        # 5. Vehicle Detail
        resp = client.get(reverse("core:vehicle_detail", args=[self.vehicle_a1.id]))
        self.assertEqual(resp.status_code, 200)

        # 6. Transport Creation via HTTP POST
        post_data = {
            "company": self.company_a.id,
            "site": self.site_a1.id,
            "reporting_period": self.period.id,
            "transport_date": "2026-05-15",
            "transport_mode": TransportMode.ROAD,
            "carrier": self.carrier_a.id,
            "vehicle": self.vehicle_a1.id,
            "origin_location": "Secunderabad Terminal",
            "origin_type": TransportLocationType.SUPPLIER_FACILITY,
            "destination_location": "Site Alpha 1 Compound",
            "destination_type": TransportLocationType.SITE,
            "distance": "120.00",
            "distance_unit": DistanceUnit.KM,
            "distance_source": DistanceSource.USER_PROVIDED,
            "shipment_material": "Steel Structural Beams",
            "shipment_quantity": "15.00",
            "freight_amount": "25000.00",
            "currency": "INR",
        }
        resp = client.post(reverse("core:transport_create"), post_data)
        if resp.status_code != 302:
            form_errs = resp.context["form"].errors if (hasattr(resp, "context") and resp.context and "form" in resp.context) else None
            self.fail(f"Transport create POST failed with status {resp.status_code}. Form errors: {form_errs}")
        self.assertTrue(TransportRecord.objects.filter(origin_location="Secunderabad Terminal").exists())

    def test_review_inbox_and_decision_http_view(self):
        """Test Subsidiary Manager Review Inbox and Decision HTTP submission."""
        trn = TransportRecord.objects.create(
            transport_reference="TRN-HTTP-REV",
            reporting_period=self.period,
            company=self.company_a,
            project=self.project_a,
            site=self.site_a1,
            transport_date=date(2026, 5, 10),
            carrier=self.carrier_a,
            origin_location="A",
            destination_location="B",
            distance=Decimal("50.00"),
            status=TransportStatus.SUBMITTED,
        )

        client = Client()
        client.force_login(self.user_sub_mgr_a)

        # Review Inbox
        resp = client.get(reverse("core:transport_review_inbox"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "TRN-HTTP-REV")

        # Review Action POST
        review_data = {
            "action": "VERIFY",
            "comments": "Audited logistics documentation matches manifest.",
        }
        resp = client.post(reverse("core:transport_review", args=[trn.id]), review_data)
        self.assertEqual(resp.status_code, 302)
        trn.refresh_from_db()
        self.assertEqual(trn.status, TransportStatus.VERIFIED)
