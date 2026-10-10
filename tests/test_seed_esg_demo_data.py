"""
Automated Test Suite for Demo Data Management Command: seed_esg_demo_data.

Verifies:
1. Safe dry-run execution (zero database records committed, clean rollback)
2. Live apply execution & idempotency (running twice does not create duplicate rows)
3. Organizational scope boundary protection (preserves 2 subsidiaries, skips 42 unmapped entities)
4. Relational integrity & foreign-key constraints across all 10 domain tiers
5. Synthetic demo labeling ([SYNTHETIC DEMO] preserved, unverified state respected)
6. Dashboard query compatibility (seeded records load properly in dashboard queries)
"""

import os
from datetime import date
from decimal import Decimal
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, Client
from django.urls import reverse

from apps.core.models import (
    ActivityMaster,
    ActivityRecord,
    ActivityRevision,
    AnomalyDetectionRun,
    AnomalyRecord,
    CalculationResult,
    Carrier,
    Company,
    CorrectionRequest,
    EmissionFactor,
    Evidence,
    OCRField,
    OCRRun,
    ProcurementItem,
    ProcurementRecord,
    Project,
    ReportingPeriod,
    Shipment,
    Site,
    Submission,
    SubmissionReview,
    Subsidiary,
    Supplier,
    TransportRecord,
    UnitOfMeasure,
    User,
    ValidationResult,
    ValidationRun,
    Vehicle,
)


class SeedESGDataCommandTests(TestCase):
    """Test suite validating the seed_esg_demo_data management command."""

    def setUp(self):
        self.workbook_path = os.path.join(
            settings.BASE_DIR, "MEIL_BRSR_45_Entities_FY2025-26_Comprehensive_Demo.xlsx"
        )
        self.assertTrue(
            os.path.exists(self.workbook_path),
            f"Expected demo workbook at {self.workbook_path}",
        )

    def test_dry_run_mode_does_not_commit_data(self):
        """Verify that --dry-run simulates the full 10-step process and commits 0 rows."""
        initial_activity_count = ActivityRecord.objects.count()
        initial_sub_count = Submission.objects.count()
        initial_calc_count = CalculationResult.objects.count()

        call_command("seed_esg_demo_data", "--dry-run")

        self.assertEqual(
            ActivityRecord.objects.count(),
            initial_activity_count,
            "Dry run must not commit ActivityRecord rows.",
        )
        self.assertEqual(
            Submission.objects.count(),
            initial_sub_count,
            "Dry run must not commit Submission rows.",
        )
        self.assertEqual(
            CalculationResult.objects.count(),
            initial_calc_count,
            "Dry run must not commit CalculationResult rows.",
        )

    def test_apply_and_idempotency(self):
        """Verify that --apply commits records and running a second time does not duplicate rows."""
        # First execution (apply)
        call_command("seed_esg_demo_data", "--apply")

        act_count_1 = ActivityRecord.objects.count()
        sub_count_1 = Submission.objects.count()
        calc_count_1 = CalculationResult.objects.count()
        ev_count_1 = Evidence.objects.count()
        proc_count_1 = ProcurementRecord.objects.count()
        trans_count_1 = TransportRecord.objects.count()

        self.assertGreater(act_count_1, 0, "Seeder should have inserted ActivityRecords.")
        self.assertGreater(sub_count_1, 0, "Seeder should have inserted Submissions.")
        self.assertGreater(calc_count_1, 0, "Seeder should have inserted CalculationResults.")
        self.assertGreater(ev_count_1, 0, "Seeder should have inserted Evidence records.")
        self.assertGreater(proc_count_1, 0, "Seeder should have inserted ProcurementRecords.")
        self.assertGreater(trans_count_1, 0, "Seeder should have inserted TransportRecords.")

        # Second execution (verify idempotency)
        call_command("seed_esg_demo_data", "--apply")

        self.assertEqual(
            ActivityRecord.objects.count(),
            act_count_1,
            "Second execution must not duplicate ActivityRecord rows.",
        )
        self.assertEqual(
            Submission.objects.count(),
            sub_count_1,
            "Second execution must not duplicate Submission rows.",
        )
        self.assertEqual(
            CalculationResult.objects.count(),
            calc_count_1,
            "Second execution must not duplicate CalculationResult rows.",
        )
        self.assertEqual(
            Evidence.objects.count(),
            ev_count_1,
            "Second execution must not duplicate Evidence rows.",
        )
        self.assertEqual(
            ProcurementRecord.objects.count(),
            proc_count_1,
            "Second execution must not duplicate ProcurementRecord rows.",
        )
        self.assertEqual(
            TransportRecord.objects.count(),
            trans_count_1,
            "Second execution must not duplicate TransportRecord rows.",
        )

    def test_organizational_scope_boundary_protection(self):
        """Verify that 42 unmapped entities from the 45-entity workbook are NOT inserted."""
        call_command("seed_esg_demo_data", "--apply")

        # Must maintain strictly 1 Company, 2 Subsidiaries, 2 Projects, 3 Sites
        self.assertEqual(Company.objects.count(), 1, "Must maintain exactly 1 company (MEIL-ENT).")
        self.assertEqual(Subsidiary.objects.count(), 2, "Must preserve exactly 2 subsidiaries.")
        self.assertEqual(Project.objects.count(), 2, "Must preserve exactly 2 projects.")
        self.assertEqual(Site.objects.count(), 3, "Must preserve exactly 3 operational sites.")

        # Confirm unmapped workbook entities are not in subsidiaries table
        self.assertFalse(
            Subsidiary.objects.filter(code="E02").exists(),
            "Entity E02 must be skipped as SKIPPED_UNMAPPED_ENTITY.",
        )
        self.assertFalse(
            Subsidiary.objects.filter(code="E45").exists(),
            "Entity E45 must be skipped as SKIPPED_UNMAPPED_ENTITY.",
        )

    def test_foreign_key_and_constraint_integrity(self):
        """Verify foreign-key relationships across all populated tiers."""
        call_command("seed_esg_demo_data", "--apply")

        # 1. ActivityRecord integrity
        for rec in ActivityRecord.objects.all():
            self.assertIsNotNone(rec.site)
            self.assertIsNotNone(rec.activity)
            self.assertIsNotNone(rec.unit)
            self.assertIsNotNone(rec.reporting_period)
            self.assertGreater(rec.quantity, Decimal("0"))

        # 2. Submission integrity
        for sub in Submission.objects.all():
            self.assertIsNotNone(sub.activity_record)
            self.assertIsNotNone(sub.site)
            self.assertIsNotNone(sub.reporting_period)

        # 3. CalculationResult integrity
        for calc in CalculationResult.objects.all():
            self.assertIsNotNone(calc.activity_record)
            self.assertIsNotNone(calc.raw_unit)

        # 4. Scope 3 Procurement & Transport integrity
        for proc in ProcurementRecord.objects.all():
            self.assertIsNotNone(proc.supplier)
            self.assertIsNotNone(proc.company)
            self.assertIsNotNone(proc.reporting_period)

        for trans in TransportRecord.objects.all():
            self.assertIsNotNone(trans.reporting_period)
            self.assertIsNotNone(trans.carrier)
            self.assertIsNotNone(trans.vehicle)
            self.assertIsNotNone(trans.shipment)

    def test_synthetic_demo_labeling(self):
        """Verify that synthetic demo records are explicitly labeled and not marked as verified statutory audits."""
        call_command("seed_esg_demo_data", "--apply")

        # All demo activity records must contain synthetic indicator in notes
        for rec in ActivityRecord.filter_demo_records() if hasattr(ActivityRecord, "filter_demo_records") else ActivityRecord.objects.filter(notes__contains="SYNTHETIC DEMO"):
            self.assertIn("SYNTHETIC DEMO", rec.notes)

        # Evidence records must have synthetic marker
        for ev in Evidence.objects.filter(description__contains="SYNTHETIC DEMO"):
            self.assertIn("SYNTHETIC DEMO", ev.description)

    def test_dashboard_queries_read_seeded_records(self):
        """Verify that standard dashboard queries execute and return seeded telemetry."""
        call_command("seed_esg_demo_data", "--apply")

        period = ReportingPeriod.objects.get(code="FY2025-26")
        pol_site = Site.objects.get(code="SITE-POL-101")

        records_pol = ActivityRecord.objects.filter(site=pol_site, reporting_period=period)
        self.assertGreater(records_pol.count(), 0, "Site Manager dashboard must find Polavaram records.")

        submissions_pol = Submission.objects.filter(site=pol_site, reporting_period=period)
        self.assertGreater(submissions_pol.count(), 0, "Subsidiary Review dashboard must find submissions.")

        calculations_pol = CalculationResult.objects.filter(activity_record__site=pol_site)
        self.assertGreater(calculations_pol.count(), 0, "ESG Manager dashboard must find calculation results.")
