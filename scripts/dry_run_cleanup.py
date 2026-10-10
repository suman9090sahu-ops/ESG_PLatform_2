import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
import django
django.setup()

from django.db import transaction
from django.db.models import Count, Q
from apps.core.models import (
    Company, Subsidiary, Project, Site,
    User, Role, UserRole,
    CompanyAssignment, SubsidiaryAssignment, ProjectAssignment, SiteAssignment,
    ReportingPeriod, ActivityCategory, UnitOfMeasure, ActivityMaster,
    ActivityRecord, ActivityRevision, Evidence,
    ValidationRule, ValidationRun, ValidationResult,
    OCRRun, OCRField,
    Submission, SubmissionReview, CorrectionRequest,
    AnomalyRule, AnomalyDetectionRun, AnomalyRecord,
    Supplier, ProcurementRecord, ProcurementItem,
    Carrier, Vehicle, Shipment, TransportRecord,
    EmissionFactor, CalculationResult, AuthAuditLog, Scope3Category
)

def simulate_dry_run():
    print("=" * 80)
    print("DRY-RUN DELETION PLAN & INTEGRITY VALIDATION")
    print("=" * 80)

    # Identify Canonical Entities
    canonical_company = Company.objects.get(code="MEIL-ENT")
    canonical_subsidiaries = Subsidiary.objects.filter(code__in=["MEIL-HYDRO", "MEIL-SOLAR"])
    canonical_projects = Project.objects.filter(code__in=["PRJ-POL-01", "PRJ-KRN-01"])
    canonical_sites = Site.objects.filter(code__in=["SITE-POL-101", "SITE-POL-102", "SITE-KRN-201"])
    canonical_periods = ReportingPeriod.objects.filter(
        company=canonical_company,
        code__in=["FY2024-25", "FY2025-26", "FY2026-27"]
    )

    print(f"\n[1] CANONICAL TARGET ENTITIES IDENTIFIED (PROTECTED)")
    print(f"  Canonical Company: {canonical_company.code} (ID: {canonical_company.id}) - {canonical_company.name}")
    print(f"  Canonical Subsidiaries ({canonical_subsidiaries.count()}): {[s.code for s in canonical_subsidiaries]}")
    print(f"  Canonical Projects ({canonical_projects.count()}): {[p.code for p in canonical_projects]}")
    print(f"  Canonical Sites ({canonical_sites.count()}): {[st.code for st in canonical_sites]}")
    print(f"  Canonical Periods ({canonical_periods.count()}): {[rp.code for rp in canonical_periods]}")

    # Check Suppliers referencing disposable companies
    disposable_companies = Company.objects.exclude(id=canonical_company.id)
    suppliers_to_reassign = Supplier.objects.filter(company__in=disposable_companies)
    print(f"\n[2] REUSABLE REFERENCE DATA (PROTECTED)")
    print(f"  Total Suppliers: {Supplier.objects.count()} (Preserved)")
    print(f"  Suppliers currently linked to disposable companies: {suppliers_to_reassign.count()}")
    print(f"    -> These will have company reassigned to {canonical_company.code} (or None) before company cleanup.")

    # Check Audit Logs
    print(f"\n[3] AUDIT TRAIL PROTECTION")
    print(f"  AuthAuditLog count: {AuthAuditLog.objects.count()} (100% Preserved - Zero deletions)")

    # Disposable Transaction Records
    print(f"\n[4] DISPOSABLE TRANSACTION & WORKFLOW DATA PROPOSED FOR DELETION")
    records_to_delete = {
        "ProcurementItem": ProcurementItem.objects.count(),
        "ProcurementRecord": ProcurementRecord.objects.count(),
        "CalculationResult": CalculationResult.objects.count(),
        "CorrectionRequest": CorrectionRequest.objects.count(),
        "SubmissionReview": SubmissionReview.objects.count(),
        "Submission": Submission.objects.count(),
        "OCRField": OCRField.objects.count(),
        "OCRRun": OCRRun.objects.count(),
        "Evidence": Evidence.objects.count(),
        "ValidationResult": ValidationResult.objects.count(),
        "ValidationRun": ValidationRun.objects.count(),
        "AnomalyRecord": AnomalyRecord.objects.count(),
        "AnomalyDetectionRun": AnomalyDetectionRun.objects.count(),
        "ActivityRevision": ActivityRevision.objects.count(),
        "ActivityRecord": ActivityRecord.objects.count(),
    }

    for name, cnt in records_to_delete.items():
        print(f"  {name:<25}: {cnt} rows proposed for deletion")

    # Disposable Organization Records
    disposable_periods = ReportingPeriod.objects.exclude(id__in=canonical_periods.values_list('id', flat=True))
    disposable_sites = Site.objects.exclude(id__in=canonical_sites.values_list('id', flat=True))
    disposable_projects = Project.objects.exclude(id__in=canonical_projects.values_list('id', flat=True))
    disposable_subsidiaries = Subsidiary.objects.exclude(id__in=canonical_subsidiaries.values_list('id', flat=True))

    print(f"\n[5] DISPOSABLE ORGANIZATION ENTITIES PROPOSED FOR DELETION")
    print(f"  Reporting Periods: {disposable_periods.count()} to delete ({[rp.code for rp in disposable_periods]})")
    print(f"  Sites: {disposable_sites.count()} to delete ({[st.code for st in disposable_sites]})")
    print(f"  Projects: {disposable_projects.count()} to delete ({[p.code for p in disposable_projects]})")
    print(f"  Subsidiaries: {disposable_subsidiaries.count()} to delete ({[s.code for s in disposable_subsidiaries]})")
    print(f"  Companies: {disposable_companies.count()} to delete ({[c.code for c in disposable_companies]})")

    # Affected Files
    evidence_files = [e.file.name for e in Evidence.objects.all() if e.file]
    print(f"\n[6] EVIDENCE FILES AFFECTED")
    print(f"  Evidence files tracked in db: {len(evidence_files)}")

    # Dry-run execution in an atomic transaction that rolls back
    print(f"\n[7] SIMULATING DELETION ORDER IN AN ATOMIC ROLLBACK TRANSACTION...")
    try:
        with transaction.atomic():
            # Step A: Reassign suppliers referencing disposable companies
            for sup in suppliers_to_reassign:
                sup.company = canonical_company
                sup.save(update_fields=["company"])

            # Step B: Delete transactional data in safe cascade order
            # 1. Procurement Items
            pi_deleted, _ = ProcurementItem.objects.all().delete()
            # 2. Calculation Results
            cr_deleted, _ = CalculationResult.objects.all().delete()
            # 3. Anomaly Records & Runs
            ar_deleted, _ = AnomalyRecord.objects.all().delete()
            adr_deleted, _ = AnomalyDetectionRun.objects.all().delete()
            # 4. Correction Requests & Submission Reviews
            crq_deleted, _ = CorrectionRequest.objects.all().delete()
            sr_deleted, _ = SubmissionReview.objects.all().delete()
            # 5. Activity Revisions
            rev_deleted, _ = ActivityRevision.objects.all().delete()
            # 6. Submissions
            sub_deleted, _ = Submission.objects.all().delete()
            # 7. OCR Fields & OCR Runs
            ocrf_deleted, _ = OCRField.objects.all().delete()
            ocrr_deleted, _ = OCRRun.objects.all().delete()
            # 8. Evidence
            evi_deleted, _ = Evidence.objects.all().delete()
            # 9. Validation Results & Runs
            vr_deleted, _ = ValidationResult.objects.all().delete()
            vrun_deleted, _ = ValidationRun.objects.all().delete()
            # 10. Procurement Records
            pr_deleted, _ = ProcurementRecord.objects.all().delete()
            # 11. Activity Records
            act_deleted, _ = ActivityRecord.objects.all().delete()

            print(f"    Transaction data deleted successfully in atomic block:")
            print(f"      ProcurementItem: {pi_deleted}, CalculationResult: {cr_deleted}")
            print(f"      AnomalyRecord: {ar_deleted}, AnomalyDetectionRun: {adr_deleted}")
            print(f"      CorrectionRequest: {crq_deleted}, SubmissionReview: {sr_deleted}")
            print(f"      ActivityRevision: {rev_deleted}, Submission: {sub_deleted}")
            print(f"      OCRField: {ocrf_deleted}, OCRRun: {ocrr_deleted}, Evidence: {evi_deleted}")
            print(f"      ValidationResult: {vr_deleted}, ValidationRun: {vrun_deleted}")
            print(f"      ProcurementRecord: {pr_deleted}, ActivityRecord: {act_deleted}")

            # Step C: Delete disposable reporting periods
            dp_deleted, _ = disposable_periods.delete()
            print(f"      Disposable ReportingPeriods deleted: {dp_deleted}")

            # Step D: Delete assignments pointing to disposable entities
            sa_deleted, _ = SiteAssignment.objects.filter(site__in=disposable_sites).delete()
            suba_deleted, _ = SubsidiaryAssignment.objects.filter(subsidiary__in=disposable_subsidiaries).delete()
            ca_deleted, _ = CompanyAssignment.objects.filter(company__in=disposable_companies).delete()
            print(f"      Disposable Assignments deleted: SiteAssignments={sa_deleted}, SubAssignments={suba_deleted}, CoAssignments={ca_deleted}")

            # Step E: Delete disposable sites
            dst_deleted, _ = disposable_sites.delete()
            print(f"      Disposable Sites deleted: {dst_deleted}")

            # Step F: Delete disposable projects
            dpj_deleted, _ = disposable_projects.delete()
            print(f"      Disposable Projects deleted: {dpj_deleted}")

            # Step G: Delete disposable subsidiaries
            dsub_deleted, _ = disposable_subsidiaries.delete()
            print(f"      Disposable Subsidiaries deleted: {dsub_deleted}")

            # Step H: Delete disposable companies
            dco_deleted, _ = disposable_companies.delete()
            print(f"      Disposable Companies deleted: {dco_deleted}")

            # Verify remaining state inside transaction
            assert Company.objects.count() == 1, f"Company count is {Company.objects.count()}"
            assert Subsidiary.objects.count() == 2, f"Subsidiary count is {Subsidiary.objects.count()}"
            assert Project.objects.count() == 2, f"Project count is {Project.objects.count()}"
            assert ActivityMaster.objects.count() == 18, f"ActivityMaster count is {ActivityMaster.objects.count()}"
            assert UnitOfMeasure.objects.count() == 17, f"UnitOfMeasure count is {UnitOfMeasure.objects.count()}"
            assert ActivityCategory.objects.count() == 13, f"ActivityCategory count is {ActivityCategory.objects.count()}"
            assert ValidationRule.objects.count() == 22, f"ValidationRule count is {ValidationRule.objects.count()}"
            assert AnomalyRule.objects.count() == 8, f"AnomalyRule count is {AnomalyRule.objects.count()}"
            assert EmissionFactor.objects.count() == 10, f"EmissionFactor count is {EmissionFactor.objects.count()}"
            assert Scope3Category.objects.count() == 15, f"Scope3Category count is {Scope3Category.objects.count()}"
            assert Supplier.objects.count() == 13, f"Supplier count is {Supplier.objects.count()}"
            assert AuthAuditLog.objects.count() == 1278, f"AuthAuditLog count is {AuthAuditLog.objects.count()}"

            print("\n    ALL ASSERTIONS PASSED! Hierarchy, master data, and audit trail verified in transaction.")
            # Trigger rollback to ensure dry run is strictly non-destructive
            raise RuntimeError("INTENTIONAL_DRY_RUN_ROLLBACK")

    except RuntimeError as ex:
        if str(ex) == "INTENTIONAL_DRY_RUN_ROLLBACK":
            print(f"\n[8] DRY-RUN COMPLETED AND ROLLED BACK CLEANLY (ZERO DESTRUCTIVE CHANGES)")
        else:
            raise

    print("=" * 80)

if __name__ == "__main__":
    simulate_dry_run()
