"""
Controlled Database Cleanup & Workflow Reset Management Command.
MEIL ESG CONTROL TOWER.

Performs a controlled reset of disposable transaction and submission data only.
Preserves:
- All Django models, migrations, and database schema.
- Activity master definitions, categories, and units of measurement.
- Validation rules, methods, and anomaly rules.
- Emission factor records and scope classification logic.
- Calculation formulas, unit conversion methods, and calculation engine.
- Roles, users, permissions, and legitimate assignments.
- Complete audit trail in AuthAuditLog.
- Exactly 1 canonical MEIL company, 2 subsidiaries, and 2 projects.
"""

import os
import shutil
from pathlib import Path
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Count

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


class Command(BaseCommand):
    help = (
        "Perform a controlled database cleanup of dummy/test transactions "
        "and enforce the canonical MEIL 1-Company / 2-Subsidiary / 2-Project hierarchy."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Execute the cleanup. Without this flag, only a dry run is executed.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate the cleanup in an atomic rollback transaction without committing changes.",
        )

    def handle(self, *args, **options):
        execute_mode = options.get("execute", False)
        dry_run_mode = options.get("dry_run", False) or not execute_mode

        mode_str = "EXECUTE (DESTRUCTIVE TRANSACTIONS ONLY)" if execute_mode else "DRY-RUN (SIMULATION ONLY - NO CHANGES)"
        self.stdout.write(self.style.NOTICE("=" * 80))
        self.stdout.write(self.style.NOTICE(f"CONTROLLED DATABASE CLEANUP & WORKFLOW RESET"))
        self.stdout.write(self.style.NOTICE(f"Mode: {mode_str}"))
        self.stdout.write(self.style.NOTICE("=" * 80))

        # 1. Environment Safety Check
        db_engine = connection.settings_dict.get("ENGINE", "")
        db_name = str(connection.settings_dict.get("NAME", ""))
        self.stdout.write(f"\n[1] Environment Safety Check:")
        self.stdout.write(f"    Database Engine: {db_engine}")
        self.stdout.write(f"    Database Name  : {db_name}")

        if "sqlite3" not in db_engine.lower() and "postgres" not in db_engine.lower():
            raise CommandError(f"Unexpected database engine: {db_engine}. Aborting cleanup for safety.")

        # 2. Backup Verification
        base_dir = Path(settings.BASE_DIR)
        backup_dir = base_dir / "backups"
        canonical_backup = backup_dir / "db_backup_pre_cleanup.sqlite3"

        if execute_mode:
            if not canonical_backup.exists():
                self.stdout.write(self.style.WARNING("    Canonical backup not found. Creating backup before proceeding..."))
                from scripts.create_verified_backup import create_and_verify_backup
                create_and_verify_backup()
            
            if not canonical_backup.exists() or canonical_backup.stat().st_size == 0:
                raise CommandError("Backup verification failed! Cannot proceed without verified backup.")
            self.stdout.write(self.style.SUCCESS(f"    Verified backup confirmed: {canonical_backup} ({canonical_backup.stat().st_size:,} bytes)"))

        # 3. Identify Canonical Targets
        try:
            canonical_company = Company.objects.get(code="MEIL-ENT")
        except Company.DoesNotExist:
            raise CommandError("Canonical MEIL company record ('MEIL-ENT') not found! Aborting.")

        canonical_subsidiaries = Subsidiary.objects.filter(
            company=canonical_company,
            code__in=["MEIL-HYDRO", "MEIL-SOLAR"]
        )
        if canonical_subsidiaries.count() != 2:
            raise CommandError(
                f"Expected exactly 2 canonical subsidiaries ('MEIL-HYDRO', 'MEIL-SOLAR'), "
                f"found {canonical_subsidiaries.count()}. Aborting."
            )

        canonical_projects = Project.objects.filter(
            subsidiary__in=canonical_subsidiaries,
            code__in=["PRJ-POL-01", "PRJ-KRN-01"]
        )
        if canonical_projects.count() != 2:
            raise CommandError(
                f"Expected exactly 2 canonical projects ('PRJ-POL-01', 'PRJ-KRN-01'), "
                f"found {canonical_projects.count()}. Aborting."
            )

        canonical_sites = Site.objects.filter(
            project__in=canonical_projects,
            code__in=["SITE-POL-101", "SITE-POL-102", "SITE-KRN-201"]
        )

        canonical_periods = ReportingPeriod.objects.filter(
            company=canonical_company,
            code__in=["FY2024-25", "FY2025-26", "FY2026-27"]
        )

        self.stdout.write(f"\n[2] Canonical Organization Target Structure:")
        self.stdout.write(f"    Company: {canonical_company.name} ({canonical_company.code})")
        for sub in canonical_subsidiaries:
            prj = canonical_projects.filter(subsidiary=sub).first()
            prj_code = prj.code if prj else "None"
            self.stdout.write(f"    |-- Subsidiary: {sub.name} ({sub.code}) -> Project: {prj.name if prj else 'None'} ({prj_code})")
        self.stdout.write(f"    Canonical Sites: {[st.code for st in canonical_sites]}")
        self.stdout.write(f"    Canonical Periods: {[rp.code for rp in canonical_periods]}")

        # 4. Snapshot Counts Before Cleanup
        before_counts = {
            # Protected Master / Config
            "Role": Role.objects.count(),
            "User": User.objects.count(),
            "UserRole": UserRole.objects.count(),
            "ActivityCategory": ActivityCategory.objects.count(),
            "UnitOfMeasure": UnitOfMeasure.objects.count(),
            "ActivityMaster": ActivityMaster.objects.count(),
            "ValidationRule": ValidationRule.objects.count(),
            "AnomalyRule": AnomalyRule.objects.count(),
            "Scope3Category": Scope3Category.objects.count(),
            "EmissionFactor": EmissionFactor.objects.count(),
            "Supplier": Supplier.objects.count(),
            "Carrier": Carrier.objects.count(),
            "Vehicle": Vehicle.objects.count(),
            "AuthAuditLog": AuthAuditLog.objects.count(),
            # Hierarchy
            "Company": Company.objects.count(),
            "Subsidiary": Subsidiary.objects.count(),
            "Project": Project.objects.count(),
            "Site": Site.objects.count(),
            "ReportingPeriod": ReportingPeriod.objects.count(),
            "CompanyAssignment": CompanyAssignment.objects.count(),
            "SubsidiaryAssignment": SubsidiaryAssignment.objects.count(),
            "SiteAssignment": SiteAssignment.objects.count(),
            # Disposable Transactions
            "ActivityRecord": ActivityRecord.objects.count(),
            "ActivityRevision": ActivityRevision.objects.count(),
            "Evidence": Evidence.objects.count(),
            "OCRRun": OCRRun.objects.count(),
            "OCRField": OCRField.objects.count(),
            "ValidationRun": ValidationRun.objects.count(),
            "ValidationResult": ValidationResult.objects.count(),
            "Submission": Submission.objects.count(),
            "SubmissionReview": SubmissionReview.objects.count(),
            "CorrectionRequest": CorrectionRequest.objects.count(),
            "AnomalyDetectionRun": AnomalyDetectionRun.objects.count(),
            "AnomalyRecord": AnomalyRecord.objects.count(),
            "ProcurementRecord": ProcurementRecord.objects.count(),
            "ProcurementItem": ProcurementItem.objects.count(),
            "TransportRecord": TransportRecord.objects.count(),
            "Shipment": Shipment.objects.count(),
            "CalculationResult": CalculationResult.objects.count(),
        }

        # 5. Determine Disposable Querysets
        disposable_companies = Company.objects.exclude(id=canonical_company.id)
        disposable_subsidiaries = Subsidiary.objects.exclude(id__in=canonical_subsidiaries.values_list("id", flat=True))
        disposable_projects = Project.objects.exclude(id__in=canonical_projects.values_list("id", flat=True))
        disposable_sites = Site.objects.exclude(id__in=canonical_sites.values_list("id", flat=True))
        disposable_periods = ReportingPeriod.objects.exclude(id__in=canonical_periods.values_list("id", flat=True))
        suppliers_to_reassign = Supplier.objects.filter(company__in=disposable_companies)

        deleted_summary = {}

        # 6. Execute or Simulate Cleanup
        def run_cleanup():
            # Step A: Reassign Suppliers referencing disposable companies to canonical company
            reassigned_count = 0
            for sup in suppliers_to_reassign:
                sup.company = canonical_company
                sup.save(update_fields=["company"])
                reassigned_count += 1
            deleted_summary["SuppliersReassigned"] = reassigned_count

            # Step B: Delete Transaction & Workflow Records in Strict Cascade Order
            deleted_summary["ProcurementItem"], _ = ProcurementItem.objects.all().delete()
            deleted_summary["CalculationResult"], _ = CalculationResult.objects.all().delete()
            deleted_summary["AnomalyRecord"], _ = AnomalyRecord.objects.all().delete()
            deleted_summary["AnomalyDetectionRun"], _ = AnomalyDetectionRun.objects.all().delete()
            deleted_summary["CorrectionRequest"], _ = CorrectionRequest.objects.all().delete()
            deleted_summary["SubmissionReview"], _ = SubmissionReview.objects.all().delete()
            deleted_summary["ActivityRevision"], _ = ActivityRevision.objects.all().delete()
            deleted_summary["Submission"], _ = Submission.objects.all().delete()
            deleted_summary["OCRField"], _ = OCRField.objects.all().delete()
            deleted_summary["OCRRun"], _ = OCRRun.objects.all().delete()
            deleted_summary["Evidence"], _ = Evidence.objects.all().delete()
            deleted_summary["ValidationResult"], _ = ValidationResult.objects.all().delete()
            deleted_summary["ValidationRun"], _ = ValidationRun.objects.all().delete()
            deleted_summary["ProcurementRecord"], _ = ProcurementRecord.objects.all().delete()
            deleted_summary["TransportRecord"], _ = TransportRecord.objects.all().delete()
            deleted_summary["Shipment"], _ = Shipment.objects.all().delete()
            deleted_summary["ActivityRecord"], _ = ActivityRecord.objects.all().delete()

            # Step C: Delete Disposable Reporting Periods
            deleted_summary["ReportingPeriod"], _ = disposable_periods.delete()

            # Step D: Delete Assignments referencing disposable entities
            deleted_summary["SiteAssignment"], _ = SiteAssignment.objects.filter(site__in=disposable_sites).delete()
            deleted_summary["SubsidiaryAssignment"], _ = SubsidiaryAssignment.objects.filter(subsidiary__in=disposable_subsidiaries).delete()
            deleted_summary["CompanyAssignment"], _ = CompanyAssignment.objects.filter(company__in=disposable_companies).delete()

            # Step E: Delete Disposable Hierarchy Entities
            deleted_summary["Site"], _ = disposable_sites.delete()
            deleted_summary["Project"], _ = disposable_projects.delete()
            deleted_summary["Subsidiary"], _ = disposable_subsidiaries.delete()
            deleted_summary["Company"], _ = disposable_companies.delete()

            # Step F: Integrity Assertions
            if Company.objects.count() != 1:
                raise CommandError(f"Assertion failed: Company count is {Company.objects.count()}, expected 1.")
            if Subsidiary.objects.count() != 2:
                raise CommandError(f"Assertion failed: Subsidiary count is {Subsidiary.objects.count()}, expected 2.")
            if Project.objects.count() != 2:
                raise CommandError(f"Assertion failed: Project count is {Project.objects.count()}, expected 2.")
            if Site.objects.count() != 3:
                raise CommandError(f"Assertion failed: Site count is {Site.objects.count()}, expected 3.")
            if ReportingPeriod.objects.count() != 3:
                raise CommandError(f"Assertion failed: ReportingPeriod count is {ReportingPeriod.objects.count()}, expected 3.")
            if ActivityRecord.objects.count() != 0:
                raise CommandError(f"Assertion failed: ActivityRecord count is {ActivityRecord.objects.count()}, expected 0.")
            if Submission.objects.count() != 0:
                raise CommandError(f"Assertion failed: Submission count is {Submission.objects.count()}, expected 0.")
            if CalculationResult.objects.count() != 0:
                raise CommandError(f"Assertion failed: CalculationResult count is {CalculationResult.objects.count()}, expected 0.")

            # Master Data Integrity Assertions
            if ActivityMaster.objects.count() != before_counts["ActivityMaster"]:
                raise CommandError("ActivityMaster records were accidentally altered!")
            if UnitOfMeasure.objects.count() != before_counts["UnitOfMeasure"]:
                raise CommandError("UnitOfMeasure records were accidentally altered!")
            if ActivityCategory.objects.count() != before_counts["ActivityCategory"]:
                raise CommandError("ActivityCategory records were accidentally altered!")
            if ValidationRule.objects.count() != before_counts["ValidationRule"]:
                raise CommandError("ValidationRule records were accidentally altered!")
            if AnomalyRule.objects.count() != before_counts["AnomalyRule"]:
                raise CommandError("AnomalyRule records were accidentally altered!")
            if EmissionFactor.objects.count() != before_counts["EmissionFactor"]:
                raise CommandError("EmissionFactor records were accidentally altered!")
            if Scope3Category.objects.count() != before_counts["Scope3Category"]:
                raise CommandError("Scope3Category records were accidentally altered!")
            if Supplier.objects.count() != before_counts["Supplier"]:
                raise CommandError("Supplier records were accidentally altered!")
            if AuthAuditLog.objects.count() != before_counts["AuthAuditLog"]:
                raise CommandError("AuthAuditLog records were accidentally altered!")
            if User.objects.count() != before_counts["User"]:
                raise CommandError("User records were accidentally altered!")

        if dry_run_mode:
            self.stdout.write(self.style.NOTICE("\n[3] Executing Dry-Run Simulation (Atomic Rollback)..."))
            try:
                with transaction.atomic():
                    run_cleanup()
                    raise RuntimeError("INTENTIONAL_DRY_RUN_ROLLBACK")
            except RuntimeError as err:
                if str(err) == "INTENTIONAL_DRY_RUN_ROLLBACK":
                    self.stdout.write(self.style.SUCCESS("    Dry-run simulation succeeded with 100% integrity validation!"))
                    self.stdout.write(self.style.SUCCESS("    Zero destructive changes committed to database."))
                else:
                    raise
        else:
            self.stdout.write(self.style.WARNING("\n[3] Executing Database Cleanup Transaction (COMMIT)..."))
            with transaction.atomic():
                run_cleanup()
            self.stdout.write(self.style.SUCCESS("    Cleanup transaction committed successfully!"))

            # Step G: Clean up orphaned test evidence files on disk
            media_evidence_dir = base_dir / "media" / "evidence"
            if media_evidence_dir.exists():
                self.stdout.write(f"\n[4] Cleaning up orphaned test media files in {media_evidence_dir}...")
                cleaned_dirs = 0
                for item in media_evidence_dir.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                        cleaned_dirs += 1
                self.stdout.write(self.style.SUCCESS(f"    Removed {cleaned_dirs} orphaned evidence storage subdirectories."))

        # 7. Post-Cleanup Snapshot
        after_counts = {
            "Role": Role.objects.count(),
            "User": User.objects.count(),
            "UserRole": UserRole.objects.count(),
            "ActivityCategory": ActivityCategory.objects.count(),
            "UnitOfMeasure": UnitOfMeasure.objects.count(),
            "ActivityMaster": ActivityMaster.objects.count(),
            "ValidationRule": ValidationRule.objects.count(),
            "AnomalyRule": AnomalyRule.objects.count(),
            "Scope3Category": Scope3Category.objects.count(),
            "EmissionFactor": EmissionFactor.objects.count(),
            "Supplier": Supplier.objects.count(),
            "Carrier": Carrier.objects.count(),
            "Vehicle": Vehicle.objects.count(),
            "AuthAuditLog": AuthAuditLog.objects.count(),
            "Company": Company.objects.count(),
            "Subsidiary": Subsidiary.objects.count(),
            "Project": Project.objects.count(),
            "Site": Site.objects.count(),
            "ReportingPeriod": ReportingPeriod.objects.count(),
            "CompanyAssignment": CompanyAssignment.objects.count(),
            "SubsidiaryAssignment": SubsidiaryAssignment.objects.count(),
            "SiteAssignment": SiteAssignment.objects.count(),
            "ActivityRecord": ActivityRecord.objects.count(),
            "ActivityRevision": ActivityRevision.objects.count(),
            "Evidence": Evidence.objects.count(),
            "OCRRun": OCRRun.objects.count(),
            "OCRField": OCRField.objects.count(),
            "ValidationRun": ValidationRun.objects.count(),
            "ValidationResult": ValidationResult.objects.count(),
            "Submission": Submission.objects.count(),
            "SubmissionReview": SubmissionReview.objects.count(),
            "CorrectionRequest": CorrectionRequest.objects.count(),
            "AnomalyDetectionRun": AnomalyDetectionRun.objects.count(),
            "AnomalyRecord": AnomalyRecord.objects.count(),
            "ProcurementRecord": ProcurementRecord.objects.count(),
            "ProcurementItem": ProcurementItem.objects.count(),
            "TransportRecord": TransportRecord.objects.count(),
            "Shipment": Shipment.objects.count(),
            "CalculationResult": CalculationResult.objects.count(),
        }

        # 8. Print Before / After Summary Table
        self.stdout.write(f"\n" + "=" * 80)
        del_header = "WOULD DELETE" if dry_run_mode else "DELETED"
        aft_header = "PROJ AFTER" if dry_run_mode else "AFTER"
        self.stdout.write(f"{'TABLE / MODEL':<25} | {'BEFORE':<8} | {del_header:<12} | {aft_header:<10} | {'STATUS':<15}")
        self.stdout.write("-" * 80)

        for model_name in before_counts:
            b_cnt = before_counts[model_name]
            if dry_run_mode:
                d_cnt = deleted_summary.get(model_name, 0)
                a_cnt = b_cnt - d_cnt
            else:
                a_cnt = after_counts[model_name]
                d_cnt = b_cnt - a_cnt

            if b_cnt == a_cnt:
                status_str = "PRESERVED"
            elif a_cnt == 0:
                status_str = "RESET (CLEAN)"
            else:
                status_str = "CONSOLIDATED"
            self.stdout.write(f"{model_name:<25} | {b_cnt:<8} | {d_cnt:<12} | {a_cnt:<10} | {status_str:<15}")

        self.stdout.write("=" * 80)
        self.stdout.write(self.style.SUCCESS(f"\nCleanup {'simulation' if dry_run_mode else 'execution'} finished successfully."))
