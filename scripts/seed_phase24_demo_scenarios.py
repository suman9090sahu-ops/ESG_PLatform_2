"""
Deterministic Seeding Script for Phase 24 ESG Calculation & Emission Factor Scenarios.

Builds:
- Standard regulatory emission factors (IPCC 2006, CEA Baseline v19, India GHG Program)
- Demo Scenario 1: Deterministic Simple Calculation (1,000 L Diesel -> 2.6800 tCO2e)
- Demo Scenario 2: Multi-Site Reconciled Consolidation (Site A + Site B + Site C)
- Demo Scenario 3: Missing Factor Safety (Requires Configuration state with zero fabricated numbers)
- Demo Scenario 4: Auditor 6-Tier Traceability with Calculation Engine Ledger
"""

import os
import sys
import django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from datetime import date
from decimal import Decimal
from django.utils import timezone

from apps.core.calculation_services import calculate_activity_record
from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    ActivityRecord,
    AuthAuditLog,
    CalculationResult,
    CalculationStatus,
    Company,
    EmissionFactor,
    EmissionFactorStatus,
    Evidence,
    EvidenceStatus,
    OrganizationStatus,
    PeriodStatus,
    Project,
    RecordStatus,
    ReportingPeriod,
    Role,
    ScopeClassification,
    Site,
    Submission,
    SubmissionReview,
    SubmissionStatus,
    Subsidiary,
    UnitOfMeasure,
    User,
    ValidationStatus,
)


def seed_phase24_data():
    print("=" * 80)
    print("SEEDING PHASE 24: ESG CALCULATION, EMISSION FACTORS & DEMO SCENARIOS")
    print("=" * 80)

    # 1. Base Users
    admin_user = User.objects.filter(is_superuser=True).first() or User.objects.filter(username="admin").first()
    esg_mgr = User.objects.filter(username="esg_manager").first() or admin_user
    sub_mgr = User.objects.filter(username="subsidiary_manager").first() or admin_user
    site_mgr = User.objects.filter(username="site_manager").first() or admin_user
    auditor = User.objects.filter(username="auditor").first() or admin_user

    # 2. Reporting Period
    period, _ = ReportingPeriod.objects.get_or_create(
        code="FY2025-26",
        defaults={
            "name": "Financial Year 2025-2026",
            "start_date": "2025-04-01",
            "end_date": "2026-03-31",
            "status": PeriodStatus.OPEN,
            "created_by": esg_mgr,
        },
    )

    # 3. Units
    u_litre = UnitOfMeasure.objects.filter(code__in=["LITRE", "L", "LTR"]).first()
    u_kl = UnitOfMeasure.objects.filter(code__in=["KL", "KILOLITRE"]).first()
    u_kwh = UnitOfMeasure.objects.filter(code__in=["KWH", "KILOWATT HOUR"]).first()
    u_mwh = UnitOfMeasure.objects.filter(code__in=["MWH"]).first()
    u_kg = UnitOfMeasure.objects.filter(code__in=["KG", "KILOGRAM"]).first()
    u_tonne = UnitOfMeasure.objects.filter(code__in=["TONNE", "MT", "T"]).first()

    # 4. Standard Regulatory Emission Factors
    factors_spec = [
        {
            "code": "EF-DIESEL-STAT-2024",
            "name": "IPCC 2006 Diesel Stationary Combustion",
            "activity_code": "FUEL-DIESEL-STAT",
            "scope": ScopeClassification.SCOPE_1,
            "factor_value": Decimal("2.680000"),
            "factor_unit": "kg CO₂e / L",
            "input_unit": u_litre,
            "output_unit": "kg CO₂e",
            "source": "India GHG Program / IPCC 2006 Stationary Combustion",
            "effective_year": 2024,
            "version": "v1.0",
        },
        {
            "code": "EF-DIESEL-MOB-2024",
            "name": "IPCC 2006 Diesel Mobile Combustion",
            "activity_code": "FUEL-DIESEL-MOB",
            "scope": ScopeClassification.SCOPE_1,
            "factor_value": Decimal("2.680000"),
            "factor_unit": "kg CO₂e / L",
            "input_unit": u_litre,
            "output_unit": "kg CO₂e",
            "source": "India GHG Program / IPCC 2006 Mobile Combustion",
            "effective_year": 2024,
            "version": "v1.0",
        },
        {
            "code": "EF-PETROL-MOB-2024",
            "name": "IPCC 2006 Petrol Mobile Fleet Combustion",
            "activity_code": "FUEL-PETROL-MOB",
            "scope": ScopeClassification.SCOPE_1,
            "factor_value": Decimal("2.310000"),
            "factor_unit": "kg CO₂e / L",
            "input_unit": u_litre,
            "output_unit": "kg CO₂e",
            "source": "India GHG Program / IPCC 2006 Mobile Combustion",
            "effective_year": 2024,
            "version": "v1.0",
        },
        {
            "code": "EF-GRID-CEA-V19",
            "name": "CEA National Grid Average Baseline v19",
            "activity_code": "ELEC-GRID",
            "scope": ScopeClassification.SCOPE_2,
            "factor_value": Decimal("0.820000"),
            "factor_unit": "kg CO₂e / kWh",
            "input_unit": u_kwh,
            "output_unit": "kg CO₂e",
            "source": "Central Electricity Authority (CEA) CO₂ Baseline Database v19 (National Weighted Average)",
            "effective_year": 2024,
            "version": "v19.0",
        },
        {
            "code": "EF-SOLAR-CAPTIVE-2024",
            "name": "Captive Solar Renewable Generation",
            "activity_code": "ELEC-RENEWABLE-CAPTIVE",
            "scope": ScopeClassification.SCOPE_2,
            "factor_value": Decimal("0.000000"),
            "factor_unit": "kg CO₂e / kWh",
            "input_unit": u_kwh,
            "output_unit": "kg CO₂e",
            "source": "GHG Protocol Scope 2 Guidance (Zero-emission on-site renewable generation)",
            "effective_year": 2024,
            "version": "v1.0",
        },
    ]

    for f_data in factors_spec:
        act = ActivityMaster.objects.filter(code=f_data["activity_code"]).first()
        f_obj, created = EmissionFactor.objects.update_or_create(
            code=f_data["code"],
            defaults={
                "name": f_data["name"],
                "activity": act,
                "activity_code": f_data["activity_code"],
                "scope": f_data["scope"],
                "factor_value": f_data["factor_value"],
                "factor_unit": f_data["factor_unit"],
                "input_unit": f_data["input_unit"],
                "output_unit": f_data["output_unit"],
                "source": f_data["source"],
                "effective_year": f_data["effective_year"],
                "version": f_data["version"],
                "status": EmissionFactorStatus.ACTIVE,
                "created_by": esg_mgr,
                "updated_by": esg_mgr,
            },
        )
        print(f"  [Factor] {f_obj.code} ({f_obj.factor_value} {f_obj.factor_unit}) - {'CREATED' if created else 'UPDATED'}")

    # Resolve Hierarchy entities aligned with ReportingPeriod company
    company = period.company or Company.objects.first()
    sub = Subsidiary.objects.filter(company=company).first()
    if not sub:
        sub = Subsidiary.objects.create(company=company, name=f"{company.name} Infrastructure Div", code=f"{company.code}-INF")
    proj = Project.objects.filter(subsidiary=sub).first()
    if not proj:
        proj = Project.objects.create(subsidiary=sub, name=f"{sub.name} Flagship Project", code=f"{sub.code}-PRJ01")

    site_a = Site.objects.filter(project=proj).first()
    if not site_a:
        site_a = Site.objects.create(
            project=proj,
            name=f"{proj.name} - Site Alpha",
            code=f"{proj.code}-STA",
            facility_type="Primary Facility",
            location="Zone A, Andhra Pradesh",
            status=OrganizationStatus.ACTIVE,
        )

    site_b = Site.objects.filter(project=proj).exclude(id=site_a.id).first()
    if not site_b:
        site_b = Site.objects.create(
            project=proj,
            name=f"{proj.name} - Site Bravo",
            code=f"{proj.code}-STB",
            facility_type="Substation / Staging",
            location="Zone B, Andhra Pradesh",
            status=OrganizationStatus.ACTIVE,
        )

    site_c = Site.objects.filter(project=proj).exclude(id__in=[site_a.id, site_b.id]).first()
    if not site_c:
        site_c = Site.objects.create(
            project=proj,
            name=f"{proj.name} - Site Charlie",
            code=f"{proj.code}-STC",
            facility_type="Fabrication Yard",
            location="Zone C, Andhra Pradesh",
            status=OrganizationStatus.ACTIVE,
        )

    act_diesel = ActivityMaster.objects.filter(code="FUEL-DIESEL-STAT").first()
    act_grid = ActivityMaster.objects.filter(code="ELEC-GRID").first()

    # -------------------------------------------------------------------------
    # SCENARIO 1: SIMPLE DETERMINISTIC CALCULATION
    # -------------------------------------------------------------------------
    # SCENARIO 1: SIMPLE DETERMINISTIC CALCULATION
    # -------------------------------------------------------------------------
    # Fuel: 1,000 L * 2.68 kg CO2e / 1,000 = 2.6800 tCO2e
    print("\n--- SCENARIO 1: SIMPLE DETERMINISTIC CALCULATION ---")
    demo_meas_date = date(2025, 10, 15)

    rec_s1, _ = ActivityRecord.objects.get_or_create(
        evidence_reference="DEMO-P24-SCENARIO-1-DIESEL",
        defaults={
            "site": site_a,
            "reporting_period": period,
            "activity": act_diesel,
            "measurement_date": demo_meas_date,
            "quantity": Decimal("1000.0000"),
            "unit": u_litre,
            "notes": "Demo Scenario 1: Stationary DG Set Fuel Consumption (Deterministic 1,000 L)",
            "status": RecordStatus.VERIFIED,
            "validation_status": ValidationStatus.VALID,
            "created_by": site_mgr,
            "updated_by": sub_mgr,
        },
    )
    rec_s1.measurement_date = demo_meas_date
    rec_s1.quantity = Decimal("1000.0000")
    rec_s1.unit = u_litre
    rec_s1.status = RecordStatus.VERIFIED
    rec_s1.validation_status = ValidationStatus.VALID
    rec_s1.save()

    calc_s1 = calculate_activity_record(rec_s1, user=esg_mgr, force_recalculate=True)
    print(f"  Scenario 1 Result: Record #{rec_s1.id} -> {calc_s1.calculated_value} {calc_s1.result_unit} (Status: {calc_s1.status})")
    assert calc_s1.calculated_value == Decimal("2.6800"), f"Expected 2.6800, got {calc_s1.calculated_value}"

    # -------------------------------------------------------------------------
    # SCENARIO 2: MULTI-SITE RECONCILED CONSOLIDATION
    # -------------------------------------------------------------------------
    # Site A: 1,000 L (2.6800 tCO2e)
    # Site B: 2,000 L (5.3600 tCO2e)
    # Site C: 3,000 L (8.0400 tCO2e)
    # Project Total: 6,000 L -> 16.0800 tCO2e
    print("\n--- SCENARIO 2: MULTI-SITE CONSOLIDATION RECONCILIATION ---")
    rec_s2_b, _ = ActivityRecord.objects.get_or_create(
        evidence_reference="DEMO-P24-SCENARIO-2-SITE-B",
        defaults={
            "site": site_b,
            "reporting_period": period,
            "activity": act_diesel,
            "measurement_date": demo_meas_date,
            "quantity": Decimal("2000.0000"),
            "unit": u_litre,
            "notes": "Demo Scenario 2: Multi-Site Consolidation Site B (2,000 L)",
            "status": RecordStatus.VERIFIED,
            "validation_status": ValidationStatus.VALID,
            "created_by": site_mgr,
            "updated_by": sub_mgr,
        },
    )
    rec_s2_b.measurement_date = demo_meas_date
    rec_s2_b.quantity = Decimal("2000.0000")
    rec_s2_b.status = RecordStatus.VERIFIED
    rec_s2_b.save()
    calc_s2_b = calculate_activity_record(rec_s2_b, user=esg_mgr, force_recalculate=True)

    rec_s2_c, _ = ActivityRecord.objects.get_or_create(
        evidence_reference="DEMO-P24-SCENARIO-2-SITE-C",
        defaults={
            "site": site_c,
            "reporting_period": period,
            "activity": act_diesel,
            "measurement_date": demo_meas_date,
            "quantity": Decimal("3000.0000"),
            "unit": u_litre,
            "notes": "Demo Scenario 2: Multi-Site Consolidation Site C (3,000 L)",
            "status": RecordStatus.VERIFIED,
            "validation_status": ValidationStatus.VALID,
            "created_by": site_mgr,
            "updated_by": sub_mgr,
        },
    )
    rec_s2_c.measurement_date = demo_meas_date
    rec_s2_c.quantity = Decimal("3000.0000")
    rec_s2_c.status = RecordStatus.VERIFIED
    rec_s2_c.save()
    calc_s2_c = calculate_activity_record(rec_s2_c, user=esg_mgr, force_recalculate=True)

    total_s2_emissions = calc_s1.calculated_value + calc_s2_b.calculated_value + calc_s2_c.calculated_value
    print(f"  Site A: {calc_s1.calculated_value} tCO2e")
    print(f"  Site B: {calc_s2_b.calculated_value} tCO2e")
    print(f"  Site C: {calc_s2_c.calculated_value} tCO2e")
    print(f"  Project Total: {total_s2_emissions} tCO2e (Reconciled: 16.0800 tCO2e)")
    assert total_s2_emissions == Decimal("16.0800"), f"Expected 16.0800, got {total_s2_emissions}"

    # -------------------------------------------------------------------------
    # SCENARIO 3: MISSING FACTOR SAFETY (REQUIRES CONFIGURATION)
    # -------------------------------------------------------------------------
    print("\n--- SCENARIO 3: MISSING FACTOR CONFIGURATION REQUIRED ---")
    cat_env = ActivityCategory.objects.first()
    act_unconfigured, _ = ActivityMaster.objects.get_or_create(
        code="ACT-SF6-INSULATION-GAS",
        defaults={
            "name": "Sulfur Hexafluoride (SF6) High-Voltage Switchgear Gas",
            "category": cat_env,
            "activity_type": "FUGITIVE_EMISSIONS",
            "base_unit": u_kg,
            "scope_classification": ScopeClassification.SCOPE_1,
            "status": "ACTIVE",
            "is_active": True,
        },
    )

    # Ensure no factor exists for this activity
    EmissionFactor.objects.filter(activity_code="ACT-SF6-INSULATION-GAS").delete()

    rec_s3, _ = ActivityRecord.objects.get_or_create(
        evidence_reference="DEMO-P24-SCENARIO-3-MISSING-FACTOR",
        defaults={
            "site": site_a,
            "reporting_period": period,
            "activity": act_unconfigured,
            "measurement_date": demo_meas_date,
            "quantity": Decimal("45.0000"),
            "unit": u_kg,
            "notes": "Demo Scenario 3: SF6 Fugitive Gas without configured emission factor",
            "status": RecordStatus.VERIFIED,
            "validation_status": ValidationStatus.VALID,
            "created_by": site_mgr,
        },
    )
    rec_s3.measurement_date = demo_meas_date
    rec_s3.activity = act_unconfigured
    rec_s3.quantity = Decimal("45.0000")
    rec_s3.unit = u_kg
    rec_s3.save()

    calc_s3 = calculate_activity_record(rec_s3, user=esg_mgr, force_recalculate=True)
    print(f"  Scenario 3 Result: Record #{rec_s3.id} -> Status: {calc_s3.status}")
    print(f"  Scenario 3 Notice: {calc_s3.error_message}")
    print(f"  Scenario 3 Value: {calc_s3.calculated_value} (Zero fabricated numbers)")
    assert calc_s3.status == CalculationStatus.REQUIRES_CONFIGURATION, f"Expected REQUIRES_CONFIGURATION, got {calc_s3.status}"
    assert calc_s3.calculated_value == Decimal("0.0000"), f"Expected 0.0000, got {calc_s3.calculated_value}"

    # -------------------------------------------------------------------------
    # SCENARIO 4: AUDITOR 6-TIER TRACEABILITY
    # -------------------------------------------------------------------------
    print("\n--- SCENARIO 4: AUDITOR 6-TIER TRACEABILITY LINEAGE ---")
    # Link evidence, submission, and review to Scenario 1 record for full trace demonstration
    sub_rec, _ = Submission.objects.get_or_create(
        activity_record=rec_s1,
        submission_number=1,
        defaults={
            "site": site_a,
            "reporting_period": period,
            "submitted_by": site_mgr,
            "status": SubmissionStatus.VERIFIED,
            "validation_status": ValidationStatus.VALID,
            "is_current": True,
        },
    )
    review_obj, _ = SubmissionReview.objects.get_or_create(
        submission=sub_rec,
        action="VERIFY",
        defaults={
            "reviewer": sub_mgr,
            "previous_status": SubmissionStatus.SUBMITTED,
            "new_status": SubmissionStatus.VERIFIED,
            "comments": "Audited and verified against weighbridge ticket and invoice fuel meters.",
        },
    )

    ev_doc, _ = Evidence.objects.get_or_create(
        activity_record=rec_s1,
        defaults={
            "evidence_type": "INVOICE",
            "original_filename": "diesel_delivery_inv_2025.pdf",
            "file_size": 245100,
            "file_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "status": EvidenceStatus.ACTIVE,
            "uploaded_by": site_mgr,
        },
    )

    # Auth audit log entry
    AuthAuditLog.objects.create(
        user=auditor,
        event_type=AuthAuditLog.EventType.CALCULATION_EXECUTED,
        resource_accessed=f"CalculationResult:{calc_s1.id}:Record:{rec_s1.id}",
        details=f"Auditor lineage trace validated: {calc_s1.formula_repr}",
        success=True,
    )
    print(f"  Scenario 4 Lineage Verified: Record #{rec_s1.id} -> Submission #{sub_rec.id} -> Evidence #{ev_doc.id} -> Review by {sub_mgr.username}")

    print("\n" + "=" * 80)
    print("ALL PHASE 24 DEMO SCENARIOS SUCCESSFULLY SEEDED & VERIFIED!")
    print("=" * 80)


if __name__ == "__main__":
    seed_phase24_data()
