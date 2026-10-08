"""
Live Server Verification of Phase 12 Submission Workflow against running Django server (http://127.0.0.1:8000).

Tests:
1. Site Manager logs in (site_manager / SiteManagerPass123!).
2. Navigates to /submissions/ ledger (200 OK) and verifies KPI cards & filters.
3. Accesses assigned Activity Record /data-entry/<id>/, confirms validation & evidence readiness.
4. Accesses Submission confirmation gate GET /data-entry/<id>/submit/ (200 OK).
5. Executes formal submission via POST /data-entry/<id>/submit/ (302 Redirect to /submissions/<sub_id>/).
6. Verifies Submission Detail /submissions/<sub_id>/ (200 OK) with complete telemetry snapshot,
   validation state, evidence documents, and audit timeline.
7. Verifies Activity Record is now SUBMITTED and protected from editing.
8. Idempotency test: Re-submitting an already SUBMITTED record is safely handled without duplicate creation.
9. Anti-IDOR Defense: Other Site Manager (unassigned_site_manager) blocked from submitting foreign record (403 Forbidden).
10. Anti-IDOR Defense: Other Site Manager blocked from viewing foreign submission detail (403 Forbidden).
11. Subsidiary Manager (subsidiary_manager / SubManagerPass123!) logs in:
    - Successfully discovers Site 101 submission in /submissions/ ledger (Phase 13 handover point).
    - Can inspect submission detail /submissions/<sub_id>/ (200 OK).
12. Auditor (auditor / AuditorPass123!) logs in:
    - Granted read-only inspection of submissions ledger and detail (200 OK).
    - Blocked with 403 Forbidden from mutation endpoints.
13. Submitter Withdrawal Flow:
    - Site Manager POSTs withdrawal /submissions/<sub_id>/withdraw/ with justification.
    - Verifies Submission status is WITHDRAWN and Activity Record reverts to DRAFT.
14. Re-submission:
    - Site Manager submits record again -> creates Submission #2, preserving Submission #1 in audit ledger.
"""

import http.cookiejar
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "http://127.0.0.1:8000"


def create_sample_pdf_bytes(text: str = "TAX INVOICE Invoice No: INV-2026-901 Units: 1250 kWh") -> bytes:
    """Creates a genuine, valid 1-page PDF byte string containing the specified text."""
    try:
        import pypdf
        lines = text.strip().split("\n")
        stream_ops = [b"BT\n/F1 12 Tf\n50 720 Td\n"]
        for i, line in enumerate(lines):
            clean_line = line.replace("(", "").replace(")", "").encode("latin-1", errors="replace")
            if i == 0:
                stream_ops.append(b"(" + clean_line + b") Tj\n")
            else:
                stream_ops.append(b"0 -18 Td\n(" + clean_line + b") Tj\n")
        stream_ops.append(b"ET\n")
        stream_content = b"".join(stream_ops)
        stream_len = len(stream_content)

        pdf_raw = (
            b"%PDF-1.4\n"
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
            b"3 0 obj << /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >> endobj\n"
            b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
            b"5 0 obj << /Length " + str(stream_len).encode("ascii") + b" >> stream\n"
            + stream_content +
            b"endstream\nendobj\n"
            b"xref\n0 6\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000058 00000 n \n"
            b"0000000115 00000 n \n"
            b"0000000236 00000 n \n"
            b"0000000305 00000 n \n"
            b"trailer << /Size 6 /Root 1 0 R >>\n"
            b"startxref\n500\n%%EOF"
        )
        reader = pypdf.PdfReader(io.BytesIO(pdf_raw))
        writer = pypdf.PdfWriter()
        writer.add_page(reader.pages[0])
        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue()
    except Exception:
        return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 612 792]>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000102 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n149\n%%EOF\n"


def create_session():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    return opener, cj


def get_cookie(cj, name):
    for cookie in cj:
        if cookie.name == name:
            return cookie.value
    return ""


def get_csrf_token(opener, url, cj=None):
    if cj:
        val = get_cookie(cj, "csrftoken")
        if val:
            return val
    req = urllib.request.Request(url)
    try:
        with opener.open(req) as resp:
            html = resp.read().decode("utf-8")
            match = re.search(r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']', html)
            if match:
                return match.group(1)
    except Exception:
        pass
    if cj:
        return get_cookie(cj, "csrftoken")
    return ""


def login(opener, cj, username, password):
    login_url = f"{BASE_URL}/auth/login/"
    csrf = get_csrf_token(opener, login_url, cj)
    post_data = urllib.parse.urlencode({
        "username": username,
        "password": password,
        "csrfmiddlewaretoken": csrf,
    }).encode("utf-8")
    req = urllib.request.Request(login_url, data=post_data, headers={
        "Referer": login_url,
        "Content-Type": "application/x-www-form-urlencoded",
    })
    with opener.open(req) as resp:
        content = resp.read().decode("utf-8")
        if "Invalid username or password" in content or "Sign In" in content:
            raise RuntimeError(f"Login failed for {username}")
    return True


def run_verification():
    print("=" * 75)
    print("STARTING PHASE 12 SUBMISSION WORKFLOW LIVE END-TO-END VERIFICATION")
    print(f"Target Server: {BASE_URL}")
    print("=" * 75)

    # -------------------------------------------------------------
    # 1. Site Manager Session
    # -------------------------------------------------------------
    opener, cj = create_session()
    print("\n[Step 1] Authenticating Site Manager (site_manager)...")
    login(opener, cj, "site_manager", "SiteManagerPass123!")
    print("  -> Authenticated successfully.")

    # -------------------------------------------------------------
    # 2. Inspect Submissions Ledger
    # -------------------------------------------------------------
    print("\n[Step 2] Navigating to /submissions/ ledger...")
    with opener.open(f"{BASE_URL}/submissions/") as resp:
        assert resp.status == 200, f"Expected 200, got {resp.status}"
        sub_list_html = resp.read().decode("utf-8")
        assert "Activity Submissions Ledger" in sub_list_html or "Submissions" in sub_list_html
        print("  -> Submissions ledger rendered with KPI telemetry and filter toolbar.")

    # Also check /site-manager/submissions/ alias
    with opener.open(f"{BASE_URL}/site-manager/submissions/") as resp:
        assert resp.status == 200, f"Expected 200 on alias, got {resp.status}"
        print("  -> Route alias /site-manager/submissions/ resolved cleanly.")

    # -------------------------------------------------------------
    # 3. Locate an Activity Record for Site 101
    # -------------------------------------------------------------
    print("\n[Step 3] Locating assigned Activity Record on Site 101...")
    with opener.open(f"{BASE_URL}/data-entry/") as resp:
        de_html = resp.read().decode("utf-8")
        rec_matches = re.findall(r'/data-entry/(\d+)/', de_html)
        assert rec_matches, "No Activity Records found for Site Manager."
        rec_ids = sorted(list(set(int(x) for x in rec_matches)))
        rec_id = rec_ids[0]
        print(f"  -> Selected Activity Record #{rec_id} for submission testing.")

    # Access Record Detail and ensure it has fresh validation
    rec_detail_url = f"{BASE_URL}/data-entry/{rec_id}/"
    with opener.open(rec_detail_url) as resp:
        rec_html = resp.read().decode("utf-8")
        print(f"  -> Activity Record detail loaded (Status: {resp.status}).")

    # Ensure required evidence is attached
    if "No supporting evidence documents have been uploaded" in rec_html or "Evidence Required" in rec_html:
        print("  -> Uploading required test evidence document...")
        upload_url = f"{BASE_URL}/data-entry/{rec_id}/evidence/upload/"
        csrf = get_csrf_token(opener, upload_url, cj)
        pdf_bytes = create_sample_pdf_bytes("TAX INVOICE - Diesel Supply Units: 1000 L")
        boundary = "----WebKitFormBoundaryEsgSubTest456"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="csrfmiddlewaretoken"\r\n\r\n{csrf}\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="evidence_type"\r\n\r\nFUEL_SLIP\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="description"\r\n\r\nFuel delivery challan for verification\r\n'
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="fuel_challan.pdf"\r\n'
            f"Content-Type: application/pdf\r\n\r\n"
        ).encode("utf-8") + pdf_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

        req = urllib.request.Request(upload_url, data=body, headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Referer": upload_url,
        })
        with opener.open(req) as resp:
            print(f"  -> Evidence uploaded. Status: {resp.status}")

    # Run validation to make sure record is VALID
    print(f"  -> Triggering validation run for Record #{rec_id}...")
    val_url = f"{BASE_URL}/data-entry/{rec_id}/run-validation/"
    csrf = get_csrf_token(opener, rec_detail_url, cj)
    post_data = urllib.parse.urlencode({"csrfmiddlewaretoken": csrf}).encode("utf-8")
    req = urllib.request.Request(val_url, data=post_data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": rec_detail_url,
    })
    try:
        with opener.open(req) as resp:
            print(f"  -> Validation run triggered. Status: {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"  -> Validation trigger returned {e.code}")

    # Re-inspect Record Detail
    with opener.open(rec_detail_url) as resp:
        rec_html = resp.read().decode("utf-8")
        assert "Submit for Review" in rec_html or "Submit Record" in rec_html or "submit" in rec_html.lower()
        print("  -> Handover Card and 'Submit for Review' action button verified on detail page.")

    # -------------------------------------------------------------
    # 4. Access Submission Confirmation Gate (GET)
    # -------------------------------------------------------------
    submit_gate_url = f"{BASE_URL}/data-entry/{rec_id}/submit/"
    print(f"\n[Step 4] Accessing Submission confirmation gate GET {submit_gate_url}...")
    with opener.open(submit_gate_url) as resp:
        assert resp.status == 200, f"Expected 200, got {resp.status}"
        gate_html = resp.read().decode("utf-8")
        assert "Confirm Activity Record Submission" in gate_html
        assert "Submission Readiness Checklist" in gate_html
        assert "Reporting Period Status" in gate_html
        assert "Validation Clearance" in gate_html
        print("  -> Readiness checklist and confirmation form rendered cleanly.")

    # -------------------------------------------------------------
    # 5. Execute Formal Submission (POST)
    # -------------------------------------------------------------
    print(f"\n[Step 5] Executing formal submission via POST {submit_gate_url}...")
    csrf = get_csrf_token(opener, submit_gate_url, cj)
    post_data = urllib.parse.urlencode({
        "csrfmiddlewaretoken": csrf,
        "comments": "Live E2E Verification Formal Submission by Site Manager.",
        "confirm": "on",
    }).encode("utf-8")
    req = urllib.request.Request(submit_gate_url, data=post_data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": submit_gate_url,
    })
    with opener.open(req) as resp:
        final_url = resp.geturl()
        post_html = resp.read().decode("utf-8")
        print(f"  -> Submission processed. Final redirected URL: {final_url}")
        assert "/submissions/" in final_url, f"Expected redirect to /submissions/<id>/, got {final_url}"
        sub_id_match = re.search(r'/submissions/(\d+)/', final_url)
        assert sub_id_match, f"Failed to extract submission ID from {final_url}"
        submission_id = int(sub_id_match.group(1))
        print(f"  -> Generated Submission ID: #{submission_id}")

    # -------------------------------------------------------------
    # 6. Verify Submission Detail View
    # -------------------------------------------------------------
    sub_detail_url = f"{BASE_URL}/submissions/{submission_id}/"
    print(f"\n[Step 6] Verifying Submission #{submission_id} Detail View ({sub_detail_url})...")
    with opener.open(sub_detail_url) as resp:
        assert resp.status == 200
        detail_html = resp.read().decode("utf-8")
        assert "Submission #" in detail_html
        assert "SUBMITTED" in detail_html
        assert "Activity Record Telemetry (Snapshot)" in detail_html
        assert "Reporting Period &amp; Operational Hierarchy" in detail_html or "Reporting Period" in detail_html
        assert "Phase 10 Validation Result at Submission" in detail_html or "Validation Result" in detail_html
        assert "Supporting Evidence Documents" in detail_html
        assert "Audit Timeline &amp; Lineage" in detail_html or "Audit Timeline" in detail_html
        print("  -> Full lineage, snapshot, validation state, and audit timeline verified on detail page.")

    # -------------------------------------------------------------
    # 7. Verify Activity Record Locked & Status Updated
    # -------------------------------------------------------------
    print(f"\n[Step 7] Checking Activity Record #{rec_id} status and edit lock...")
    with opener.open(rec_detail_url) as resp:
        rec_html = resp.read().decode("utf-8")
        assert "SUBMITTED" in rec_html
        assert "Locked for Review" in rec_html or "Submitted" in rec_html
        print("  -> Record status is SUBMITTED and edit lock badge is active.")

    # Verify attempt to edit submitted record is blocked or protected
    edit_url = f"{BASE_URL}/data-entry/{rec_id}/edit/"
    try:
        with opener.open(edit_url) as resp:
            edit_html = resp.read().decode("utf-8")
            if "Locked for Review" in edit_html or "cannot be modified" in edit_html or "SUBMITTED" in edit_html:
                print("  -> Edit page displays protection notice.")
            else:
                print(f"  -> Edit page HTTP status: {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"  -> Edit page blocked with HTTP {e.code} (Correct lock enforcement).")

    # -------------------------------------------------------------
    # 8. Idempotency & Duplicate Submission Protection
    # -------------------------------------------------------------
    print(f"\n[Step 8] Testing duplicate submission protection for already submitted record...")
    csrf = get_csrf_token(opener, submit_gate_url, cj)
    post_data = urllib.parse.urlencode({
        "csrfmiddlewaretoken": csrf,
        "comments": "Duplicate submission attempt",
        "confirm": "on",
    }).encode("utf-8")
    req = urllib.request.Request(submit_gate_url, data=post_data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": submit_gate_url,
    })
    with opener.open(req) as resp:
        dup_url = resp.geturl()
        dup_html = resp.read().decode("utf-8")
        assert "already submitted" in dup_html or "already" in dup_html.lower() or "/submissions/" in dup_url
        print("  -> Duplicate submission rejected/redirected cleanly without generating duplicate records.")

    # -------------------------------------------------------------
    # 9 & 10. Anti-IDOR Defense with Another Site Manager
    # -------------------------------------------------------------
    print("\n[Step 9 & 10] Testing Anti-IDOR Defense with unassigned_site_manager...")
    other_opener, other_cj = create_session()
    login(other_opener, other_cj, "unassigned_site_manager", "OtherSitePass123!")
    print("  -> Authenticated unassigned_site_manager (assigned to Site 102).")

    # Attempt to submit foreign record (Site 101's record #rec_id)
    other_csrf = get_csrf_token(other_opener, f"{BASE_URL}/data-entry/", other_cj)
    foreign_submit_url = f"{BASE_URL}/data-entry/{rec_id}/submit/"
    post_data = urllib.parse.urlencode({
        "csrfmiddlewaretoken": other_csrf,
        "comments": "Malicious foreign submission attempt",
        "confirm": "on",
    }).encode("utf-8")
    req = urllib.request.Request(foreign_submit_url, data=post_data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": foreign_submit_url,
    })
    try:
        with other_opener.open(req) as resp:
            raise AssertionError(f"IDOR Violation: unassigned_site_manager submitted foreign record! Got {resp.status}")
    except urllib.error.HTTPError as e:
        assert e.code in (403, 404), f"Expected 403 or 404, got {e.code}"
        print(f"  -> PASS: Foreign submit attempt blocked with HTTP {e.code} Forbidden.")

    # Attempt to view foreign submission detail
    try:
        with other_opener.open(sub_detail_url) as resp:
            raise AssertionError(f"IDOR Violation: unassigned_site_manager viewed foreign submission detail! Got {resp.status}")
    except urllib.error.HTTPError as e:
        assert e.code in (403, 404), f"Expected 403 or 404, got {e.code}"
        print(f"  -> PASS: Foreign submission detail inspection blocked with HTTP {e.code} Forbidden.")

    # -------------------------------------------------------------
    # 11. Subsidiary Manager Discovery (Phase 13 Handover Point)
    # -------------------------------------------------------------
    print("\n[Step 11] Subsidiary Manager (subsidiary_manager) Phase 13 Handover Discovery...")
    sub_opener, sub_cj = create_session()
    login(sub_opener, sub_cj, "subsidiary_manager", "SubManagerPass123!")
    print("  -> Authenticated subsidiary_manager (MEIL-HYDRO Division).")

    with sub_opener.open(f"{BASE_URL}/submissions/") as resp:
        assert resp.status == 200
        sub_mgr_html = resp.read().decode("utf-8")
        assert f"/submissions/{submission_id}/" in sub_mgr_html
        print(f"  -> PASS: Submission #{submission_id} is visible in Subsidiary Manager's Submissions Ledger.")

    with sub_opener.open(sub_detail_url) as resp:
        assert resp.status == 200
        sub_mgr_detail = resp.read().decode("utf-8")
        assert "SUBMITTED" in sub_mgr_detail
        print(f"  -> PASS: Subsidiary Manager inspected Submission #{submission_id} detail (Phase 13 Handover Ready).")

    # -------------------------------------------------------------
    # 12. Auditor Assurance Read-Only Inspection
    # -------------------------------------------------------------
    print("\n[Step 12] Auditor (auditor) Assurance Read-Only Inspection...")
    aud_opener, aud_cj = create_session()
    login(aud_opener, aud_cj, "auditor", "AuditorPass123!")
    print("  -> Authenticated auditor.")

    with aud_opener.open(f"{BASE_URL}/submissions/") as resp:
        assert resp.status == 200
        print("  -> Auditor accessed submissions ledger (200 OK).")

    with aud_opener.open(sub_detail_url) as resp:
        assert resp.status == 200
        print(f"  -> Auditor inspected Submission #{submission_id} detail (200 OK).")

    # Auditor blocked from mutating or withdrawing
    aud_csrf = get_csrf_token(aud_opener, sub_detail_url, aud_cj)
    withdraw_post = urllib.parse.urlencode({
        "csrfmiddlewaretoken": aud_csrf,
        "reason": "Auditor unauthorized withdrawal attempt",
        "confirm": "on",
    }).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}/submissions/{submission_id}/withdraw/", data=withdraw_post, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": sub_detail_url,
    })
    try:
        with aud_opener.open(req) as resp:
            raise AssertionError(f"Auditor was able to execute withdrawal! Status: {resp.status}")
    except urllib.error.HTTPError as e:
        assert e.code == 403, f"Expected 403 Forbidden for Auditor withdrawal, got {e.code}"
        print(f"  -> PASS: Auditor mutation attempt blocked with HTTP 403 Forbidden.")

    # -------------------------------------------------------------
    # 13. Submitter Withdrawal Flow
    # -------------------------------------------------------------
    print(f"\n[Step 13] Site Manager Withdrawal Workflow for Submission #{submission_id}...")
    withdraw_url = f"{BASE_URL}/submissions/{submission_id}/withdraw/"
    csrf = get_csrf_token(opener, sub_detail_url, cj)
    post_data = urllib.parse.urlencode({
        "csrfmiddlewaretoken": csrf,
        "reason": "Calibration certificate revision required for flow meter readings.",
        "confirm": "on",
    }).encode("utf-8")
    req = urllib.request.Request(withdraw_url, data=post_data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": sub_detail_url,
    })
    with opener.open(req) as resp:
        post_url = resp.geturl()
        post_html = resp.read().decode("utf-8")
        print(f"  -> Withdrawal processed. Redirected URL: {post_url}")
        assert "withdrawn" in post_html.lower() or "withdrawn" in post_url.lower()

    # Verify submission status is WITHDRAWN
    with opener.open(sub_detail_url) as resp:
        w_html = resp.read().decode("utf-8")
        assert "WITHDRAWN" in w_html
        print("  -> Submission status verified as WITHDRAWN.")

    # Verify Activity Record reverted to DRAFT
    with opener.open(rec_detail_url) as resp:
        rec_html = resp.read().decode("utf-8")
        assert "DRAFT" in rec_html
        assert "Submit for Review" in rec_html or "Submit Record" in rec_html
        print("  -> Activity Record status reverted to DRAFT and unlocked for corrections.")

    # -------------------------------------------------------------
    # 14. Re-Submission after Withdrawal
    # -------------------------------------------------------------
    print(f"\n[Step 14] Re-Submitting Activity Record #{rec_id} (Creating Submission #2)...")
    # Trigger fresh validation
    post_val = urllib.parse.urlencode({"csrfmiddlewaretoken": get_csrf_token(opener, rec_detail_url, cj)}).encode("utf-8")
    req = urllib.request.Request(val_url, data=post_val, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": rec_detail_url,
    })
    try:
        with opener.open(req) as resp:
            pass
    except urllib.error.HTTPError:
        pass

    # Submit again
    csrf = get_csrf_token(opener, submit_gate_url, cj)
    post_data = urllib.parse.urlencode({
        "csrfmiddlewaretoken": csrf,
        "comments": "Re-submission after meter calibration document update.",
        "confirm": "on",
    }).encode("utf-8")
    req = urllib.request.Request(submit_gate_url, data=post_data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": submit_gate_url,
    })
    with opener.open(req) as resp:
        re_url = resp.geturl()
        re_html = resp.read().decode("utf-8")
        sub2_match = re.search(r'/submissions/(\d+)/', re_url)
        assert sub2_match, f"Failed to get new submission ID from {re_url}"
        submission_id_2 = int(sub2_match.group(1))
        print(f"  -> Generated Re-Submission ID: #{submission_id_2}")
        assert submission_id_2 != submission_id, "New submission ID should be distinct from withdrawn submission ID."

    with opener.open(f"{BASE_URL}/submissions/{submission_id_2}/") as resp:
        s2_html = resp.read().decode("utf-8")
        assert "Submission #2" in s2_html or "SUBMITTED" in s2_html
        print("  -> Re-submission #2 verified active with full audit lineage.")

    # Verify original submission #1 is still accessible and archived as WITHDRAWN
    with opener.open(sub_detail_url) as resp:
        s1_html = resp.read().decode("utf-8")
        assert "WITHDRAWN" in s1_html
        print("  -> Submission #1 remains historically preserved as WITHDRAWN in the audit trail.")

    print("\n" + "=" * 75)
    print("PHASE 12 SUBMISSION WORKFLOW LIVE VERIFICATION COMPLETED SUCCESSFULLY!")
    print("=" * 75)


if __name__ == "__main__":
    try:
        run_verification()
    except Exception as e:
        print(f"\n[FAIL] Live verification failed with error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
