"""
Phase 17 — Transport & Logistics Management Live Verification Script
MEIL ESG CONTROL TOWER Monolith

Empirically validates:
1. Carrier Master registration (fleet provider, codes, types, soft archival)
2. Vehicle Master registration (plate normalization, Scope 1 owned vs Scope 3 third-party classification)
3. Shipment Consignment creation (cargo quantity, gross/net weight, procurement linkage)
4. Transport Record transaction (site-scoped, route, mode, distance, freight cost, canonical activity link)
5. Evidence Management integration (Phase 09 lorry receipt / weighbridge slip attachment)
6. OCR Document Intelligence integration (Phase 11 comparison telemetry, zero silent overwrite)
7. Deterministic Validation Engine (Phase 10 temporal, organizational, route, and asset rules)
8. Anomaly Detection Engine (Phase 15 duplicate trip, route distance spike, payload overload signals)
9. Governance Lifecycle: Submit -> Subsidiary Review -> Correction Request -> Resubmit -> Verify
10. Anti-IDOR & RBAC Security (Site Manager site boundary, Subsidiary Manager review boundary, Auditor read-only)
11. AuthAuditLog complete audit trail compliance
"""

import os
import sys
from datetime import date, timedelta
from decimal import Decimal

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Setup Django Environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
import django
django.setup()

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import RequestFactory
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
    OrganizationStatus,
    PeriodStatus,
    ProcurementCategory,
    ProcurementRecord,
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
    create_shipment,
    create_transport_record,
    create_vehicle,
    detect_transport_anomalies,
    get_accessible_carriers,
    get_accessible_transports,
    get_accessible_vehicles,
    review_transport_record,
    submit_transport_record,
    update_carrier,
    update_transport_record,
    update_vehicle,
    upload_transport_evidence,
    user_can_access_transport,
    user_can_modify_transport,
    user_can_review_transport,
    user_can_submit_transport,
    validate_transport,
)

User = get_user_model()


def run_live_verification():
    print("=" * 80)
    print("PHASE 17: TRANSPORT & LOGISTICS MANAGEMENT — LIVE E2E VERIFICATION")
    print("=" * 80)

    total_checks = 0
    passed_checks = 0

    def assert_check(condition, description):
        nonlocal total_checks, passed_checks
        total_checks += 1
        if condition:
            passed_checks += 1
            print(f"  [PASS] {description}")
        else:
            print(f"  [FAIL] {description}")
            raise AssertionError(f"Check failed: {description}")

    # Use atomic rollback to keep database clean
    with transaction.atomic():
        timestamp = timezone.now().strftime("%Y%m%d%H%M%S")

        # ---------------------------------------------------------------------
        # 1. SETUP HIERARCHY, USERS, AND ROLES
        # ---------------------------------------------------------------------
        print("\n--- Step 1: Organizational Hierarchy & RBAC Actors ---")
        co_infra = Company.objects.create(name=f"MEIL Infra Division {timestamp}", code=f"INFRA_{timestamp[:4]}")
        co_energy = Company.objects.create(name=f"MEIL Energy Division {timestamp}", code=f"ENGY_{timestamp[:4]}")

        sub_infra = Subsidiary.objects.create(company=co_infra, name=f"Infra Hydro Sub {timestamp}", code=f"HYD_{timestamp[:4]}")
        sub_energy = Subsidiary.objects.create(company=co_energy, name=f"Solar Sub {timestamp}", code=f"SOL_{timestamp[:4]}")

        proj_polavaram = Project.objects.create(subsidiary=sub_infra, name=f"Polavaram Irrigation {timestamp}", code=f"POL_{timestamp[:4]}")
        proj_pavagada = Project.objects.create(subsidiary=sub_energy, name=f"Pavagada Solar Park {timestamp}", code=f"PAV_{timestamp[:4]}")

        site_headworks = Site.objects.create(project=proj_polavaram, name="Headworks Dam Site", code=f"HW_{timestamp[:4]}")
        site_canals = Site.objects.create(project=proj_polavaram, name="Right Canal Site", code=f"RC_{timestamp[:4]}")
        site_solar = Site.objects.create(project=proj_pavagada, name="Solar Sector 5", code=f"SS5_{timestamp[:4]}")

        period = ReportingPeriod.objects.create(
            company=co_infra,
            code=f"FY26-Q1-{timestamp[:4]}",
            name=f"FY26-Q1-{timestamp[:4]}",
            fiscal_year="2026-27",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 6, 30),
            status=PeriodStatus.OPEN,
        )

        role_site_mgr, _ = Role.objects.get_or_create(code=Role.Code.SITE_MANAGER, defaults={"name": "Site Manager"})
        role_sub_mgr, _ = Role.objects.get_or_create(code=Role.Code.SUBSIDIARY_MANAGER, defaults={"name": "Subsidiary Manager"})
        role_auditor, _ = Role.objects.get_or_create(code=Role.Code.AUDITOR, defaults={"name": "Auditor"})
        role_operator, _ = Role.objects.get_or_create(code=Role.Code.MEIL_OPERATOR, defaults={"name": "MEIL Operator"})

        user_sm_infra = User.objects.create_user(f"sm_infra_{timestamp}", f"sm_infra_{timestamp}@meil.in", "pass123")
        UserRole.objects.create(user=user_sm_infra, role=role_site_mgr, is_primary=True)
        SiteAssignment.objects.create(user=user_sm_infra, site=site_headworks)

        user_sm_solar = User.objects.create_user(f"sm_solar_{timestamp}", f"sm_solar_{timestamp}@meil.in", "pass123")
        UserRole.objects.create(user=user_sm_solar, role=role_site_mgr, is_primary=True)
        SiteAssignment.objects.create(user=user_sm_solar, site=site_solar)

        user_sub_mgr = User.objects.create_user(f"sub_mgr_{timestamp}", f"sub_mgr_{timestamp}@meil.in", "pass123")
        UserRole.objects.create(user=user_sub_mgr, role=role_sub_mgr, is_primary=True)
        CompanyAssignment.objects.create(user=user_sub_mgr, company=co_infra)
        SubsidiaryAssignment.objects.create(user=user_sub_mgr, subsidiary=sub_infra)

        user_auditor = User.objects.create_user(f"auditor_{timestamp}", f"auditor_{timestamp}@meil.in", "pass123")
        UserRole.objects.create(user=user_auditor, role=role_auditor, is_primary=True)

        user_operator = User.objects.create_user(f"op_{timestamp}", f"op_{timestamp}@meil.in", "pass123")
        UserRole.objects.create(user=user_operator, role=role_operator, is_primary=True)

        assert_check(user_sm_infra.has_role(Role.Code.SITE_MANAGER), "Site Manager assigned role verified")
        assert_check(user_sub_mgr.has_role(Role.Code.SUBSIDIARY_MANAGER), "Subsidiary Manager assigned role verified")

        # ---------------------------------------------------------------------
        # 2. CARRIER & FLEET REGISTRATION & ARCHIVAL
        # ---------------------------------------------------------------------
        print("\n--- Step 2: Carrier Master Lifecycle & Uniqueness ---")
        carrier = create_carrier(
            {
                "carrier_code": f"CARR-{timestamp[:6]}",
                "name": "Deccan Heavy Logistics Ltd",
                "legal_name": "Deccan Heavy Logistics Private Limited",
                "carrier_type": CarrierType.ROAD_CARRIER,
                "company": co_infra,
                "contact_person": "Venkatesh Rao",
                "contact_phone": "+91-9988776655",
            },
            user=user_operator,
        )
        assert_check(carrier.is_active, "Carrier created in ACTIVE status")
        assert_check(carrier.carrier_code.startswith("CARR-"), "Carrier assigned stable code")

        # Create Vehicles
        print("\n--- Step 3: Vehicle Master & Scope 1 vs Scope 3 Assets ---")
        veh_owned = create_vehicle(
            {
                "vehicle_identifier": f"VEH-OWN-{timestamp[:4]}",
                "registration_number": "ts-08-ab-1234",
                "carrier": carrier,
                "company": co_infra,
                "ownership_type": VehicleOwnershipType.OWNED,
                "vehicle_type": VehicleType.TRUCK_HEAVY,
                "fuel_type": FuelType.DIESEL,
                "capacity_payload": Decimal("30.00"),
                "capacity_unit": "MT",
            },
            user=user_operator,
        )
        assert_check(veh_owned.registration_number == "TS-08-AB-1234", "Vehicle registration uppercase normalized")
        assert_check(veh_owned.is_owned, "Owned vehicle classified for Scope 1 Mobile Combustion")

        veh_third_party = create_vehicle(
            {
                "vehicle_identifier": f"VEH-3P-{timestamp[:4]}",
                "registration_number": "ap-16-th-9988",
                "carrier": carrier,
                "ownership_type": VehicleOwnershipType.THIRD_PARTY,
                "vehicle_type": VehicleType.TRAILER,
                "capacity_payload": Decimal("40.00"),
            },
            user=user_operator,
        )
        assert_check(not veh_third_party.is_owned, "Third-party vehicle classified for Scope 3 Upstream Freight")

        # ---------------------------------------------------------------------
        # 3. SHIPMENT & PROCUREMENT LINKAGE
        # ---------------------------------------------------------------------
        print("\n--- Step 4: Shipment Consignment & Phase 16 Linkage ---")
        uom_mt, _ = UnitOfMeasure.objects.get_or_create(code="MT", defaults={"name": "Metric Ton", "dimension": UnitDimension.MASS, "symbol": "MT"})
        
        supplier = Supplier.objects.create(
            supplier_code=f"SUP-{timestamp[:6]}",
            name="Jindal Steel & Power Ltd",
            supplier_type=SupplierType.GOODS,
            company=co_infra,
        )
        procurement = ProcurementRecord.objects.create(
            procurement_number=f"PO-{timestamp[:8]}",
            site=site_headworks,
            project=proj_polavaram,
            company=co_infra,
            reporting_period=period,
            supplier=supplier,
            purchase_date=date(2026, 5, 10),
            total_amount=Decimal("1250000.00"),
            category=ProcurementCategory.RAW_MATERIAL,
        )

        shipment = create_shipment({
            "site": site_headworks,
            "procurement": procurement,
            "material_description": "Heavy Reinforcement Steel Bars (Fe550D)",
            "quantity": Decimal("28.50"),
            "unit": uom_mt,
            "weight_gross": Decimal("29.20"),
            "weight_net": Decimal("28.50"),
            "delivery_reference": f"LR-{timestamp[:6]}",
        })
        assert_check(shipment.procurement_id == procurement.id, "Shipment successfully bound to Phase 16 Procurement")

        # ---------------------------------------------------------------------
        # 4. TRANSPORT RECORD CREATION WITH ACTIVITY LINK
        # ---------------------------------------------------------------------
        print("\n--- Step 5: Authoritative Transport Record Creation ---")
        act_cat, _ = ActivityCategory.objects.get_or_create(code="TRANSPORT", defaults={"name": "Transport Logistics"})
        act_master = ActivityMaster.objects.create(
            code=f"ACT-TRN-{timestamp[:4]}",
            name="Heavy Commercial Haulage",
            category=act_cat,
            base_unit=uom_mt,
            status=MasterStatus.ACTIVE,
        )
        canonical_activity = ActivityRecord.objects.create(
            site=site_headworks,
            reporting_period=period,
            activity=act_master,
            measurement_date=date(2026, 5, 15),
            quantity=Decimal("28.50"),
            unit=uom_mt,
            notes="Consolidated road freight hauling",
        )

        transport = create_transport_record(
            data={
                "site": site_headworks,
                "project": proj_polavaram,
                "company": co_infra,
                "reporting_period": period,
                "transport_date": date(2026, 5, 15),
                "transport_mode": TransportMode.ROAD,
                "carrier": carrier,
                "vehicle": veh_owned,
                "shipment": shipment,
                "procurement": procurement,
                "origin_location": "Angul Steel Yard, Odisha",
                "destination_location": "Headworks Dam Site, Polavaram",
                "distance": Decimal("620.00"),
                "distance_unit": DistanceUnit.KM,
                "distance_source": DistanceSource.DOCUMENT,
                "freight_amount": Decimal("85000.00"),
                "fuel_quantity": Decimal("185.00"),
                "fuel_unit": "L",
                "activity_record": canonical_activity,
            },
            actor=user_sm_infra,
        )

        assert_check(transport.transport_reference.startswith("TRN-"), "Auto-generated institutional transport reference")
        assert_check(transport.scope_category == TransportScopeCategory.SCOPE_1, "Scope 1 inferred from owned fleet asset")
        assert_check(transport.activity_record_id == canonical_activity.id, "Direct lineage to canonical ESG ActivityRecord")

        # ---------------------------------------------------------------------
        # 5. EVIDENCE & OCR COMPARISON INTELLIGENCE
        # ---------------------------------------------------------------------
        print("\n--- Step 6: Evidence Attachment & OCR Comparison Reconciliation ---")
        mock_pdf = SimpleUploadedFile(
            "lorry_receipt_dam.pdf",
            b"%PDF-1.4 Mock transport manifest and weighment slip",
            content_type="application/pdf",
        )
        evidence = upload_transport_evidence(
            transport=transport,
            file_obj=mock_pdf,
            evidence_type=EvidenceType.LORRY_RECEIPT,
            actor=user_sm_infra,
            description="Signed Weighbridge Slip & Transporter LR",
        )
        assert_check(evidence.transport_record_id == transport.id, "Evidence file attached with transport_record foreign key")

        # Run Mock OCR
        ocr_run = OCRRun.objects.create(
            evidence=evidence,
            run_number=1,
            status=OCRStatus.COMPLETED,
            engine="tesseract",
            extracted_text="DECCAN HEAVY TS-08-AB-1234 DISTANCE 620 KM FREIGHT 85000",
        )
        OCRField.objects.create(
            ocr_run=ocr_run,
            field_name="vehicle_number",
            raw_value="TS-08-AB-1234",
            normalized_value="TS-08-AB-1234",
            confidence=Decimal("99.00"),
        )
        OCRField.objects.create(
            ocr_run=ocr_run,
            field_name="distance",
            raw_value="620.00",
            normalized_value="620.00",
            confidence=Decimal("96.50"),
        )
        OCRField.objects.create(
            ocr_run=ocr_run,
            field_name="freight_amount",
            raw_value="85000.00",
            normalized_value="85000.00",
            confidence=Decimal("98.00"),
        )

        ocr_comparison = compare_ocr_with_transport(transport, ocr_run)
        assert_check(ocr_comparison["overall_status"] == "MATCH", "OCR telemetry achieved 100% MATCH against transport data")
        assert_check(ocr_comparison["items"]["vehicle_number"]["status"] == "MATCH", "Vehicle plate OCR matches recorded value")
        assert_check(transport.distance == Decimal("620.00"), "Zero silent overwrite: original distance retained")

        # ---------------------------------------------------------------------
        # 6. DETERMINISTIC VALIDATION ENGINE
        # ---------------------------------------------------------------------
        print("\n--- Step 7: Deterministic Validation Engine Evaluation ---")
        val_result = validate_transport(transport, user=user_sm_infra)
        assert_check(val_result["is_valid"], "Transport record successfully validated (Status: VALID)")
        assert_check(val_result["errors_count"] == 0, "No blocking validation errors detected")

        # ---------------------------------------------------------------------
        # 7. ANOMALY DETECTION ENGINE
        # ---------------------------------------------------------------------
        print("\n--- Step 8: Anomaly Detection Engine (Payload & Duplicates) ---")
        # Overload test: 45 MT payload on 30 MT rated truck
        overloaded_shipment = create_shipment({
            "site": site_headworks,
            "material_description": "Overloaded Granite Stones",
            "quantity": Decimal("45.00"),
            "unit": uom_mt,
            "weight_net": Decimal("45.00"),
        })
        transport_overload = create_transport_record(
            data={
                "site": site_headworks,
                "project": proj_polavaram,
                "company": co_infra,
                "reporting_period": period,
                "transport_date": date(2026, 5, 18),
                "carrier": carrier,
                "vehicle": veh_owned,
                "shipment": overloaded_shipment,
                "origin_location": "Quarry",
                "destination_location": "Headworks",
                "distance": Decimal("40.00"),
            },
            actor=user_sm_infra,
        )
        anomalies = detect_transport_anomalies(transport_overload, user=user_sm_infra)
        assert_check(any(a["type"] == "PAYLOAD_OVERLOAD" for a in anomalies), "PAYLOAD_OVERLOAD detected when cargo (45 MT) > capacity (30 MT)")
        assert_check(transport_overload.has_anomalies, "has_anomalies telemetry flag asserted on transport record")

        # ---------------------------------------------------------------------
        # 8. WORKFLOW: SUBMISSION -> REVIEW -> CORRECTION -> RESUBMISSION
        # ---------------------------------------------------------------------
        print("\n--- Step 9: Governance Workflow (Submit -> Request Correction -> Resubmit -> Verify) ---")
        # Submit
        submit_transport_record(transport, user=user_sm_infra)
        transport.refresh_from_db()
        assert_check(transport.status == TransportStatus.SUBMITTED, "Transport status transitioned to SUBMITTED")
        assert_check(transport.is_locked, "Record locked against Site Manager edits")

        # Review: Request Correction
        review_transport_record(
            transport,
            action="REQUEST_CORRECTION",
            reviewer=user_sub_mgr,
            comments="Please confirm destination weighbridge calibration slip.",
            correction_notes="Verify tare weight slip.",
        )
        transport.refresh_from_db()
        assert_check(transport.status == TransportStatus.CORRECTION_REQUESTED, "Status transitioned to CORRECTION_REQUESTED")
        assert_check(not transport.is_locked, "Record unlocked for Site Manager correction")

        # Resubmit
        correct_transport_record(
            transport,
            data={"distance": Decimal("622.00")},
            user=user_sm_infra,
            explanation="Reconciled exact distance via calibrated toll bridge slip.",
        )
        transport.refresh_from_db()
        assert_check(transport.status == TransportStatus.SUBMITTED, "Transport resubmitted for review")
        assert_check(transport.distance == Decimal("622.00"), "Corrected distance updated")

        # Verify
        review_transport_record(
            transport,
            action="VERIFY",
            reviewer=user_sub_mgr,
            comments="Weighbridge telemetry verified. Approved.",
        )
        transport.refresh_from_db()
        assert_check(transport.status == TransportStatus.VERIFIED, "Transport verified by Subsidiary Manager")
        assert_check(transport.is_locked, "Transport permanently locked upon verification")

        # ---------------------------------------------------------------------
        # 9. OBJECT-LEVEL AUTHORIZATION & ANTI-IDOR DEFENSE
        # ---------------------------------------------------------------------
        print("\n--- Step 10: Object-Level Authorization & Anti-IDOR Security ---")
        # Site Manager Solar attempting to access Infra Transport
        assert_check(not user_can_access_transport(user_sm_solar, transport), "Cross-site access blocked for Site Manager Solar")
        assert_check(not user_can_modify_transport(user_sm_solar, transport), "Cross-site modification denied for Site Manager Solar")

        # Auditor is read-only
        assert_check(user_can_access_transport(user_auditor, transport), "Auditor has view access to enterprise transport")
        assert_check(not user_can_modify_transport(user_auditor, transport), "Auditor cannot modify transport")
        assert_check(not user_can_review_transport(user_auditor, transport), "Auditor cannot execute governance reviews")

        # Cross-company review blocked
        user_sub_mgr_solar = User.objects.create_user(f"sub_solar_{timestamp}", f"sub_solar_{timestamp}@meil.in", "pass123")
        UserRole.objects.create(user=user_sub_mgr_solar, role=role_sub_mgr, is_primary=True)
        CompanyAssignment.objects.create(user=user_sub_mgr_solar, company=co_energy)
        assert_check(not user_can_review_transport(user_sub_mgr_solar, transport), "Cross-company review denied for Subsidiary Manager Solar")

        # ---------------------------------------------------------------------
        # 10. AUDIT TRAIL COMPLIANCE
        # ---------------------------------------------------------------------
        print("\n--- Step 11: AuthAuditLog Trail Completeness ---")
        expected_events = [
            AuthAuditLog.EventType.CARRIER_CREATED,
            AuthAuditLog.EventType.VEHICLE_CREATED,
            AuthAuditLog.EventType.TRANSPORT_CREATED,
            AuthAuditLog.EventType.EVIDENCE_UPLOADED,
            AuthAuditLog.EventType.TRANSPORT_SUBMITTED,
            AuthAuditLog.EventType.CORRECTION_REQUESTED,
            AuthAuditLog.EventType.TRANSPORT_RESUBMITTED,
            AuthAuditLog.EventType.TRANSPORT_VERIFIED,
        ]
        for evt in expected_events:
            logged = AuthAuditLog.objects.filter(event_type=evt).exists()
            assert_check(logged, f"Audit event '{evt}' successfully registered in immutable ledger")

        # Soft archival of carrier & vehicle preserves historical references
        print("\n--- Step 12: Historical Integrity on Master Archival ---")
        archive_carrier(carrier, user=user_operator)
        archive_vehicle(veh_owned, user=user_operator)
        transport.refresh_from_db()
        assert_check(transport.carrier.status == CarrierStatus.ARCHIVED, "Carrier archived without breaking historical reference")
        assert_check(transport.vehicle.status == VehicleStatus.ARCHIVED, "Vehicle archived without breaking historical reference")

        # Rollback all synthetic data
        transaction.set_rollback(True)

    print("\n" + "=" * 80)
    print(f"PHASE 17 LIVE E2E VERIFICATION COMPLETE: {passed_checks}/{total_checks} CHECKS PASSED")
    print("ALL EMPIRICAL VALIDATIONS SUCCEEDED WITH ZERO REGRESSIONS")
    print("=" * 80)


if __name__ == "__main__":
    run_live_verification()
