"""
Authoritative Seed Script for Phase 23 Demo Scenarios:
Evidence, OCR, Validation & ESG Anomaly Intelligence.

Creates:
1. Demo Users:
   - Site Manager: sm_p23 / Pass123!
   - Subsidiary Manager: sub_p23 / Pass123!
   - Auditor: auditor_p23 / Pass123!
2. Hierarchy:
   - Company: MEIL Energy & Infra Group (MEIL-ENERGY-P23)
   - Subsidiary: Clean Power & Utilities Division (MEIL-POWER-P23)
   - Project: Kurnool Ultra Mega Solar Project (PRJ-KURNOOL-P23)
   - Site: Inverter Substation Alpha (SITE-SUB-A)
3. SCENARIO A (Clean Data Flow):
   - Operational quantity: 25,000 kWh
   - Attached Evidence: clean_power_invoice_apr2026.pdf
   - OCR Run: Extracted 25,000 kWh (Match: 100%)
   - Validation Run: VALID (All layers PASS)
   - Anomaly Scan: 0 anomalies
   - Status: VERIFIED by Subsidiary Manager
   - Appears in Auditor Lineage & Reporting Disclosures
4. SCENARIO B (Problem Data Flow):
   - Operational quantity: 45,000 kWh
   - Attached Evidence: power_invoice_discrepant.pdf
   - OCR Run: Extracted 38,000 kWh (Discrepancy: 15.5% Significant Difference)
   - Validation Run: INVALID (EVID_OCR_COMPARISON fails with blocking ERROR)
   - Anomaly: CRITICAL OCR_MISMATCH anomaly with explainable diagnostics
   - Status: Submitted -> Correction Requested with active remediation prompt
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    ActivityRecord,
    AnomalySeverity,
    AnomalyStatus,
    Company,
    CompanyAssignment,
    CorrectionRequest,
    CorrectionStatus,
    Evidence,
    EvidenceStatus,
    EvidenceType,
    MasterStatus,
    OCRField,
    OCRRun,
    OCRStatus,
    OrganizationStatus,
    PeriodStatus,
    Project,
    RecordStatus,
    ReportingPeriod,
    ReviewAction,
    Role,
    Site,
    SiteAssignment,
    Submission,
    SubmissionReview,
    SubmissionStatus,
    Subsidiary,
    SubsidiaryAssignment,
    UnitDimension,
    UnitOfMeasure,
    UserRole,
    ValidationResult,
    ValidationSeverity,
    ValidationStatus,
)
from apps.core.ocr_services import compare_ocr_with_activity_record
from apps.core.validation_services import execute_validation_run, seed_standard_validation_rules
from apps.core.anomaly_services import detect_anomalies_for_record, ensure_default_anomaly_rules
from apps.core.review_services import request_correction_submission, verify_submission

User = get_user_model()


def seed_phase23_demo():
    print("=" * 80)
    print("  SEEDING PHASE 23 DEMO SCENARIOS (EVIDENCE, OCR & ANOMALY INTELLIGENCE)")
    print("=" * 80)

    # 1. Standard rules setup
    seed_standard_validation_rules()
    ensure_default_anomaly_rules()

    # 2. Roles
    r_site, _ = Role.objects.get_or_create(code=Role.Code.SITE_MANAGER, defaults={"name": "Site Manager"})
    r_sub, _ = Role.objects.get_or_create(code=Role.Code.SUBSIDIARY_MANAGER, defaults={"name": "Subsidiary Manager"})
    r_aud, _ = Role.objects.get_or_create(code=Role.Code.AUDITOR, defaults={"name": "Auditor"})

    # 3. Hierarchy
    company, _ = Company.objects.get_or_create(
        code="MEIL-ENERGY-P23",
        defaults={"name": "MEIL Energy & Infra Group", "status": OrganizationStatus.ACTIVE},
    )
    subsidiary, _ = Subsidiary.objects.get_or_create(
        code="MEIL-POWER-P23",
        defaults={"company": company, "name": "Clean Power & Utilities Division", "status": OrganizationStatus.ACTIVE},
    )
    project, _ = Project.objects.get_or_create(
        code="PRJ-KURNOOL-P23",
        defaults={"subsidiary": subsidiary, "name": "Kurnool Ultra Mega Solar Project", "status": OrganizationStatus.ACTIVE},
    )
    site, _ = Site.objects.get_or_create(
        code="SITE-SUB-A",
        defaults={"project": project, "name": "Inverter Substation Alpha", "status": OrganizationStatus.ACTIVE},
    )

    # 4. Reporting Period
    period, _ = ReportingPeriod.objects.get_or_create(
        code="FY2026-Q1",
        company=company,
        defaults={
            "name": "FY 2026 Annual",
            "start_date": timezone.now().date().replace(month=1, day=1),
            "end_date": timezone.now().date().replace(month=12, day=31),
            "status": PeriodStatus.OPEN,
        },
    )
    period.start_date = timezone.now().date().replace(month=1, day=1)
    period.end_date = timezone.now().date().replace(month=12, day=31)
    period.save()

    # 5. Units & Activity
    kwh, _ = UnitOfMeasure.objects.get_or_create(
        code="KWH-P23",
        defaults={
            "name": "Kilowatt Hour",
            "symbol": "kWh",
            "dimension": UnitDimension.ENERGY,
            "is_active": True,
        },
    )
    cat, _ = ActivityCategory.objects.get_or_create(
        code="ELEC-P23",
        defaults={"name": "Electricity & Power Generation", "is_active": True},
    )
    activity, _ = ActivityMaster.objects.get_or_create(
        code="ACT-GRID-ELEC-P23",
        defaults={
            "category": cat,
            "name": "Substation Auxiliary Grid Electricity",
            "base_unit": kwh,
            "status": MasterStatus.ACTIVE,
            "validation_rules": {"evidence_mandatory": True},
        },
    )
    activity.allowed_units.add(kwh)

    # 6. Users
    sm_user, _ = User.objects.get_or_create(
        username="sm_p23",
        defaults={"email": "sm_p23@meil.test", "first_name": "Kavitha", "last_name": "Rao"},
    )
    sm_user.set_password("Pass123!")
    sm_user.save()
    UserRole.objects.get_or_create(user=sm_user, role=r_site, defaults={"is_primary": True})
    SiteAssignment.objects.get_or_create(user=sm_user, site=site)

    sub_user, _ = User.objects.get_or_create(
        username="sub_p23",
        defaults={"email": "sub_p23@meil.test", "first_name": "Naveen", "last_name": "Varma"},
    )
    sub_user.set_password("Pass123!")
    sub_user.save()
    UserRole.objects.get_or_create(user=sub_user, role=r_sub, defaults={"is_primary": True})
    SubsidiaryAssignment.objects.get_or_create(user=sub_user, subsidiary=subsidiary)

    aud_user, _ = User.objects.get_or_create(
        username="auditor_p23",
        defaults={"email": "auditor_p23@meil.test", "first_name": "Pooja", "last_name": "Menon"},
    )
    aud_user.set_password("Pass123!")
    aud_user.save()
    UserRole.objects.get_or_create(user=aud_user, role=r_aud, defaults={"is_primary": True})
    CompanyAssignment.objects.get_or_create(user=aud_user, company=company)

    print("[+] Users and Hierarchy Seeded:")
    print("    - Site Manager: sm_p23 / Pass123! -> Site Inverter Substation Alpha")
    print("    - Subsidiary Manager: sub_p23 / Pass123! -> Clean Power & Utilities Division")
    print("    - Auditor: auditor_p23 / Pass123! -> MEIL Energy & Infra Group")

    # =========================================================================
    # SCENARIO A: CLEAN RECORD (VERIFIED & INCLUDED IN REPORTING)
    # =========================================================================
    rec_clean, _ = ActivityRecord.objects.get_or_create(
        site=site,
        reporting_period=period,
        activity=activity,
        quantity=Decimal("25000.00"),
        defaults={
            "unit": kwh,
            "measurement_date": timezone.now().date(),
            "status": RecordStatus.VERIFIED,
            "created_by": sm_user,
            "notes": "Auxiliary substation monthly consumption per DISCOM bill #AP-2026-0491.",
        },
    )

    ev_clean, _ = Evidence.objects.get_or_create(
        activity_record=rec_clean,
        original_filename="clean_power_invoice_apr2026.pdf",
        defaults={
            "file": SimpleUploadedFile("clean_power_invoice_apr2026.pdf", b"%PDF-1.4 APCPDCL Electricity Invoice 25,000 kWh", content_type="application/pdf"),
            "file_type": "application/pdf",
            "file_size": 24500,
            "file_hash": "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90",
            "evidence_type": EvidenceType.UTILITY_BILL,
            "uploaded_by": sm_user,
            "status": EvidenceStatus.ACTIVE,
        },
    )

    ocr_clean, _ = OCRRun.objects.get_or_create(
        evidence=ev_clean,
        run_number=1,
        defaults={
            "status": OCRStatus.COMPLETED,
            "engine": "PaddleOCR-v4-HighAccuracy",
            "confidence": Decimal("99.20"),
            "is_latest": True,
            "extracted_text": "APCPDCL Electricity Bill\nAccount: 0491823\nPeriod: Apr 2026\nConsumption: 25000 kWh\nAmount: INR 187,500.00\nSupplier: AP State Power Distribution",
        },
    )
    OCRField.objects.get_or_create(
        ocr_run=ocr_clean,
        field_name="quantity",
        defaults={"raw_value": "25000", "normalized_value": "25000", "unit": "kWh", "confidence": Decimal("99.40")},
    )
    OCRField.objects.get_or_create(
        ocr_run=ocr_clean,
        field_name="invoice_number",
        defaults={"raw_value": "AP-2026-0491", "normalized_value": "AP-2026-0491", "confidence": Decimal("98.90")},
    )
    OCRField.objects.get_or_create(
        ocr_run=ocr_clean,
        field_name="supplier",
        defaults={"raw_value": "APCPDCL", "normalized_value": "APCPDCL", "confidence": Decimal("99.10")},
    )
    comp_clean = compare_ocr_with_activity_record(ocr_clean)
    ocr_clean.raw_metadata["comparison"] = comp_clean
    ocr_clean.save()

    val_clean = execute_validation_run(rec_clean, executed_by=sm_user)
    detect_anomalies_for_record(rec_clean, user=sm_user)

    sub_clean, _ = Submission.objects.get_or_create(
        activity_record=rec_clean,
        site=site,
        reporting_period=period,
        submission_number=1,
        defaults={
            "submitted_by": sm_user,
            "status": SubmissionStatus.VERIFIED,
            "validation_run": val_clean,
            "validation_status": ValidationStatus.VALID,
            "comments": "Substation auxiliary consumption aligned with APCPDCL meter invoice.",
            "snapshot_data": {
                "quantity": "25000.00",
                "unit_symbol": "kWh",
                "measurement_date": rec_clean.measurement_date.isoformat(),
            },
        },
    )

    SubmissionReview.objects.get_or_create(
        submission=sub_clean,
        reviewer=sub_user,
        defaults={
            "action": ReviewAction.VERIFY,
            "previous_status": SubmissionStatus.SUBMITTED,
            "new_status": SubmissionStatus.VERIFIED,
            "comments": "Verified. 100% OCR Match (25,000 kWh) with DISCOM bill #AP-2026-0491. Zero anomalies.",
        },
    )
    print(f"[+] Scenario A (Clean Record) Seeded: Record #{rec_clean.id} (Submission #{sub_clean.id}) -> VERIFIED")

    # =========================================================================
    # SCENARIO B: PROBLEM RECORD (MISMATCH, ANOMALY, CORRECTION REQUEST)
    # =========================================================================
    rec_prob, _ = ActivityRecord.objects.get_or_create(
        site=site,
        reporting_period=period,
        activity=activity,
        quantity=Decimal("45000.00"),
        defaults={
            "unit": kwh,
            "measurement_date": timezone.now().date(),
            "status": RecordStatus.SUBMITTED,
            "created_by": sm_user,
            "notes": "Estimated operational consumption for high-yield solar collection period.",
        },
    )

    ev_prob, _ = Evidence.objects.get_or_create(
        activity_record=rec_prob,
        original_filename="power_invoice_discrepant.pdf",
        defaults={
            "file": SimpleUploadedFile("power_invoice_discrepant.pdf", b"%PDF-1.4 APCPDCL Actual Meter Invoice 38,000 kWh", content_type="application/pdf"),
            "file_type": "application/pdf",
            "file_size": 28200,
            "file_hash": "f9e8d7c6b5a41029384756abcdef0123f9e8d7c6b5a41029384756abcdef0123",
            "evidence_type": EvidenceType.UTILITY_BILL,
            "uploaded_by": sm_user,
            "status": EvidenceStatus.ACTIVE,
        },
    )

    ocr_prob, _ = OCRRun.objects.get_or_create(
        evidence=ev_prob,
        run_number=1,
        defaults={
            "status": OCRStatus.COMPLETED,
            "engine": "PaddleOCR-v4-HighAccuracy",
            "confidence": Decimal("95.80"),
            "is_latest": True,
            "extracted_text": "APCPDCL Electricity Bill\nAccount: 0491823\nPeriod: Apr 2026\nConsumption: 38000 kWh\nAmount: INR 285,000.00\nSupplier: AP State Power Distribution",
        },
    )
    OCRField.objects.get_or_create(
        ocr_run=ocr_prob,
        field_name="quantity",
        defaults={"raw_value": "38000", "normalized_value": "38000", "unit": "kWh", "confidence": Decimal("96.20")},
    )
    OCRField.objects.get_or_create(
        ocr_run=ocr_prob,
        field_name="invoice_number",
        defaults={"raw_value": "AP-2026-0512", "normalized_value": "AP-2026-0512", "confidence": Decimal("95.40")},
    )
    comp_prob = compare_ocr_with_activity_record(ocr_prob)
    ocr_prob.raw_metadata["comparison"] = comp_prob
    ocr_prob.save()

    val_prob = execute_validation_run(rec_prob, executed_by=sm_user)
    anoms_prob = detect_anomalies_for_record(rec_prob, user=sm_user)

    sub_prob, _ = Submission.objects.get_or_create(
        activity_record=rec_prob,
        site=site,
        reporting_period=period,
        submission_number=1,
        defaults={
            "submitted_by": sm_user,
            "status": SubmissionStatus.CORRECTION_REQUESTED,
            "validation_run": val_prob,
            "validation_status": val_prob.status,
            "comments": "Auxiliary grid electricity submission pending validation audit.",
            "snapshot_data": {
                "quantity": "45000.00",
                "unit_symbol": "kWh",
                "measurement_date": rec_prob.measurement_date.isoformat(),
            },
        },
    )

    corr_prob, _ = CorrectionRequest.objects.get_or_create(
        submission=sub_prob,
        defaults={
            "activity_record": rec_prob,
            "requested_by": sub_user,
            "reason": "Significant OCR Discrepancy: Entered 45,000 kWh vs extracted utility bill 38,000 kWh (15.5% discrepancy).",
            "required_correction": "Review uploaded APCPDCL bill and align operational quantity with invoice value (38,000 kWh).",
            "status": CorrectionStatus.OPEN,
            "site_manager_notes": "",
        },
    )
    print(f"[+] Scenario B (Problem Record) Seeded: Record #{rec_prob.id} (Submission #{sub_prob.id}) -> CORRECTION REQUESTED")
    print(f"    - Discrepancy: Entered 45,000 kWh vs OCR Extracted 38,000 kWh")
    print(f"    - Validation Status: {val_prob.status}")
    print(f"    - Anomalies Detected: {len(anoms_prob)}")
    print(f"    - Correction Request #{corr_prob.id} created for Site Manager.")
    print("=" * 80)
    print("  SEEDING COMPLETE!")
    print("=" * 80)


if __name__ == "__main__":
    seed_phase23_demo()
