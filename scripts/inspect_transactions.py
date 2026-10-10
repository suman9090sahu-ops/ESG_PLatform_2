import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
import django
django.setup()

from apps.core.models import ActivityRecord, Submission, Evidence, CalculationResult, ProcurementRecord

print(f"Total ActivityRecords: {ActivityRecord.objects.count()}")
for r in ActivityRecord.objects.all():
    notes = (r.notes or "").replace("\n", " ")[:50]
    print(f"ID:{r.id:<3} Site:{r.site.code:<16} Act:{r.activity.code:<22} Period:{r.reporting_period.code:<16} Status:{r.status:<10} Notes:{notes}")

print(f"\nTotal Submissions: {Submission.objects.count()}")
for s in Submission.objects.all():
    print(f"Sub ID:{s.id:<3} RecID:{s.activity_record_id:<3} Site:{s.site.code:<16} Status:{s.status:<22} Period:{s.reporting_period.code:<16}")

print(f"\nTotal Procurements: {ProcurementRecord.objects.count()}")
for pr in ProcurementRecord.objects.all():
    print(f"Proc ID:{pr.id:<3} Site:{pr.site.code:<16} Supplier:{pr.supplier.name:<25} Status:{pr.status:<12}")

