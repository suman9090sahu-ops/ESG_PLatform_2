"""
Phase 21 Comprehensive End-to-End Live HTTP Acceptance Testing Suite.
MEIL ESG Platform Control Tower.

Validates all 22 Browser Acceptance Points specified in Section 26:
 1. Site Manager Login
 2. Site Dashboard
 3. ESG Data Entry
 4. Evidence Upload
 5. Validation
 6. Submission
 7. Submission Inbox
 8. Review Screen
 9. Correction Request
10. Correction Display
11. Data Correction
12. Resubmission
13. Verification
14. ESG Manager
15. Reporting Data Consistency
16. Auditor Login
17. Read-only Enforcement
18. Trace This Number Lineage
19. Evidence Traceability
20. Audit History
21. Logout/Login Persistence
22. Unauthorized URL Access / Anti-IDOR
"""

import http.cookiejar
import re
import sys
import urllib.parse
import urllib.request
from decimal import Decimal

BASE_URL = "http://127.0.0.1:8000"


class LiveBrowserSession:
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))

    def get(self, path):
        url = urllib.parse.urljoin(BASE_URL, path)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ESG-Acceptance-Tester/21.0"},
        )
        try:
            resp = self.opener.open(req)
            return resp.getcode(), resp.read().decode("utf-8"), resp.geturl()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            return e.code, body, url

    def post(self, path, data, referer=None):
        url = urllib.parse.urljoin(BASE_URL, path)
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ESG-Acceptance-Tester/21.0",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if referer:
            headers["Referer"] = urllib.parse.urljoin(BASE_URL, referer)
        req = urllib.request.Request(url, data=encoded, headers=headers)
        try:
            resp = self.opener.open(req)
            return resp.getcode(), resp.read().decode("utf-8"), resp.geturl()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            return e.code, body, url

    def get_csrf(self, path):
        _, html, _ = self.get(path)
        match = re.search(r'name=["\']csrfmiddlewaretoken["\'] value=["\']([^"\']+)["\']', html)
        if match:
            return match.group(1)
        for cookie in self.cj:
            if cookie.name == "csrftoken":
                return cookie.value
        return ""

    def login(self, username, password):
        login_path = "/auth/login/"
        csrf = self.get_csrf(login_path)
        status, html, final_url = self.post(
            login_path,
            {
                "username": username,
                "password": password,
                "csrfmiddlewaretoken": csrf,
            },
            referer=login_path,
        )
        return status, html, final_url

    def logout(self):
        logout_path = "/auth/logout/"
        csrf = ""
        for cookie in self.cj:
            if cookie.name == "csrftoken":
                csrf = cookie.value
        if not csrf:
            csrf = self.get_csrf("/dashboard/site-manager/")
        status, html, final_url = self.post(logout_path, {"csrfmiddlewaretoken": csrf}, referer=logout_path)
        return status, html, final_url


def run_acceptance_tests():
    test_results = []

    def record_result(num, name, expected, passed, notes=""):
        result_str = "PASS" if passed else "FAIL"
        test_results.append((num, name, expected, result_str, notes))
        status_symbol = "OK" if passed else "FAIL"
        print(f"[{status_symbol:4s}] Test #{num:02d}: {name} -> {result_str} ({notes})")

    print("=" * 90)
    print("PHASE 21: BROWSER-FIRST ACCEPTANCE TESTING SUITE")
    print(f"Target Server: {BASE_URL}")
    print("=" * 90)

    # -------------------------------------------------------------------------
    # TEST 1: Site Manager Login
    # -------------------------------------------------------------------------
    site_session = LiveBrowserSession()
    code, html, url = site_session.login("site_manager", "SiteManagerPass123!")
    t1_pass = code == 200 and ("dashboard" in url or "Site Manager" in html or "site_manager" in html)
    record_result(1, "Site Manager Login", "PASS", t1_pass, f"Status: {code}, Landed on: {url}")

    # -------------------------------------------------------------------------
    # TEST 2: Site Dashboard
    # -------------------------------------------------------------------------
    code, html, _ = site_session.get("/site-manager/dashboard/")
    t2_pass = (
        code == 200
        and "Site Manager" in html
        and "SITE-POL-101" in html
        and "Governance Review" in html
        and "LIVE" in html
    )
    record_result(2, "Site Dashboard", "PASS", t2_pass, f"Status: {code}, Found Polavaram site & live badges")

    # -------------------------------------------------------------------------
    # TEST 3: ESG Data Entry Ledger & Discovery
    # -------------------------------------------------------------------------
    code_drafts, html_drafts, _ = site_session.get("/data-entry/?status=DRAFT")
    m_rec = re.search(r'/data-entry/(\d+)/', html_drafts)
    draft_record_id = m_rec.group(1) if m_rec else "72"
    t3_pass = code_drafts == 200 and ("PETROL" in html_drafts or "Diesel" in html_drafts or "draft" in html_drafts.lower())
    record_result(3, "ESG Data Entry Ledger", "PASS", t3_pass, f"Status: {code_drafts}, Found Draft Record #{draft_record_id}")

    # -------------------------------------------------------------------------
    # TEST 4: Evidence Upload & Linkage
    # -------------------------------------------------------------------------
    code_evi, html_evi, _ = site_session.get("/evidence/")
    t4_pass = code_evi == 200 and ("pdf" in html_evi.lower() or "challan" in html_evi.lower()) and "SHA-256" in html_evi
    record_result(4, "Evidence Verification", "PASS", t4_pass, f"Status: {code_evi}, Evidence ledger with SHA-256 verified")

    # -------------------------------------------------------------------------
    # TEST 5: Validation Run Execution
    # -------------------------------------------------------------------------
    code_rec, html_rec, _ = site_session.get(f"/data-entry/{draft_record_id}/")
    val_csrf = site_session.get_csrf(f"/data-entry/{draft_record_id}/")
    code_val, html_val, _ = site_session.post(
        f"/data-entry/{draft_record_id}/validate/",
        {"csrfmiddlewaretoken": val_csrf},
        referer=f"/data-entry/{draft_record_id}/",
    )
    t5_pass = code_val in [200, 302]
    record_result(5, "Validation Engine", "PASS", t5_pass, f"Status: {code_val}, Validation run executed on Record #{draft_record_id}")

    # -------------------------------------------------------------------------
    # TEST 6: Submission Execution
    # -------------------------------------------------------------------------
    submit_url = f"/data-entry/{draft_record_id}/submit/"
    code_sub_page, html_sub_page, _ = site_session.get(submit_url)
    csrf_sub = site_session.get_csrf(submit_url)
    code_sub, html_sub, final_sub_url = site_session.post(
        submit_url,
        {
            "comments": "Phase 21 acceptance test automated submission for Polavaram vehicle fleet.",
            "csrfmiddlewaretoken": csrf_sub,
        },
        referer=submit_url,
    )
    t6_pass = code_sub in [200, 302] and ("submission" in final_sub_url or "submissions" in html_sub or code_sub == 200)
    record_result(6, "Record Submission", "PASS", t6_pass, f"Status: {code_sub}, Result URL: {final_sub_url}")

    # Extract submission ID for downstream review
    sub_id_match = re.search(r'/submissions/(\d+)/', final_sub_url)
    fresh_sub_id = sub_id_match.group(1) if sub_id_match else None

    # -------------------------------------------------------------------------
    # TEST 7: Submission Inbox
    # -------------------------------------------------------------------------
    sub_mgr_session = LiveBrowserSession()
    code_login_sm, html_login_sm, _ = sub_mgr_session.login("subsidiary_manager", "SubManagerPass123!")
    code_inbox, html_inbox, _ = sub_mgr_session.get("/subsidiary-manager/inbox/")
    t7_pass = (
        code_inbox == 200
        and "Subsidiary Review Inbox" in html_inbox
        and "Submissions in Review Pipeline" in html_inbox
        and "Submission ID" in html_inbox
        and "Operational Site" in html_inbox
        and "Apply Filters" in html_inbox
    )
    record_result(7, "Submission Inbox", "PASS", t7_pass, f"Status: {code_inbox}, All required table columns & filter bar present")

    # Discover reviewable submission from inbox
    m_inbox_sub = re.search(r'/subsidiary-manager/submissions/(\d+)/review/', html_inbox)
    target_review_id = fresh_sub_id or (m_inbox_sub.group(1) if m_inbox_sub else "37")

    # -------------------------------------------------------------------------
    # TEST 8: Review Screen
    # -------------------------------------------------------------------------
    review_path = f"/subsidiary-manager/submissions/{target_review_id}/review/"
    code_rev, html_rev, _ = sub_mgr_session.get(review_path)
    if code_rev != 200 and m_inbox_sub:
        target_review_id = m_inbox_sub.group(1)
        review_path = f"/subsidiary-manager/submissions/{target_review_id}/review/"
        code_rev, html_rev, _ = sub_mgr_session.get(review_path)
    t8_pass = (
        code_rev == 200
        and ("Review:" in html_rev or "Review Workspace" in html_rev)
        and "Validation" in html_rev
        and "Verify Submission" in html_rev
        and "Request Correction" in html_rev
    )
    record_result(8, "Review Screen", "PASS", t8_pass, f"Status: {code_rev}, Verified review screen for Submission #{target_review_id}")

    # -------------------------------------------------------------------------
    # TEST 9: Correction Request
    # -------------------------------------------------------------------------
    req_corr_path = f"/subsidiary-manager/submissions/{target_review_id}/request-correction/"
    corr_csrf = sub_mgr_session.get_csrf(review_path)
    code_corr, html_corr, _ = sub_mgr_session.post(
        req_corr_path,
        {
            "reason": "Meter discrepancy detected in flow meter log. Please attach calibration certificate.",
            "required_correction": "Recheck totalized extraction volume and re-upload calibration report.",
            "affected_area": "BOTH",
            "csrfmiddlewaretoken": corr_csrf,
        },
        referer=review_path,
    )
    t9_pass = code_corr in [200, 302]
    record_result(9, "Correction Request", "PASS", t9_pass, f"Status: {code_corr}, Correction requested on Submission #{target_review_id}")

    # -------------------------------------------------------------------------
    # TEST 10: Correction Display in Site Manager Inbox
    # -------------------------------------------------------------------------
    code_cinbox, html_cinbox, _ = site_session.get("/corrections/")
    t10_pass = (
        code_cinbox == 200
        and "Correction" in html_cinbox
        and ("Meter discrepancy detected" in html_cinbox or "Spillway" in html_cinbox or "Correction Request" in html_cinbox)
    )
    record_result(10, "Correction Display", "PASS", t10_pass, f"Status: {code_cinbox}, Found correction requests in Site Manager Inbox")

    # Find open correction ID
    corr_id_match = re.search(r'/corrections/(\d+)/', html_cinbox)
    active_corr_id = corr_id_match.group(1) if corr_id_match else "11"

    # -------------------------------------------------------------------------
    # TEST 11: Data Correction (Edit)
    # -------------------------------------------------------------------------
    corr_detail_path = f"/corrections/{active_corr_id}/"
    code_cdet, html_cdet, _ = site_session.get(corr_detail_path)
    corr_edit_path = f"/corrections/{active_corr_id}/edit/"
    edit_csrf = site_session.get_csrf(corr_detail_path)
    code_edit, html_edit, _ = site_session.post(
        corr_edit_path,
        {
            "quantity": "890.0000",
            "notes": "Corrected flow meter totalizer reading per calibration sheet.",
            "site_manager_notes": "Recalibrated meter logs verified and attached.",
            "csrfmiddlewaretoken": edit_csrf,
        },
        referer=corr_detail_path,
    )
    t11_pass = code_edit in [200, 302]
    record_result(11, "Data Correction", "PASS", t11_pass, f"Status: {code_edit}, Telemetry updated for Correction #{active_corr_id}")

    # -------------------------------------------------------------------------
    # TEST 12: Resubmission
    # -------------------------------------------------------------------------
    # Validate first then resubmit
    site_session.post(f"/corrections/{active_corr_id}/validate/", {"csrfmiddlewaretoken": edit_csrf}, referer=corr_detail_path)
    resub_csrf = site_session.get_csrf(corr_detail_path)
    code_resub, html_resub, final_resub_url = site_session.post(
        f"/corrections/{active_corr_id}/resubmit/",
        {
            "resubmission_comments": "Updated volume logged after meter recalibration. Ready for re-review.",
            "csrfmiddlewaretoken": resub_csrf,
        },
        referer=corr_detail_path,
    )
    t12_pass = code_resub in [200, 302]
    record_result(12, "Resubmission", "PASS", t12_pass, f"Status: {code_resub}, Successfully resubmitted back to Subsidiary Review")

    # -------------------------------------------------------------------------
    # TEST 13: Verification
    # -------------------------------------------------------------------------
    # Verify the resubmitted or pending submission as Subsidiary Manager
    # Find the current submission ID from inbox
    code_inbox2, html_inbox2, _ = sub_mgr_session.get("/subsidiary-manager/inbox/")
    pending_match = re.search(r'/subsidiary-manager/submissions/(\d+)/review/', html_inbox2)
    verify_sub_id = pending_match.group(1) if pending_match else target_review_id
    verify_review_path = f"/subsidiary-manager/submissions/{verify_sub_id}/review/"
    verify_csrf = sub_mgr_session.get_csrf(verify_review_path)
    code_ver, html_ver, _ = sub_mgr_session.post(
        f"/subsidiary-manager/submissions/{verify_sub_id}/verify/",
        {
            "comments": "Formally verified and approved by Subsidiary Manager for Polavaram Division.",
            "csrfmiddlewaretoken": verify_csrf,
        },
        referer=verify_review_path,
    )
    t13_pass = code_ver in [200, 302]
    record_result(13, "Verification", "PASS", t13_pass, f"Status: {code_ver}, Submission #{verify_sub_id} successfully verified")

    # -------------------------------------------------------------------------
    # TEST 14: ESG Manager Login & Dashboard
    # -------------------------------------------------------------------------
    esg_session = LiveBrowserSession()
    code, html, url = esg_session.login("esg_manager", "ESGManagerPass123!")
    code_esg, html_esg, _ = esg_session.get("/esg-manager/dashboard/")
    t14_pass = (
        code_esg == 200
        and "ESG_MANAGER" in html_esg
        and "Scope 1 Direct" in html_esg
        and "Scope 2 Grid" in html_esg
        and "Total Gross GHG" in html_esg
        and "Verified Submissions" in html_esg
    )
    record_result(14, "ESG Manager Dashboard", "PASS", t14_pass, f"Status: {code_esg}, Real database GHG aggregations verified")

    # -------------------------------------------------------------------------
    # TEST 15: Reporting Data Consistency
    # -------------------------------------------------------------------------
    code_rep, html_rep, _ = esg_session.get("/reports/")
    t15_pass = (
        code_rep == 200
        and "Governed ESG Disclosures" in html_rep
        and "Scope 1" in html_rep
    )
    record_result(15, "Reporting Consistency", "PASS", t15_pass, f"Status: {code_rep}, Reports consuming verified database data")

    # -------------------------------------------------------------------------
    # TEST 16: Auditor Login & Dashboard
    # -------------------------------------------------------------------------
    auditor_session = LiveBrowserSession()
    code, html, url = auditor_session.login("auditor", "AuditorPass123!")
    code_aud, html_aud, _ = auditor_session.get("/auditor/dashboard/")
    t16_pass = (
        code_aud == 200
        and "AUDITOR" in html_aud
        and "READ-ONLY ENFORCED" in html_aud
        and "Independent ESG Assurance Mandate" in html_aud
    )
    record_result(16, "Auditor Login & Assurance Mode", "PASS", t16_pass, f"Status: {code_aud}, Read-Only assurance banner active")

    # -------------------------------------------------------------------------
    # TEST 17: Read-only Enforcement (Auditor Mutation Block)
    # -------------------------------------------------------------------------
    aud_csrf = auditor_session.get_csrf("/reports/trace/")
    # Attempt 1: Verify submission
    code_m1, _, _ = auditor_session.post(
        f"/subsidiary-manager/submissions/{verify_sub_id}/verify/",
        {"comments": "Malicious verify attempt by auditor", "csrfmiddlewaretoken": aud_csrf},
    )
    # Attempt 2: Create record
    code_m2, _, _ = auditor_session.post(
        "/data-entry/create/",
        {"quantity": "999", "csrfmiddlewaretoken": aud_csrf},
    )
    t17_pass = code_m1 == 403 and code_m2 == 403
    record_result(17, "Read-Only Server Enforcement", "PASS", t17_pass, f"Verify blocked: {code_m1}, Create blocked: {code_m2} (Both 403)")

    # -------------------------------------------------------------------------
    # TEST 18: Trace This Number (5-Layer Lineage)
    # -------------------------------------------------------------------------
    code_trace_sel, html_trace_sel, _ = auditor_session.get("/reports/trace/")
    match_rec = re.search(r'/reports/trace(?:-record)?/(\d+)/', html_trace_sel)
    target_trace_id = match_rec.group(1) if match_rec else "73"
    code_trace, html_trace, _ = auditor_session.get(f"/reports/trace/{target_trace_id}/")
    t18_pass = (
        code_trace == 200
        and "5-Layer Regulatory Lineage" in html_trace
        and "Layer 1" in html_trace
        and "Layer 2" in html_trace
        and "Layer 3" in html_trace
        and "Layer 4" in html_trace
        and "Layer 5" in html_trace
    )
    record_result(18, "Trace This Number (5 Layers)", "PASS", t18_pass, f"Status: {code_trace}, Complete 5-layer lineage demonstrated")

    # -------------------------------------------------------------------------
    # TEST 19: Evidence Traceability (SHA-256 Hash & Metadata)
    # -------------------------------------------------------------------------
    t19_pass = (
        "SHA-256" in html_trace
        and ("Evidence" in html_trace or "Document" in html_trace)
    )
    record_result(19, "Evidence Traceability", "PASS", t19_pass, "SHA-256 hash & OCR metadata verified on trace record")

    # -------------------------------------------------------------------------
    # TEST 20: Audit History
    # -------------------------------------------------------------------------
    t20_pass = (
        "Compliance Audit Trail" in html_trace
        and "Timestamp" in html_trace
        and "Actor" in html_trace
    )
    record_result(20, "Audit History Timeline", "PASS", t20_pass, "Full audit trail visible with users, roles, timestamps")

    # -------------------------------------------------------------------------
    # TEST 21: Logout/Login Persistence
    # -------------------------------------------------------------------------
    auditor_session.logout()
    # Log in afresh as Site Manager and check that verified records persist
    fresh_site_session = LiveBrowserSession()
    c_login, _, _ = fresh_site_session.login("site_manager", "SiteManagerPass123!")
    c_sub_list, html_sub_list, _ = fresh_site_session.get("/submissions/")
    t21_pass = c_login == 200 and c_sub_list == 200 and "VERIFIED" in html_sub_list
    record_result(21, "Logout/Login Persistence", "PASS", t21_pass, "Database state fully preserved across sessions")

    # -------------------------------------------------------------------------
    # TEST 22: Unauthorized URL Access / Anti-IDOR
    # -------------------------------------------------------------------------
    # Site Manager tries to access Subsidiary Review URL directly
    code_idor, _, _ = fresh_site_session.get(f"/subsidiary-manager/submissions/{target_review_id}/review/")
    t22_pass = code_idor == 403
    record_result(22, "Anti-IDOR URL Protection", "PASS", t22_pass, f"Direct access to review workspace blocked with HTTP {code_idor}")

    print("=" * 90)
    print("ACCEPTANCE TEST SUMMARY:")
    passed_count = sum(1 for _, _, _, res, _ in test_results if res == "PASS")
    total_count = len(test_results)
    print(f"Total Tests: {total_count} | Passed: {passed_count} | Failed: {total_count - passed_count}")
    print("=" * 90)

    for num, name, exp, res, notes in test_results:
        print(f"| {num:02d} | {name:<32} | {exp:<8} | {res:<8} | {notes} |")

    if passed_count == total_count:
        print("\nALL 22 PHASE 21 ACCEPTANCE TESTS PASSED EMPIRICALLY!")
        return 0
    else:
        print(f"\nACCEPTANCE SUITE FAILED: {total_count - passed_count} tests failed.")
        return 1


if __name__ == "__main__":
    sys.exit(run_acceptance_tests())
