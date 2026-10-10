import os
import sys
import django

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
from django.db import connection
from django.apps import apps
from django.db.models import Count, Q

def run_inspection():
    print("=" * 80)
    print("ESG PLATFORM - COMPREHENSIVE DATABASE INSPECTION REPORT")
    print("=" * 80)

    # 1. Database Connection & Engine
    db_conn = connection
    vendor = db_conn.vendor
    db_name = connection.settings_dict.get('NAME')
    print(f"\n[1] DATABASE ENVIRONMENT")
    print(f"Database Engine: {vendor}")
    print(f"Database Identifier/Name: {db_name}")
    print(f"Connection Host: {connection.settings_dict.get('HOST', 'localhost')}")

    # 2. Total Tables
    table_names = connection.introspection.table_names()
    print(f"\n[2] DATABASE TABLES (Total: {len(table_names)})")

    # 3. Model Counts
    print(f"\n[3] MODEL RECORD COUNTS")
    app_models = [m for m in apps.get_models() if m._meta.app_label == 'core']
    other_models = [m for m in apps.get_models() if m._meta.app_label != 'core']
    
    print("\n--- Core Models ---")
    for m in app_models:
        cnt = m.objects.count()
        print(f"  {m.__name__:<25} ({m._meta.db_table}): {cnt} rows")

    print("\n--- Auth & Django System Models ---")
    for m in other_models:
        cnt = m.objects.count()
        print(f"  {m.__name__:<25} ({m._meta.db_table}): {cnt} rows")

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

    # 4. Companies and Subsidiaries
    print(f"\n[4] ORGANIZATIONAL HIERARCHY")
    print("\nCompanies:")
    for c in Company.objects.all():
        subs_cnt = c.subsidiaries.count()
        periods_cnt = c.reporting_periods.count()
        print(f"  ID:{c.id:<2} Code:{c.code:<20} Name:{c.name:<32} Subs:{subs_cnt} Periods:{periods_cnt} Status:{c.status}")

    print("\nSubsidiaries:")
    for s in Subsidiary.objects.all():
        prjs_cnt = s.projects.count()
        print(f"  ID:{s.id:<2} Code:{s.code:<20} Name:{s.name:<38} Company:[{s.company.code}] Projects:{prjs_cnt} Status:{s.status}")

    print("\nProjects:")
    for p in Project.objects.all():
        sites_cnt = p.sites.count()
        print(f"  ID:{p.id:<2} Code:{p.code:<20} Name:{p.name:<40} Sub:[{p.subsidiary.code}] Sites:{sites_cnt} Status:{p.status}")

    print("\nSites:")
    for st in Site.objects.all():
        rec_cnt = st.activity_records.count()
        sub_cnt = st.submissions.count()
        print(f"  ID:{st.id:<2} Code:{st.code:<20} Name:{st.name:<40} Proj:[{st.project.code}] Records:{rec_cnt} Submissions:{sub_cnt} Status:{st.status}")

    # 5. Reporting Periods
    print(f"\n[5] REPORTING PERIODS")
    for rp in ReportingPeriod.objects.all():
        rec_cnt = rp.activity_records.count()
        sub_cnt = rp.submissions.count()
        print(f"  ID:{rp.id:<2} Code:{rp.code:<20} Name:{rp.name:<45} Co:[{rp.company.code}] Status:{rp.status:<10} Records:{rec_cnt} Submissions:{sub_cnt}")

    # 6. Submissions Breakdown
    print(f"\n[6] SUBMISSION BREAKDOWN")
    for row in Submission.objects.values('status').annotate(cnt=Count('id')):
        print(f"  Status: {row['status']:<25} Count: {row['cnt']}")

    # 7. Activity Records Breakdown
    print(f"\n[7] ACTIVITY RECORD BREAKDOWN")
    for row in ActivityRecord.objects.values('status').annotate(cnt=Count('id')):
        print(f"  Status: {row['status']:<25} Count: {row['cnt']}")

    # 8. Activity Records by Company & Subsidiary lineage
    print(f"\n[8] ACTIVITY RECORDS & SUBMISSIONS BY SITE / SUBSIDIARY / COMPANY")
    for st in Site.objects.all():
        recs = st.activity_records.count()
        subs = st.submissions.count()
        if recs > 0 or subs > 0:
            print(f"  Site: {st.code:<16} (Proj: {st.project.code:<16}, Sub: {st.project.subsidiary.code:<16}, Co: {st.project.subsidiary.company.code:<16}) -> Records: {recs}, Submissions: {subs}")

    # 9. Evidence & OCR
    print(f"\n[9] EVIDENCE & OCR BREAKDOWN")
    print(f"  Total Evidence: {Evidence.objects.count()}")
    for row in Evidence.objects.values('status').annotate(cnt=Count('id')):
        print(f"    Status: {row['status']:<20} Count: {row['cnt']}")
    print(f"  Total OCRRun: {OCRRun.objects.count()}")
    print(f"  Total OCRField: {OCRField.objects.count()}")

    # 10. Validation & Anomaly Runs
    print(f"\n[10] VALIDATION & ANOMALY RUNS")
    print(f"  Total ValidationRun: {ValidationRun.objects.count()}")
    print(f"  Total ValidationResult: {ValidationResult.objects.count()}")
    print(f"  Total AnomalyDetectionRun: {AnomalyDetectionRun.objects.count()}")
    print(f"  Total AnomalyRecord: {AnomalyRecord.objects.count()}")

    # 11. Calculation Results
    print(f"\n[11] CALCULATION RESULTS")
    print(f"  Total CalculationResult: {CalculationResult.objects.count()}")
    for cr in CalculationResult.objects.all()[:10]:
        print(f"    Calc ID:{cr.id} Record:[{cr.activity_record_id}] Scope:{cr.scope} Value:{cr.calculated_value} {cr.result_unit}")
    if CalculationResult.objects.count() > 10:
        print(f"    ... and {CalculationResult.objects.count() - 10} more")

    # 12. Procurement & Transport
    print(f"\n[12] PROCUREMENT & TRANSPORT")
    print(f"  Suppliers: {Supplier.objects.count()}")
    print(f"  ProcurementRecord: {ProcurementRecord.objects.count()}")
    print(f"  ProcurementItem: {ProcurementItem.objects.count()}")
    print(f"  Carriers: {Carrier.objects.count()}")
    print(f"  Vehicles: {Vehicle.objects.count()}")
    print(f"  Shipments: {Shipment.objects.count()}")
    print(f"  TransportRecords: {TransportRecord.objects.count()}")

    # 13. Audit Logs
    print(f"\n[13] AUDIT LOGS")
    print(f"  Total AuthAuditLog: {AuthAuditLog.objects.count()}")
    event_counts = AuthAuditLog.objects.values('event_type').annotate(cnt=Count('id')).order_by('-cnt')[:10]
    for ev in event_counts:
        print(f"    Event: {ev['event_type']:<30} Count: {ev['cnt']}")

    # 14. Master Data Counts
    print(f"\n[14] MASTER / CONFIGURATION DATA")
    print(f"  Activity Categories: {ActivityCategory.objects.count()}")
    print(f"  Units of Measure: {UnitOfMeasure.objects.count()}")
    print(f"  Activity Master: {ActivityMaster.objects.count()}")
    print(f"  Validation Rules: {ValidationRule.objects.count()}")
    print(f"  Anomaly Rules: {AnomalyRule.objects.count()}")
    print(f"  Scope 3 Categories: {Scope3Category.objects.count()}")
    print(f"  Emission Factors: {EmissionFactor.objects.count()}")
    print(f"  Roles: {Role.objects.count()}")
    print(f"  Users: {User.objects.count()}")
    print(f"  UserRoles: {UserRole.objects.count()}")
    print("=" * 80)

if __name__ == "__main__":
    run_inspection()
