import os
import sys
import django

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.core.models import (
    Company, Subsidiary, Project, Site, User,
    CompanyAssignment, SubsidiaryAssignment, ProjectAssignment, SiteAssignment,
    ReportingPeriod, ActivityRecord, Submission, Evidence, ValidationRun,
    CalculationResult, ProcurementRecord, TransportRecord, AnomalyRecord
)

print("=" * 80)
print("ORGANIZATIONAL REFERENCE TRACE")
print("=" * 80)

for c in Company.objects.all():
    print(f"\nCOMPANY: ID={c.id}, Code={c.code}, Name={c.name}")
    print(f"  Subsidiaries count: {c.subsidiaries.count()}")
    print(f"  ReportingPeriods count: {c.reporting_periods.count()} -> {[rp.code for rp in c.reporting_periods.all()]}")
    print(f"  CompanyAssignments count: {c.assigned_users.count()} -> {[ca.user.username for ca in c.assigned_users.all()]}")

for s in Subsidiary.objects.all():
    print(f"\nSUBSIDIARY: ID={s.id}, Code={s.code}, Name={s.name} (Company: {s.company.code})")
    print(f"  Projects count: {s.projects.count()} -> {[p.code for p in s.projects.all()]}")
    print(f"  SubsidiaryAssignments: {s.assigned_users.count()} -> {[sa.user.username for sa in s.assigned_users.all()]}")

for p in Project.objects.all():
    print(f"\nPROJECT: ID={p.id}, Code={p.code}, Name={p.name} (Sub: {p.subsidiary.code})")
    print(f"  Sites count: {p.sites.count()} -> {[st.code for st in p.sites.all()]}")
    print(f"  ProjectAssignments: {getattr(p, 'assigned_users', getattr(p, 'assignments', None)).count() if hasattr(p, 'assigned_users') or hasattr(p, 'assignments') else 0}")

for st in Site.objects.all():
    print(f"\nSITE: ID={st.id}, Code={st.code}, Name={st.name} (Proj: {st.project.code})")
    print(f"  SiteAssignments: {st.assigned_users.count()} -> {[sa.user.username for sa in st.assigned_users.all()]}")
    print(f"  ActivityRecords: {st.activity_records.count()}")
    print(f"  Submissions: {st.submissions.count()}")
    print(f"  Procurements: {st.procurements.count()}")
    print(f"  Transports: {st.transports.count()}")
    print(f"  CalculationResults: {st.calculation_results.count()}")
