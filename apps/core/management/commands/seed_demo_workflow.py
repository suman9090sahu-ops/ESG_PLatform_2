"""
Management command to seed complete end-to-end demo workflow data for the ESG Platform.
Provides deterministic, database-backed records across all workflow lifecycle states:
1. Verified Scope 1 Diesel record (Auditable & Traceable with Evidence & SHA-256)
2. Verified Scope 2 Grid Electricity record (Auditable & Traceable)
3. Verified Captive Solar record (Auditable & Traceable)
4. Submitted Water record (Awaiting Subsidiary Manager Review in Inbox)
5. Correction-Requested Diesel record (Awaiting Site Manager Revision in Correction Inbox)
6. Draft Petrol record (Ready for live Site Manager submission demonstration)
"""

import hashlib
from datetime import date
from decimal import Decimal
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import models, transaction
from django.utils import timezone

from apps.core.models import (
    ActivityMaster,
    ActivityRecord,
    Company,
    Evidence,
    EvidenceStatus,
    EvidenceType,
    PeriodStatus,
    RecordStatus,
    ReportingPeriod,
    ReviewAction,
    Role,
    Site,
    Submission,
    SubmissionReview,
    SubmissionStatus,
    UnitOfMeasure,
    User,
    ValidationStatus,
)
from apps.core.review_services import request_correction_submission, verify_submission
from apps.core.submission_services import submit_activity_record
from apps.core.validation_services import execute_validation_run, seed_standard_validation_rules


class Command(BaseCommand):
    help = "Seed deterministic end-to-end ESG demo workflow records for jury presentation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Clear and re-seed Phase 21 demo workflow records.",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Initializing Phase 21 Demo Workflow Seeder..."))

        # 1. Ensure Base RBAC & Hierarchy Exist
        if not User.objects.filter(username="site_manager").exists():
            self.stdout.write("Running seed_rbac_data to establish base hierarchy and users...")
            call_command("seed_rbac_data")

        # 2. Ensure Standard Validation Rules Exist
        admin_user = User.objects.filter(username="admin").first()
        rules_count = seed_standard_validation_rules(user=admin_user)
        self.stdout.write(f"Validation rules ensured ({rules_count} newly seeded).")

        # 3. Retrieve Entities
        site_manager = User.objects.get(username="site_manager")
        subsidiary_manager = User.objects.get(username="subsidiary_manager")
        esg_manager = User.objects.get(username="esg_manager")
        auditor = User.objects.get(username="auditor")

        site = Site.objects.filter(code="SITE-POL-101").first()
        if not site:
            self.stderr.write("Site SITE-POL-101 not found. Please run seed_rbac_data first.")
            return

        period = ReportingPeriod.objects.filter(code="FY2025-26").first()
        if not period:
            company = Company.objects.first()
            period = ReportingPeriod.objects.create(
                company=company,
                code="FY2025-26",
                name="FY 2025-26 Operational Annual ESG Reporting Cycle",
                fiscal_year="FY 2025-26",
                start_date="2025-04-01",
                end_date="2026-03-31",
                status=PeriodStatus.OPEN,
            )

        demo_refs = [
            "IOCL-INV-2025-05-901",
            "APCPDCL-HT-MAY2025",
            "SOLAR-SCADA-MAY2025",
            "BOREWELL-METER-LOG-JUN2025",
            "FUEL-SLIP-JUN2025",
            "PETROL-LOG-JUN2025",
        ]
        demo_notes = [
            "Stationary DG Generator batching plant fuel delivery — Polavaram Headworks Block A",
            "HT Grid Electricity sub-station metering — Andhra Pradesh Discom Utility Supply",
            "Captive Rooftop Solar PV Generation — Auxiliary Operations Camp",
            "Groundwater extraction for camp potable supply and dust suppression",
            "Auxiliary pump diesel fuel — Spillway excavation zone",
            "Site supervision utility vehicle fleet petrol consumption",
        ]

        if options.get("reset"):
            self.stdout.write(self.style.WARNING("Reset flag provided: Purging existing demo records..."))
            target_records = ActivityRecord.objects.filter(
                models.Q(notes__in=demo_notes) | models.Q(evidence_reference__in=demo_refs)
            )
            sub_count, _ = Submission.objects.filter(activity_record__in=target_records).delete()
            evi_count, _ = Evidence.objects.filter(activity_record__in=target_records).delete()
            deleted_count, _ = target_records.delete()
            self.stdout.write(self.style.SUCCESS(f"Purged {deleted_count} demo records ({sub_count} submissions, {evi_count} evidence files)."))

        act_diesel = ActivityMaster.objects.get(code="FUEL-DIESEL-STAT")
        act_petrol = ActivityMaster.objects.get(code="FUEL-PETROL-MOB")
        act_grid = ActivityMaster.objects.get(code="ELEC-GRID")
        act_solar = ActivityMaster.objects.get(code="ELEC-RENEWABLE-CAPTIVE")
        act_water = ActivityMaster.objects.get(code="WATER-GROUND")

        unit_litre = UnitOfMeasure.objects.get(code="LITRE")
        unit_kwh = UnitOfMeasure.objects.get(code="KWH")
        unit_kl = UnitOfMeasure.objects.get(code="KL")

        # Helper to attach dummy evidence
        def attach_evidence(record, doc_name, doc_type, desc, ocr_data=None):
            content = f"ESG AUDIT EVIDENCE: {doc_name}\nSite: {record.site.code}\nRecord: {record.id}\nDate: {record.measurement_date}\n".encode("utf-8")
            file_hash = hashlib.sha256(content).hexdigest()
            ev, created = Evidence.objects.get_or_create(
                activity_record=record,
                original_filename=doc_name,
                defaults={
                    "evidence_type": doc_type,
                    "file": ContentFile(content, name=doc_name),
                    "file_type": "application/pdf",
                    "file_size": len(content),
                    "file_hash": file_hash,
                    "description": desc,
                    "status": EvidenceStatus.ACTIVE,
                    "uploaded_by": record.created_by,
                    "ocr_metadata": ocr_data or {
                        "status": "EXTRACTED",
                        "confidence_score": 0.98,
                        "extracted_quantity": float(record.quantity),
                        "extracted_unit": record.unit.symbol,
                        "extraction_method": "OCR_HYBRID_PARSER",
                    },
                },
            )
            return ev

        # ---------------------------------------------------------------------
        # RECORD 1: Scope 1 Diesel — VERIFIED (The Primary Demo Trace Target)
        # ---------------------------------------------------------------------
        rec1, created1 = ActivityRecord.objects.get_or_create(
            site=site,
            reporting_period=period,
            activity=act_diesel,
            measurement_date=date(2025, 5, 15),
            notes="Stationary DG Generator batching plant fuel delivery — Polavaram Headworks Block A",
            defaults={
                "quantity": Decimal("4500.0000"),
                "unit": unit_litre,
                "evidence_reference": "IOCL-INV-2025-05-901",
                "status": RecordStatus.DRAFT,
                "created_by": site_manager,
                "updated_by": site_manager,
            },
        )
        if created1 or rec1.status != RecordStatus.VERIFIED:
            attach_evidence(
                rec1,
                "IOCL_DIESEL_CHALLAN_MAY2025.pdf",
                EvidenceType.FUEL_CHALLAN,
                "Indian Oil Corporation delivery challan and batching plant DG log sheet.",
                ocr_data={"status": "EXTRACTED", "confidence_score": 0.985, "extracted_quantity": 4500.0, "extracted_unit": "L"},
            )
            execute_validation_run(rec1, executed_by=site_manager)
            sub1 = submit_activity_record(
                rec1,
                user=site_manager,
                comments="May 2025 diesel consumption for batching plant DG sets. All meter readings reconciled.",
            )
            verify_submission(
                sub1,
                user=subsidiary_manager,
                comments="Reconciled against IOCL challan #IOCL-2025-05-901 and DG logbook. All meter readings match. Approved for corporate GHG inventory.",
            )
            self.stdout.write(self.style.SUCCESS(f"  [1] Scope 1 Diesel Record #{rec1.id} seeded -> VERIFIED"))
        else:
            self.stdout.write(f"  [1] Scope 1 Diesel Record #{rec1.id} already VERIFIED")

        # ---------------------------------------------------------------------
        # RECORD 2: Scope 2 Grid Electricity — VERIFIED
        # ---------------------------------------------------------------------
        rec2, created2 = ActivityRecord.objects.get_or_create(
            site=site,
            reporting_period=period,
            activity=act_grid,
            measurement_date=date(2025, 5, 31),
            notes="HT Grid Electricity sub-station metering — Andhra Pradesh Discom Utility Supply",
            defaults={
                "quantity": Decimal("32500.0000"),
                "unit": unit_kwh,
                "evidence_reference": "APCPDCL-HT-MAY2025",
                "status": RecordStatus.DRAFT,
                "created_by": site_manager,
                "updated_by": site_manager,
            },
        )
        if created2 or rec2.status != RecordStatus.VERIFIED:
            attach_evidence(
                rec2,
                "AP_DISCOM_HT_BILL_MAY2025.pdf",
                EvidenceType.UTILITY_BILL,
                "APCPDCL HT Service Connection monthly bill for Polavaram Dam headworks camp.",
                ocr_data={"status": "EXTRACTED", "confidence_score": 0.992, "extracted_quantity": 32500.0, "extracted_unit": "kWh"},
            )
            execute_validation_run(rec2, executed_by=site_manager)
            sub2 = submit_activity_record(
                rec2,
                user=site_manager,
                comments="May 2025 utility HT electricity billing. Billed units verified against electronic meter.",
            )
            verify_submission(
                sub2,
                user=subsidiary_manager,
                comments="Verified against APCPDCL HT Service Connection bill #HT-4491-05. Approved for corporate Scope 2 inventory.",
            )
            self.stdout.write(self.style.SUCCESS(f"  [2] Scope 2 Grid Electricity Record #{rec2.id} seeded -> VERIFIED"))
        else:
            self.stdout.write(f"  [2] Scope 2 Grid Electricity Record #{rec2.id} already VERIFIED")

        # ---------------------------------------------------------------------
        # RECORD 3: Captive Solar Generation — VERIFIED
        # ---------------------------------------------------------------------
        rec3, created3 = ActivityRecord.objects.get_or_create(
            site=site,
            reporting_period=period,
            activity=act_solar,
            measurement_date=date(2025, 5, 20),
            notes="Captive Rooftop Solar PV Generation — Auxiliary Operations Camp",
            defaults={
                "quantity": Decimal("14200.0000"),
                "unit": unit_kwh,
                "evidence_reference": "SOLAR-SCADA-MAY2025",
                "status": RecordStatus.DRAFT,
                "created_by": site_manager,
                "updated_by": site_manager,
            },
        )
        if created3 or rec3.status != RecordStatus.VERIFIED:
            attach_evidence(
                rec3,
                "SOLAR_SCADA_LOG_MAY2025.pdf",
                EvidenceType.METER_READING,
                "Solar inverter SCADA monthly generation log.",
                ocr_data={"status": "EXTRACTED", "confidence_score": 0.975, "extracted_quantity": 14200.0, "extracted_unit": "kWh"},
            )
            execute_validation_run(rec3, executed_by=site_manager)
            sub3 = submit_activity_record(
                rec3,
                user=site_manager,
                comments="Captive solar PV export reading from inverter SCADA.",
            )
            verify_submission(
                sub3,
                user=subsidiary_manager,
                comments="Solar generation export logs verified against SCADA readings.",
            )
            self.stdout.write(self.style.SUCCESS(f"  [3] Captive Solar Record #{rec3.id} seeded -> VERIFIED"))
        else:
            self.stdout.write(f"  [3] Captive Solar Record #{rec3.id} already VERIFIED")

        # ---------------------------------------------------------------------
        # RECORD 4: Groundwater Extraction — SUBMITTED (In Subsidiary Review Inbox)
        # ---------------------------------------------------------------------
        rec4, created4 = ActivityRecord.objects.get_or_create(
            site=site,
            reporting_period=period,
            activity=act_water,
            measurement_date=date(2025, 6, 10),
            notes="Groundwater extraction for camp potable supply and dust suppression",
            defaults={
                "quantity": Decimal("850.0000"),
                "unit": unit_kl,
                "evidence_reference": "BOREWELL-METER-LOG-JUN2025",
                "status": RecordStatus.DRAFT,
                "created_by": site_manager,
                "updated_by": site_manager,
            },
        )
        if created4 or rec4.status != RecordStatus.SUBMITTED:
            attach_evidence(
                rec4,
                "BOREWELL_METER_LOG_JUN2025.pdf",
                EvidenceType.METER_READING,
                "Electromagnetic flow meter calibration certificate and daily extraction log.",
                ocr_data={"status": "EXTRACTED", "confidence_score": 0.960, "extracted_quantity": 850.0, "extracted_unit": "kL"},
            )
            execute_validation_run(rec4, executed_by=site_manager)
            sub4 = submit_activity_record(
                rec4,
                user=site_manager,
                comments="June 2025 borewell extraction for camp drinking water and dust suppression.",
            )
            self.stdout.write(self.style.SUCCESS(f"  [4] Groundwater Record #{rec4.id} seeded -> SUBMITTED (Ready for Subsidiary Review demo)"))
        else:
            self.stdout.write(f"  [4] Groundwater Record #{rec4.id} already SUBMITTED")

        # ---------------------------------------------------------------------
        # RECORD 5: Correction Scenario — CORRECTION REQUESTED (In Site Manager Correction Inbox)
        # ---------------------------------------------------------------------
        rec5, created5 = ActivityRecord.objects.get_or_create(
            site=site,
            reporting_period=period,
            activity=act_diesel,
            measurement_date=date(2025, 6, 12),
            notes="Auxiliary pump diesel fuel — Spillway excavation zone",
            defaults={
                "quantity": Decimal("1200.0000"),
                "unit": unit_litre,
                "evidence_reference": "FUEL-SLIP-JUN2025",
                "status": RecordStatus.DRAFT,
                "created_by": site_manager,
                "updated_by": site_manager,
            },
        )
        if created5 or rec5.status != RecordStatus.REJECTED:
            attach_evidence(
                rec5,
                "DIESEL_SLIP_JUN2025.pdf",
                EvidenceType.FUEL_CHALLAN,
                "Delivery challan from local fuel bowser.",
                ocr_data={"status": "EXTRACTED", "confidence_score": 0.95, "extracted_quantity": 1200.0, "extracted_unit": "L"},
            )
            execute_validation_run(rec5, executed_by=site_manager)
            sub5 = submit_activity_record(
                rec5,
                user=site_manager,
                comments="Spillway excavation auxiliary dewatering pump diesel consumption.",
            )
            request_correction_submission(
                sub5,
                user=subsidiary_manager,
                reason="Delivery challan indicates 1,200 Litres, but storage tank dipstick log records 1,020 Litres received.",
                required_correction="Please reconcile discrepancy with site logistics officer and resubmit corrected quantity (expected ~1,020 L).",
                affected_area="ACTIVITY_DATA",
            )
            self.stdout.write(self.style.SUCCESS(f"  [5] Diesel Correction Record #{rec5.id} seeded -> CORRECTION_REQUESTED (Ready for Correction demo)"))
        else:
            self.stdout.write(f"  [5] Diesel Correction Record #{rec5.id} already in CORRECTION state")

        # ---------------------------------------------------------------------
        # RECORD 6: Draft Petrol Record — DRAFT (Ready for Fresh Entry / Submission demo)
        # ---------------------------------------------------------------------
        rec6, created6 = ActivityRecord.objects.get_or_create(
            site=site,
            reporting_period=period,
            activity=act_petrol,
            measurement_date=date(2025, 6, 25),
            notes="Site supervision utility vehicle fleet petrol consumption",
            defaults={
                "quantity": Decimal("350.0000"),
                "unit": unit_litre,
                "evidence_reference": "PETROL-LOG-JUN2025",
                "status": RecordStatus.DRAFT,
                "created_by": site_manager,
                "updated_by": site_manager,
            },
        )
        if created6:
            attach_evidence(
                rec6,
                "PETROL_CARD_RECEIPTS_JUN2025.pdf",
                EvidenceType.INVOICE,
                "Monthly petrol purchase corporate card log sheet.",
            )
            execute_validation_run(rec6, executed_by=site_manager)
            self.stdout.write(self.style.SUCCESS(f"  [6] Petrol Draft Record #{rec6.id} seeded -> DRAFT (Ready for Entry/Submit demo)"))
        else:
            self.stdout.write(f"  [6] Petrol Draft Record #{rec6.id} already exists (DRAFT)")

        self.stdout.write(self.style.SUCCESS("\nPhase 21 Demo Workflow Seeding Completed Successfully!"))
        self.stdout.write(self.style.NOTICE("Jury Demonstration Accounts:"))
        self.stdout.write("  Site Manager:        site_manager        / SiteManagerPass123!")
        self.stdout.write("  Subsidiary Manager:  subsidiary_manager  / SubManagerPass123!")
        self.stdout.write("  ESG Manager:         esg_manager         / ESGManagerPass123!")
        self.stdout.write("  Auditor:             auditor             / AuditorPass123!")
        self.stdout.write("  System Admin:        admin               / AdminPass123!\n")
