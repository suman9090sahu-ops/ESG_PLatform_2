"""
Seed data for Phase 14 Browser Verification:
Creates:
1. Site Manager (sm_demo / Pass123!)
2. Subsidiary Manager (sub_demo / Pass123!)
3. An Activity Record with a pending Correction Request in OPEN state.
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

from apps.core.evidence_services import create_evidence_record
from apps.core.models import (
    ActivityCategory,
    ActivityMaster,
    ActivityRecord,
    Company,
    CorrectionAffectedArea,
    CorrectionRequest,
    CorrectionStatus,
    EvidenceType,
    MasterStatus,
    OrganizationStatus,
    PeriodStatus,
    Project,
    RecordStatus,
    ReportingPeriod,
    Role,
    ScopeClassification,
    Site,
    SiteAssignment,
    Submission,
    SubmissionStatus,
    Subsidiary,
    SubsidiaryAssignment,
    UnitDimension,
    UnitOfMeasure,
    UserRole,
    ValidationStatus,
)
from apps.core.review_services import request_correction_submission
from apps.core.submission_services import submit_activity_record
from apps.core.validation_services import execute_validation_run, seed_standard_validation_rules

User = get_user_model()


def seed_demo():
    seed_standard_validation_rules()

    role_sm, _ = Role.objects.get_or_create(code=Role.Code.SITE_MANAGER, defaults={"name": "Site Manager"})
    role_sub, _ = Role.objects.get_or_create(code=Role.Code.SUBSIDIARY_MANAGER, defaults={"name": "Subsidiary Manager"})

    company, _ = Company.objects.get_or_create(
        code="MEIL-DEMO",
        defaults={"name": "MEIL Enterprise Group Demo", "status": OrganizationStatus.ACTIVE},
    )
    sub, _ = Subsidiary.objects.get_or_create(
        code="MEIL-WATER-DEMO",
        defaults={"company": company, "name": "MEIL Water Division", "status": OrganizationStatus.ACTIVE},
    )
    proj, _ = Project.objects.get_or_create(
        code="PRJ-POL-DEMO",
        defaults={"subsidiary": sub, "name": "Polavaram Dam Project", "status": OrganizationStatus.ACTIVE},
    )
    site, _ = Site.objects.get_or_create(
        code="SITE-POL-DEMO",
        defaults={"project": proj, "name": "Polavaram Intake Station", "status": OrganizationStatus.ACTIVE},
    )

    sm, _ = User.objects.get_or_create(
        username="sm_demo",
        defaults={"email": "sm.demo@meil.in", "first_name": "Ramesh", "last_name": "Kumar"},
    )
    sm.set_password("Pass123!")
    sm.save()
    UserRole.objects.get_or_create(user=sm, role=role_sm, defaults={"is_primary": True})
    SiteAssignment.objects.get_or_create(user=sm, site=site)

    sub_user, _ = User.objects.get_or_create(
        username="sub_demo",
        defaults={"email": "sub.demo@meil.in", "first_name": "Suresh", "last_name": "Reddy"},
    )
    sub_user.set_password("Pass123!")
    sub_user.save()
    UserRole.objects.get_or_create(user=sub_user, role=role_sub, defaults={"is_primary": True})
    SubsidiaryAssignment.objects.get_or_create(user=sub_user, subsidiary=sub)

    period, _ = ReportingPeriod.objects.get_or_create(
        code="FY2025-26-DEMO",
        defaults={
            "company": company,
            "name": "FY 2025-26 Demo Cycle",
            "fiscal_year": "2025-26",
            "start_date": timezone.now().date() - timezone.timedelta(days=30),
            "end_date": timezone.now().date() + timezone.timedelta(days=330),
            "status": PeriodStatus.OPEN,
        },
    )

    cat, _ = ActivityCategory.objects.get_or_create(code="DEMO-FUEL", defaults={"name": "Fuel & Generators"})
    unit_l, _ = UnitOfMeasure.objects.get_or_create(
        code="L-DEMO",
        defaults={"name": "Liters", "symbol": "L", "dimension": UnitDimension.VOLUME},
    )
    act, _ = ActivityMaster.objects.get_or_create(
        code="ACT-DG-DEMO",
        defaults={
            "category": cat,
            "name": "Stationary Diesel Generator #4",
            "scope_classification": ScopeClassification.SCOPE_1,
            "base_unit": unit_l,
            "status": MasterStatus.ACTIVE,
            "validation_rules": {"evidence_required": True},
        },
    )

    # Clean existing demo record if any
    old_records = ActivityRecord.objects.filter(site=site, reporting_period=period, activity=act)
    for old_rec in old_records:
        old_rec.evidence_files.all().delete()
        old_rec.revisions.all().delete()
        CorrectionRequest.objects.filter(activity_record=old_rec).delete()
        for sub in old_rec.submissions.all():
            sub.reviews.all().delete()
            sub.delete()
        old_rec.delete()

    rec = ActivityRecord.objects.create(
        site=site,
        reporting_period=period,
        activity=act,
        quantity=Decimal("4500.0000"),
        unit=unit_l,
        measurement_date=timezone.now().date(),
        notes="Diesel run for site extraction pumps.",
        evidence_reference="INV-DEMO-001",
        status=RecordStatus.READY,
        created_by=sm,
    )

    test_file = SimpleUploadedFile(
        "diesel_invoice_slip.pdf",
        b"%PDF-1.4 Mock Diesel Invoice Slip for 4,500 L.",
        content_type="application/pdf",
    )
    create_evidence_record(
        activity_record=rec,
        uploaded_file=test_file,
        evidence_type=EvidenceType.FUEL_CHALLAN,
        description="Initial fuel delivery slip",
        user=sm,
    )

    execute_validation_run(rec, executed_by=sm)
    sub1 = submit_activity_record(rec, user=sm)

    review = request_correction_submission(
        submission=sub1,
        user=sub_user,
        reason="Fuel invoice discrepancy: delivery slip indicates 4,850 L instead of 4,500 L.",
        required_correction="Please revise consumption to 4,850 L and attach revised meter confirmation slip.",
        affected_area=CorrectionAffectedArea.ACTIVITY_DATA,
    )

    print("Successfully seeded Phase 14 demo records:")
    print(f"Site Manager: sm_demo / Pass123!")
    print(f"Subsidiary Manager: sub_demo / Pass123!")
    print(f"Correction Request ID: {sub1.latest_correction_request.id}")


if __name__ == "__main__":
    seed_demo()
