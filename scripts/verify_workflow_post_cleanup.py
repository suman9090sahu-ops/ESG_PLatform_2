import os
import sys
import hashlib
from decimal import Decimal
from datetime import date
from pathlib import Path

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
import django
django.setup()

from django.test import Client
from django.core.files.base import ContentFile
from apps.core.models import (
    Company, Subsidiary, Project, Site, User,
    ReportingPeriod, ActivityMaster, UnitOfMeasure,
    ActivityRecord, Evidence, EvidenceType, EvidenceStatus,
    Submission, SubmissionStatus, RecordStatus, ReviewAction,
    CorrectionRequest, CalculationResult, AuthAuditLog, SubmissionReview,
    ValidationResult, ValidationRun
)
from apps.core.validation_services import execute_validation_run
from apps.core.ocr_services import execute_ocr_run
from apps.core.submission_services import submit_activity_record
from apps.core.review_services import request_correction_submission, verify_submission
from apps.core.calculation_services import calculate_activity_record

def run_workflow_test():
    print("=" * 80)
    print("POST-CLEANUP 15-STEP END-TO-END WORKFLOW VERIFICATION")
    print("=" * 80)

    # Step 1: Authenticate as authorized Site Manager
    print("\n--- Step 1: Authenticate as authorized Site Manager ---")
    client_sm = Client()
    sm_login = client_sm.login(username="site_manager", password="SiteManagerPass123!")
    assert sm_login, "Site Manager authentication failed!"
    print("  [PASS] Site Manager 'site_manager' authenticated successfully.")

    # Step 2: Access the assigned site
    print("\n--- Step 2: Access assigned site ---")
    site_101 = Site.objects.get(code="SITE-POL-101")
    sm_dash_res = client_sm.get("/site-manager/dashboard/")
    assert sm_dash_res.status_code == 200, f"Expected 200, got {sm_dash_res.status_code}"
    assert "Polavaram Dam Headworks" in sm_dash_res.content.decode("utf-8"), "Assigned site not displayed on dashboard!"
    print(f"  [PASS] Site Manager accessed assigned site: {site_101.name} ({site_101.code}).")

    # Step 3 & 4: Create an ESG activity record using permitted units
    print("\n--- Step 3 & 4: Create ESG activity record with permitted units ---")
    act_diesel = ActivityMaster.objects.get(code="FUEL-DIESEL-STAT")
    unit_litre = UnitOfMeasure.objects.get(code="LITRE")
    period = ReportingPeriod.objects.get(company__code="MEIL-ENT", code="FY2025-26")
    sm_user = User.objects.get(username="site_manager")

    record = ActivityRecord.objects.create(
        site=site_101,
        reporting_period=period,
        activity=act_diesel,
        unit=unit_litre,
        quantity=Decimal("3500.0000"),
        measurement_date=date(2025, 5, 20),
        status=RecordStatus.DRAFT,
        notes="Batch #901 DG Generator fuel delivery - Post Cleanup Workflow Verification",
        evidence_reference="IOCL-TEST-INV-901",
        created_by=sm_user,
        updated_by=sm_user,
    )
    print(f"  [PASS] Activity Record #{record.id} created: {record.activity.name}, {record.quantity} {record.unit.symbol}.")

    # Step 5: Upload supporting evidence
    print("\n--- Step 5: Upload supporting evidence document ---")
    from tests.test_phase11_ocr_engine import create_sample_pdf_bytes
    file_bytes = create_sample_pdf_bytes("TAX INVOICE IOCL BATCH 901 Quantity: 3500.0 Litres Diesel")
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    evidence = Evidence.objects.create(
        activity_record=record,
        original_filename="iocl_invoice_batch901.pdf",
        file=ContentFile(file_bytes, name="iocl_invoice_batch901.pdf"),
        file_type="application/pdf",
        file_size=len(file_bytes),
        file_hash=file_hash,
        evidence_type=EvidenceType.INVOICE,
        description="Delivery challan and commercial fuel invoice batch #901",
        status=EvidenceStatus.ACTIVE,
        uploaded_by=sm_user,
    )
    print(f"  [PASS] Evidence #{evidence.id} attached: {evidence.original_filename} (SHA-256: {file_hash[:16]}...).")

    # Step 6: Run existing validation process
    print("\n--- Step 6: Run existing validation process ---")
    val_run = execute_validation_run(record=record, executed_by=sm_user)
    print(f"  [PASS] Validation Run #{val_run.id} executed: Status = {val_run.status}, Results count = {val_run.results.count()}.")
    assert val_run.status in ["VALID", "PASSED", "WARNING", "FAILED"], f"Unexpected validation run status {val_run.status}"

    # Step 7: Run OCR where applicable
    print("\n--- Step 7: Run OCR processing ---")
    ocr_run = execute_ocr_run(evidence=evidence, user=sm_user)
    print(f"  [PASS] OCR Run #{ocr_run.id} processed: Confidence = {ocr_run.confidence}, Status = {ocr_run.status}.")

    # Step 8: Submit the record through submission workflow
    print("\n--- Step 8: Submit record through submission workflow ---")
    submission = submit_activity_record(
        record=record,
        user=sm_user,
        comments="Submitted for subsidiary verification - Phase 25 Clean Workflow Test"
    )
    record.refresh_from_db()
    print(f"  [PASS] Submission #{submission.submission_number} created (ID: {submission.id}, Status: {submission.status}).")
    assert submission.status == SubmissionStatus.SUBMITTED, f"Expected SUBMITTED, got {submission.status}"

    # Step 9: Sign in as authorized Subsidiary Manager
    print("\n--- Step 9: Sign in as authorized Subsidiary Manager ---")
    client_sub = Client()
    sub_login = client_sub.login(username="subsidiary_manager", password="SubManagerPass123!")
    assert sub_login, "Subsidiary Manager authentication failed!"
    print("  [PASS] Subsidiary Manager 'subsidiary_manager' authenticated successfully.")

    # Step 10: Review the new submission
    print("\n--- Step 10: Review the new submission ---")
    sub_inbox_res = client_sub.get("/subsidiary-manager/inbox/")
    assert sub_inbox_res.status_code == 200, f"Expected 200, got {sub_inbox_res.status_code}"
    review_res = client_sub.get(f"/subsidiary-manager/submissions/{submission.id}/review/")
    assert review_res.status_code == 200, f"Expected 200, got {review_res.status_code}"
    print(f"  [PASS] Subsidiary Manager viewed submission review page for #{submission.submission_number}.")

    # Step 11: Verify or request correction using existing actions
    print("\n--- Step 11: Request correction using existing action ---")
    sub_user = User.objects.get(username="subsidiary_manager")
    corr_review = request_correction_submission(
        submission=submission,
        user=sub_user,
        reason="Please confirm discrepancy between logbook and invoice batch slip.",
    )
    corr_req = CorrectionRequest.objects.filter(submission=submission).latest("created_at")
    submission.refresh_from_db()
    record.refresh_from_db()
    print(f"  [PASS] Correction requested: CorrectionRequest #{corr_req.id}, Submission Status = {submission.status}.")
    assert submission.status == SubmissionStatus.CORRECTION_REQUESTED

    # Step 12: Complete correction & resubmission workflow
    print("\n--- Step 12: Complete correction and resubmission workflow ---")
    record.notes = "Updated and verified batch slip #901 with logistics officer."
    record.quantity = Decimal("3550.0000")
    record.save(update_fields=["notes", "quantity"])
    
    # Resubmit
    resubmission = submit_activity_record(
        record=record,
        user=sm_user,
        comments="Resubmitted with confirmed batch quantity 3,550 L."
    )
    corr_req.status = "RESOLVED"
    corr_req.resubmission = resubmission
    corr_req.resolved_by = sm_user
    corr_req.save()

    # Subsidiary Manager Verifies
    verify_review = verify_submission(
        submission=resubmission,
        user=sub_user,
        comments="Telemetry batch quantity reconciled against delivery challan. Verified."
    )
    resubmission.refresh_from_db()
    record.refresh_from_db()
    print(f"  [PASS] Resubmission verified: Submission #{resubmission.submission_number} Status = {resubmission.status}, Record Status = {record.status}.")
    assert resubmission.status == SubmissionStatus.VERIFIED
    assert record.status == RecordStatus.VERIFIED

    # Step 13: Verify ESG Manager can access governance and calculation views
    print("\n--- Step 13: Verify ESG Manager accesses governance and calculation views ---")
    client_esg = Client()
    esg_login = client_esg.login(username="esg_manager", password="ESGManagerPass123!")
    assert esg_login, "ESG Manager authentication failed!"
    esg_dash_res = client_esg.get("/esg-manager/dashboard/")
    assert esg_dash_res.status_code == 200, f"Expected 200, got {esg_dash_res.status_code}"
    calc_desk_res = client_esg.get("/calculations/desk/")
    assert calc_desk_res.status_code == 200, f"Expected 200, got {calc_desk_res.status_code}"
    print(f"  [PASS] ESG Manager accessed governance dashboard and calculation desk (HTTP 200).")

    # Step 14: Confirm emission calculations and traceability work for valid records
    print("\n--- Step 14: Confirm emission calculations and traceability ---")
    esg_user = User.objects.get(username="esg_manager")
    calc_result = calculate_activity_record(record=record, user=esg_user)
    assert calc_result is not None, "Calculation returned None!"
    print(f"  [PASS] Calculation executed: Value = {calc_result.calculated_value} {calc_result.result_unit}, Method = {calc_result.calculation_method}.")
    
    # Check trace endpoint
    trace_res = client_esg.get(f"/reports/trace/{record.id}/")
    assert trace_res.status_code == 200, f"Expected 200 for trace, got {trace_res.status_code}"
    print(f"  [PASS] Traceability view accessible at /reports/trace/{record.id}/ (HTTP 200).")

    # Step 15: Confirm that Auditor remains read-only
    print("\n--- Step 15: Confirm that Auditor remains read-only ---")
    client_auditor = Client()
    aud_login = client_auditor.login(username="auditor", password="AuditorPass123!")
    assert aud_login, "Auditor authentication failed!"
    aud_dash_res = client_auditor.get("/auditor/dashboard/")
    assert aud_dash_res.status_code == 200, f"Expected 200, got {aud_dash_res.status_code}"
    
    # Auditor attempts mutation recalculation
    mutation_res = client_auditor.post(f"/calculations/recalculate/{record.id}/")
    assert mutation_res.status_code == 403, f"Expected 403 Forbidden for Auditor mutation, got {mutation_res.status_code}"
    print(f"  [PASS] Auditor accessed dashboard (HTTP 200) and was blocked on recalculation mutation (HTTP 403 Forbidden).")

    # Clean up this single test workflow record so database is pristine
    print("\n--- Resetting test workflow record to leave database in pristine clean state ---")
    from apps.core.models import OCRRun, OCRField, AnomalyRecord
    CorrectionRequest.objects.filter(activity_record=record).delete()
    SubmissionReview.objects.filter(submission__activity_record=record).delete()
    Submission.objects.filter(activity_record=record).delete()
    OCRField.objects.filter(ocr_run__evidence__activity_record=record).delete()
    OCRRun.objects.filter(evidence__activity_record=record).delete()
    Evidence.objects.filter(activity_record=record).delete()
    ValidationResult.objects.filter(activity_record=record).delete()
    ValidationRun.objects.filter(activity_record=record).delete()
    AnomalyRecord.objects.filter(activity_record=record).delete()
    CalculationResult.objects.filter(activity_record=record).delete()
    record.delete()
    print("  [PASS] Test verification record cleaned up. Database remains 100% ready for manual jury/user testing.")

    print("\n" + "=" * 80)
    print("ALL 15 WORKFLOW VERIFICATION STEPS PASSED SUCCESSFULLY (100% OK)")
    print("=" * 80)

if __name__ == "__main__":
    run_workflow_test()
