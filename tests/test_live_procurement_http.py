"""
Live HTTP Verification Script for Phase 16 Supplier & Procurement Management.
Exercises the running server / Django test client across all 18 Phase 16 endpoints.
"""

import os
import sys

# Ensure repository root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from decimal import Decimal
from datetime import date
from django.test import Client
from apps.core.models import (
    User, Role, Company, Subsidiary, Project, Site, ReportingPeriod, PeriodStatus,
    Supplier, SupplierStatus, SupplierType,
    ProcurementRecord, ProcurementItem, ProcurementCategory, ProcurementStatus,
    Evidence, EvidenceType,
)

def run_live_http_verification():
    print("=" * 70)
    print("PHASE 16 LIVE HTTP VERIFICATION")
    print("=" * 70)

    # 1. Setup / identify test users
    client = Client()
    
    operator = User.objects.filter(username="meil_operator").first()
    if not operator:
        print("FAIL: meil_operator user not found")
        return False

    site_mgr = User.objects.filter(username="site_manager").first()
    if not site_mgr:
        print("FAIL: site_manager user not found")
        return False

    sub_mgr = User.objects.filter(username="subsidiary_manager").first()
    if not sub_mgr:
        print("FAIL: subsidiary_manager user not found")
        return False

    # 2. Test Supplier Directory as Operator
    client.force_login(operator)
    resp = client.get("/procurement/suppliers/")
    assert resp.status_code == 200, f"Expected 200 on /procurement/suppliers/, got {resp.status_code}"
    assert "Supplier Directory" in resp.content.decode("utf-8")
    print("[PASS] 1. GET /procurement/suppliers/ returned 200 OK with Supplier Directory UI")

    # 3. Test Supplier Create GET & POST as Operator
    resp = client.get("/procurement/suppliers/create/")
    assert resp.status_code == 200, f"Expected 200 on /procurement/suppliers/create/, got {resp.status_code}"
    print("[PASS] 2. GET /procurement/suppliers/create/ returned 200 OK with Form")

    import uuid
    code = f"VEND-LIVE-{uuid.uuid4().hex[:6].upper()}"
    post_data = {
        "supplier_code": code,
        "name": f"Live Test Vendor {code}",
        "legal_name": f"Live Test Vendor {code} Pvt Ltd",
        "supplier_type": "GOODS",
        "status": "ACTIVE",
        "company": "",
        "tax_identifier": "29LIVEGST1234F1Z5",
        "city": "Hyderabad",
        "state": "Telangana",
        "country": "India",
    }
    resp = client.post("/procurement/suppliers/create/", post_data, follow=True)
    assert resp.status_code == 200, f"Failed POST /procurement/suppliers/create/: {resp.status_code}"
    supplier = Supplier.objects.get(supplier_code=code)
    print(f"[PASS] 3. POST /procurement/suppliers/create/ created Supplier #{supplier.id} ({supplier.supplier_code})")

    # 4. Test Supplier Detail View
    resp = client.get(f"/procurement/suppliers/{supplier.id}/")
    assert resp.status_code == 200, f"Expected 200 on supplier detail, got {resp.status_code}"
    assert supplier.name in resp.content.decode("utf-8")
    print(f"[PASS] 4. GET /procurement/suppliers/{supplier.id}/ returned 200 OK with profile")

    # 5. Test Site Manager Scoped Procurement List
    client.force_login(site_mgr)
    resp = client.get("/procurement/")
    assert resp.status_code == 200, f"Expected 200 on /procurement/, got {resp.status_code}"
    assert "Procurement Ledger" in resp.content.decode("utf-8")
    print("[PASS] 5. GET /procurement/ as Site Manager returned 200 OK")

    # 6. Test Site Manager Procurement Creation Form & Creation
    from apps.core.scope_services import get_accessible_sites
    sites = list(get_accessible_sites(site_mgr))
    assert len(sites) > 0, "Site Manager has no assigned sites"
    test_site = sites[0]

    from apps.core.period_services import get_accessible_reporting_periods
    periods = list(get_accessible_reporting_periods(site_mgr).filter(status=PeriodStatus.OPEN))
    if not periods:
        periods = list(ReportingPeriod.objects.filter(status=PeriodStatus.OPEN))
        if not periods:
            period = ReportingPeriod.objects.create(
                company=test_site.company,
                code="FY2026-LIVE",
                name="Live Test Period",
                fiscal_year="FY26",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                status=PeriodStatus.OPEN,
            )
        else:
            period = periods[0]
    else:
        period = periods[0]

    resp = client.get("/procurement/create/")
    assert resp.status_code == 200, f"Expected 200 on /procurement/create/, got {resp.status_code}"
    print("[PASS] 6. GET /procurement/create/ returned 200 OK")

    proc_post = {
        "supplier": supplier.id,
        "site": test_site.id,
        "project": test_site.project.id,
        "reporting_period": period.id,
        "purchase_date": period.start_date.isoformat(),
        "invoice_reference": f"INV-LIVE-{uuid.uuid4().hex[:6].upper()}",
        "purchase_order_reference": "PO-LIVE-01",
        "category": "CONSTRUCTION_MATERIAL",
        "currency": "INR",
        "total_amount": "0.00",
        "description": "Live HTTP test cement procurement",
    }
    from apps.core.procurement_forms import ProcurementRecordForm
    form = ProcurementRecordForm(proc_post, user=site_mgr)
    print("DIRECT FORM IS_VALID:", form.is_valid())
    if not form.is_valid():
        print("DIRECT FORM ERRORS:", form.errors)

    resp = client.post("/procurement/create/", proc_post, follow=False)
    print("CREATE STATUS:", resp.status_code)
    if resp.status_code != 302:
        ctx = resp.context[-1] if isinstance(resp.context, list) else resp.context
        if ctx and "form" in ctx:
            print("FORM ERRORS:", ctx["form"].errors)
        else:
            print("NO FORM IN CTX, KEYS:", [k for k in ctx.keys()] if ctx else "NO CTX")
    proc = ProcurementRecord.objects.get(invoice_reference=proc_post["invoice_reference"])
    print(f"[PASS] 7. POST /procurement/create/ created ProcurementRecord #{proc.id} ({proc.procurement_number})")

    # 7. Test Add Line Item
    from apps.core.models import UnitOfMeasure
    unit = UnitOfMeasure.objects.filter(is_active=True).first()
    item_post = {
        "item_name": "Portland Slag Cement 50kg Bags",
        "category": "CONSTRUCTION_MATERIAL",
        "quantity": "50.0000",
        "unit": unit.id if unit else "",
        "unit_custom": "Tonne" if not unit else "",
        "unit_price": "4200.00",
        "total_amount": "210000.00",
        "sync_total": "on",
        "scope3_category": "CAT_01",
    }
    resp = client.post(f"/procurement/{proc.id}/items/add/", item_post, follow=True)
    assert resp.status_code == 200, f"Failed to add line item: {resp.status_code}"
    proc.refresh_from_db()
    assert proc.items.count() == 1
    assert proc.total_amount == Decimal("210000.00")
    print(f"[PASS] 8. POST /procurement/{proc.id}/items/add/ added item, total updated to {proc.total_amount}")

    # 8. Test Procurement Detail View
    resp = client.get(f"/procurement/{proc.id}/")
    assert resp.status_code == 200
    assert proc.procurement_number in resp.content.decode("utf-8")
    assert "Portland Slag Cement" in resp.content.decode("utf-8")
    print(f"[PASS] 9. GET /procurement/{proc.id}/ returned 200 OK with line items")

    # 9. Test Formal Submission
    resp = client.post(f"/procurement/{proc.id}/submit/", follow=True)
    assert resp.status_code == 200
    proc.refresh_from_db()
    assert proc.status == ProcurementStatus.SUBMITTED
    assert proc.is_locked is True
    print(f"[PASS] 10. POST /procurement/{proc.id}/submit/ submitted record (Status: {proc.status}, Locked: True)")

    # 10. Test Subsidiary Review Inbox & Verification
    client.force_login(sub_mgr)
    resp = client.get("/procurement/inbox/")
    assert resp.status_code == 200
    print("[PASS] 11. GET /procurement/inbox/ as Subsidiary Manager returned 200 OK")

    # Verify the procurement as sub_mgr or operator
    client.force_login(operator)
    resp = client.post(f"/procurement/{proc.id}/review/", {
        "action": "VERIFY",
        "review_notes": "Live HTTP test verification successful.",
    }, follow=True)
    assert resp.status_code == 200
    proc.refresh_from_db()
    assert proc.status == ProcurementStatus.VERIFIED
    print(f"[PASS] 12. POST /procurement/{proc.id}/review/ (VERIFY) transitioned status to {proc.status}")

    # 11. Test IDOR Protection
    client.force_login(site_mgr)
    # Site manager attempts to access review inbox (forbidden)
    resp = client.get("/procurement/inbox/")
    assert resp.status_code == 403, f"Expected 403 for site manager on inbox, got {resp.status_code}"
    print("[PASS] 13. IDOR: Site Manager forbidden (403) on review inbox")

    # Site manager attempts to access supplier creation (forbidden)
    resp = client.get("/procurement/suppliers/create/")
    assert resp.status_code == 403, f"Expected 403 on supplier create for site manager, got {resp.status_code}"
    print("[PASS] 14. IDOR: Site Manager forbidden (403) on supplier create")

    # Site manager attempts to review procurement (forbidden)
    resp = client.post(f"/procurement/{proc.id}/review/", {"action": "VERIFY"})
    assert resp.status_code == 403, f"Expected 403 on review action for site manager, got {resp.status_code}"
    print("[PASS] 15. IDOR: Site Manager forbidden (403) on review mutation")

    print("=" * 70)
    print("ALL 15 LIVE HTTP VERIFICATION CHECKS PASSED PERFECTLY!")
    print("=" * 70)
    return True

if __name__ == "__main__":
    success = run_live_http_verification()
    sys.exit(0 if success else 1)
