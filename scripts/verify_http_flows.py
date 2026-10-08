"""
MEIL ESG CONTROL TOWER — Phase 14 HTTP Web Flow Verification Script
Simulates full browser HTTP session using Django Client:
1. Site Manager login, dashboard pending alert check, corrections inbox rendering.
2. Correction detail page rendering with baseline values.
3. POST operational telemetry revision form, revalidation outcome check.
4. POST resubmission confirmation, redirection, and resolution check.
5. Subsidiary Manager login, review inbox check.
6. Review detail comparative delta ledger and timeline check.
7. POST verify action, lifecycle completion check.
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
from django.test import Client
from apps.core.models import CorrectionRequest, Submission, SubmissionStatus, RecordStatus
from scripts.seed_phase14_demo import seed_demo


def verify_http_flows():
    print("=" * 80)
    print("  PHASE 14 HTTP BROWSER FLOW VERIFICATION (DJANGO CLIENT)")
    print("=" * 80)

    seed_demo()

    client_sm = Client()

    # 1. Login Site Manager
    login_ok = client_sm.login(username="sm_demo", password="Pass123!")
    assert login_ok, "Site Manager authentication failed"
    print("[1/7] Site Manager successfully authenticated via HTTP session.")

    # 2. Check Dashboard Alert
    dash_res = client_sm.get("/site-manager/dashboard/")
    assert dash_res.status_code == 200, f"Dashboard returned {dash_res.status_code}"
    assert "Correction" in dash_res.content.decode("utf-8"), "Dashboard does not mention corrections!"
    print("[2/7] Site Manager Dashboard renders active correction notification.")

    # 3. Check Corrections Inbox
    inbox_res = client_sm.get("/site-manager/corrections/")
    assert inbox_res.status_code == 200, f"Inbox returned {inbox_res.status_code}"
    content = inbox_res.content.decode("utf-8")
    assert "Correction Requests" in content, "Correction Requests title missing from inbox"
    assert "Stationary Diesel Generator" in content, "Activity title missing from inbox"
    print("[3/7] Corrections Inbox renders with correct table columns and items.")

    # 4. Open Correction Detail
    corr = CorrectionRequest.objects.filter(activity_record__activity__code="ACT-DG-DEMO").latest("created_at")
    detail_res = client_sm.get(f"/corrections/{corr.id}/")
    assert detail_res.status_code == 200, f"Detail page returned {detail_res.status_code}"
    detail_html = detail_res.content.decode("utf-8")
    assert "Fuel invoice discrepancy" in detail_html, "Review reason missing from detail page"
    assert "4,500" in detail_html or "4500" in detail_html, "Original quantity missing from detail page"
    print(f"[4/7] Correction Detail page #{corr.id} renders review decision, reason, and telemetry.")

    # 5. POST Operational Revision Form
    edit_res = client_sm.post(f"/corrections/{corr.id}/edit/", {
        "quantity": "4850.0000",
        "unit": corr.activity_record.unit.id,
        "measurement_date": corr.activity_record.measurement_date.isoformat(),
        "notes": "Updated to 4,850 L per delivery slip batch #104.",
        "site_manager_notes": "Delivery slip confirmed with logistics officer.",
    })
    assert edit_res.status_code == 302, f"Expected 302 redirect after edit, got {edit_res.status_code}"
    corr.refresh_from_db()
    assert corr.status in ["READY_FOR_RESUBMISSION", "IN_PROGRESS"]
    print(f"[5/7] Correction edit POST succeeded: quantity updated to {corr.activity_record.quantity}, status={corr.status}.")

    # 6. POST Resubmission
    resubmit_res = client_sm.post(f"/corrections/{corr.id}/resubmit/", {
        "confirm": "on",
        "resubmission_comments": "Resubmitting revised telemetry 4,850 L.",
    })
    assert resubmit_res.status_code == 302, f"Expected 302 redirect after resubmission, got {resubmit_res.status_code}"
    corr.refresh_from_db()
    assert corr.status == "RESOLVED", f"Expected RESOLVED, got {corr.status}"
    sub2 = corr.resubmission
    assert sub2 is not None, "Resubmission reference not set!"
    print(f"[6/7] Resubmission POST executed: Submission #{sub2.submission_number} created, CorrectionRequest marked RESOLVED.")

    # 7. Subsidiary Manager Comparative Review & Verification
    client_sub = Client()
    login_sub_ok = client_sub.login(username="sub_demo", password="Pass123!")
    assert login_sub_ok, "Subsidiary Manager authentication failed"

    sub_inbox = client_sub.get("/subsidiary-manager/submissions/")
    assert sub_inbox.status_code == 200
    assert "Stationary Diesel Generator" in sub_inbox.content.decode("utf-8")

    review_res = client_sub.get(f"/subsidiary-manager/submissions/{sub2.id}/review/")
    assert review_res.status_code == 200
    review_html = review_res.content.decode("utf-8")
    assert "Comparative Delta Ledger" in review_html or "Resubmission Comparative" in review_html
    assert "4,500" in review_html or "4500" in review_html
    assert "4,850" in review_html or "4850" in review_html
    assert "+350" in review_html or "350" in review_html

    # POST Verify
    verify_res = client_sub.post(f"/subsidiary-manager/submissions/{sub2.id}/verify/", {
        "confirm": "on",
        "comments": "Verified against delivery slip batch #104. Approved.",
    })
    assert verify_res.status_code == 302
    sub2.refresh_from_db()
    assert sub2.status == SubmissionStatus.VERIFIED
    assert sub2.activity_record.status == RecordStatus.VERIFIED
    print(f"[7/7] Subsidiary Manager reviewed Comparative Delta Ledger and VERIFIED Submission #{sub2.submission_number}.")

    print("=" * 80)
    print("  ALL HTTP WEB FLOWS VERIFIED SUCCESSFULLY (STATUS 200 / 302)!")
    print("=" * 80)


if __name__ == "__main__":
    verify_http_flows()
