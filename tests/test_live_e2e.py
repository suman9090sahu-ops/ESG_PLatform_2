"""
Live End-to-End HTTP Verification against the running Django dev server (http://127.0.0.1:8000).
Tests:
1. Health probe
2. Login as meil_operator
3. Access /organization/ overview, verify HTML content
4. Access /organization/companies/ and /organization/companies/1/
5. Access /organization/subsidiaries/ and /organization/subsidiaries/1/
6. Access /organization/projects/ and /organization/projects/1/
7. Access /organization/sites/ and /organization/sites/1/
8. Login as subsidiary_manager
9. Access assigned subsidiary /organization/subsidiaries/1/ -> 200
10. IDOR test: Access unassigned subsidiary /organization/subsidiaries/2/ -> 403 Forbidden!
11. Login as site_manager
12. Attempt to access /organization/ -> 403 Forbidden!
13. Access assigned site /organization/sites/1/ -> 200
14. IDOR test: Access unassigned site /organization/sites/2/ -> 403 Forbidden!
"""

import re
import urllib.parse
import urllib.request
import http.cookiejar

BASE_URL = "http://127.0.0.1:8000"

def create_session():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    return opener, cj

def get_csrf_token(opener, url):
    req = urllib.request.Request(url)
    with opener.open(req) as resp:
        html = resp.read().decode("utf-8")
        match = re.search(r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']', html)
        if match:
            return match.group(1)
    return ""

def login_user(opener, username, password):
    login_url = f"{BASE_URL}/auth/login/"
    token = get_csrf_token(opener, login_url)
    data = urllib.parse.urlencode({
        "csrfmiddlewaretoken": token,
        "username": username,
        "password": password,
    }).encode("utf-8")
    req = urllib.request.Request(login_url, data=data, headers={"Referer": login_url})
    try:
        resp = opener.open(req)
        return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")

def get_url(opener, url):
    req = urllib.request.Request(url)
    try:
        with opener.open(req) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")

def run():
    print("Starting Live E2E HTTP Verification...")

    # 1. Health
    opener, _ = create_session()
    code, body = get_url(opener, f"{BASE_URL}/health/")
    print(f"[1] Health Check: Status {code} (Expected 200)")
    assert code == 200, f"Health check failed with {code}"

    # 2. MEIL Operator Flow
    opener_op, _ = create_session()
    code, _ = login_user(opener_op, "meil_operator", "OperatorPass123!")
    print(f"[2] Login meil_operator: Status {code} (Expected 200)")

    # 3. Overview
    code, html = get_url(opener_op, f"{BASE_URL}/organization/")
    print(f"[3] /organization/ Overview: Status {code} (Expected 200)")
    assert code == 200
    assert "Organizational Hierarchy Tree" in html
    assert "MEIL-HYDRO" in html
    assert "MEIL-SOLAR" in html

    # 4. Companies
    code, html = get_url(opener_op, f"{BASE_URL}/organization/companies/")
    print(f"[4] /organization/companies/: Status {code} (Expected 200)")
    assert code == 200
    assert "MEIL Enterprise Group" in html

    code, html = get_url(opener_op, f"{BASE_URL}/organization/companies/1/")
    print(f"[5] /organization/companies/1/: Status {code} (Expected 200)")
    assert code == 200
    assert "Corporate Entity Profile" in html

    # 5. Subsidiaries
    code, html = get_url(opener_op, f"{BASE_URL}/organization/subsidiaries/")
    print(f"[6] /organization/subsidiaries/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_op, f"{BASE_URL}/organization/subsidiaries/1/")
    print(f"[7] /organization/subsidiaries/1/: Status {code} (Expected 200)")
    assert code == 200
    assert "Division Specification" in html

    # 6. Projects
    code, html = get_url(opener_op, f"{BASE_URL}/organization/projects/")
    print(f"[8] /organization/projects/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_op, f"{BASE_URL}/organization/projects/1/")
    print(f"[9] /organization/projects/1/: Status {code} (Expected 200)")
    assert code == 200
    assert "Infrastructure Project Metadata" in html

    # 7. Sites
    code, html = get_url(opener_op, f"{BASE_URL}/organization/sites/")
    print(f"[10] /organization/sites/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_op, f"{BASE_URL}/organization/sites/1/")
    print(f"[11] /organization/sites/1/: Status {code} (Expected 200)")
    assert code == 200
    assert "Operational Boundary Specification" in html

    # 8. Subsidiary Manager Flow
    opener_sub, _ = create_session()
    code, _ = login_user(opener_sub, "subsidiary_manager", "SubManagerPass123!")
    print(f"[12] Login subsidiary_manager: Status {code} (Expected 200)")

    # Access assigned Hydro: 200
    code, html = get_url(opener_sub, f"{BASE_URL}/organization/subsidiaries/1/")
    print(f"[13] subsidiary_manager accesses Hydro Division (/organization/subsidiaries/1/): Status {code} (Expected 200)")
    assert code == 200

    # IDOR attempt: access unassigned Solar Division (ID 2): 403 Forbidden
    code, html = get_url(opener_sub, f"{BASE_URL}/organization/subsidiaries/2/")
    print(f"[14] IDOR attempt: subsidiary_manager accesses unassigned Solar Division (/organization/subsidiaries/2/): Status {code} (Expected 403)")
    assert code == 403, f"Expected 403, got {code}"
    assert "Access Denied" in html or "Forbidden" in html

    # 9. Site Manager Flow
    opener_sm, _ = create_session()
    code, _ = login_user(opener_sm, "site_manager", "SiteManagerPass123!")
    print(f"[15] Login site_manager: Status {code} (Expected 200)")

    # Site manager attempts /organization/ overview: 403 Forbidden
    code, html = get_url(opener_sm, f"{BASE_URL}/organization/")
    print(f"[16] site_manager attempts /organization/ overview: Status {code} (Expected 403)")
    assert code == 403, f"Expected 403, got {code}"
    assert "Access Denied" in html or "Forbidden" in html

    # Site manager accesses assigned Site 1: 200
    code, html = get_url(opener_sm, f"{BASE_URL}/organization/sites/1/")
    print(f"[17] site_manager accesses assigned Site 1 (/organization/sites/1/): Status {code} (Expected 200)")
    assert code == 200

    # IDOR attempt: Site manager tampers URL to unassigned Site 2: 403 Forbidden
    code, html = get_url(opener_sm, f"{BASE_URL}/organization/sites/2/")
    print(f"[18] IDOR attempt: site_manager tampers URL to unassigned Site 2 (/organization/sites/2/): Status {code} (Expected 403)")
    assert code == 403, f"Expected 403, got {code}"
    assert "Access Denied" in html or "Forbidden" in html

    # -------------------------------------------------------------------------
    # PHASE 04: REPORTING PERIODS & TEMPORAL GOVERNANCE LIVE E2E
    # -------------------------------------------------------------------------
    # 10. MEIL Operator Reporting Period Flow
    code, html = get_url(opener_op, f"{BASE_URL}/reporting-periods/")
    print(f"[19] /reporting-periods/ List: Status {code} (Expected 200)")
    assert code == 200
    assert "Authorized Reporting Cycles" in html
    assert "FY2025-26" in html
    assert "FY2024-25" in html

    code, html = get_url(opener_op, f"{BASE_URL}/reporting-periods/2/")
    print(f"[20] /reporting-periods/2/ Detail (FY2025-26): Status {code} (Expected 200)")
    assert code == 200
    assert "Temporal Boundary" in html
    assert "OPEN" in html

    code, html = get_url(opener_op, f"{BASE_URL}/reporting-periods/create/")
    print(f"[21] /reporting-periods/create/ GET: Status {code} (Expected 200)")
    assert code == 200
    assert "Configure New Reporting Period" in html

    # 11. ESG Manager Flow
    opener_esg, _ = create_session()
    code, _ = login_user(opener_esg, "esg_manager", "ESGManagerPass123!")
    print(f"[22] Login esg_manager: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_esg, f"{BASE_URL}/reporting-periods/")
    print(f"[23] esg_manager accesses /reporting-periods/: Status {code} (Expected 200)")
    assert code == 200
    assert "FY2025-26" in html

    code, html = get_url(opener_esg, f"{BASE_URL}/reporting-periods/create/")
    print(f"[24] esg_manager accesses /reporting-periods/create/: Status {code} (Expected 200)")
    assert code == 200

    # 12. Auditor Flow (Read-only)
    opener_aud, _ = create_session()
    code, _ = login_user(opener_aud, "auditor", "AuditorPass123!")
    print(f"[25] Login auditor: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_aud, f"{BASE_URL}/reporting-periods/")
    print(f"[26] auditor accesses /reporting-periods/: Status {code} (Expected 200)")
    assert code == 200
    assert "FY2025-26" in html

    code, html = get_url(opener_aud, f"{BASE_URL}/reporting-periods/2/")
    print(f"[27] auditor accesses /reporting-periods/2/ Detail: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_aud, f"{BASE_URL}/reporting-periods/create/")
    print(f"[28] auditor attempts /reporting-periods/create/ -> Status {code} (Expected 403)")
    assert code == 403, f"Expected 403, got {code}"
    assert "Access Denied" in html or "Forbidden" in html

    code, html = get_url(opener_aud, f"{BASE_URL}/reporting-periods/2/edit/")
    print(f"[29] auditor attempts /reporting-periods/2/edit/ -> Status {code} (Expected 403)")
    assert code == 403, f"Expected 403, got {code}"
    assert "Access Denied" in html or "Forbidden" in html

    # 13. Site Manager Flow (Read assigned periods, mutate denied)
    code, html = get_url(opener_sm, f"{BASE_URL}/reporting-periods/")
    print(f"[30] site_manager accesses /reporting-periods/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_sm, f"{BASE_URL}/reporting-periods/create/")
    print(f"[31] site_manager attempts /reporting-periods/create/ -> Status {code} (Expected 403)")
    assert code == 403, f"Expected 403, got {code}"
    assert "Access Denied" in html or "Forbidden" in html

    code, html = get_url(opener_sm, f"{BASE_URL}/reporting-periods/2/edit/")
    print(f"[32] site_manager attempts /reporting-periods/2/edit/ -> Status {code} (Expected 403)")
    assert code == 403, f"Expected 403, got {code}"
    assert "Access Denied" in html or "Forbidden" in html

    # -------------------------------------------------------------------------
    # PHASE 05: PROJECTS & SITES DIRECT ROUTES & RBAC VERIFICATION
    # -------------------------------------------------------------------------
    # 14. MEIL Operator direct routes
    code, html = get_url(opener_op, f"{BASE_URL}/projects/")
    print(f"[33] /projects/ Direct List: Status {code} (Expected 200)")
    assert code == 200
    assert "Infrastructure Projects" in html

    code, html = get_url(opener_op, f"{BASE_URL}/projects/1/")
    print(f"[34] /projects/1/ Direct Detail: Status {code} (Expected 200)")
    assert code == 200
    assert "Polavaram Hydro Project" in html or "Infrastructure Project" in html

    code, html = get_url(opener_op, f"{BASE_URL}/sites/")
    print(f"[35] /sites/ Direct List: Status {code} (Expected 200)")
    assert code == 200
    assert "Operational Sites" in html

    code, html = get_url(opener_op, f"{BASE_URL}/sites/1/")
    print(f"[36] /sites/1/ Direct Detail: Status {code} (Expected 200)")
    assert code == 200
    assert "Operational Boundary Specification" in html

    # 15. Auditor direct routes (Read-only 200, mutation 403)
    code, html = get_url(opener_aud, f"{BASE_URL}/projects/")
    print(f"[37] auditor accesses /projects/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_aud, f"{BASE_URL}/projects/1/")
    print(f"[38] auditor accesses /projects/1/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_aud, f"{BASE_URL}/projects/create/")
    print(f"[39] auditor attempts /projects/create/ -> Status {code} (Expected 403)")
    assert code == 403, f"Expected 403, got {code}"

    code, html = get_url(opener_aud, f"{BASE_URL}/sites/")
    print(f"[40] auditor accesses /sites/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_aud, f"{BASE_URL}/sites/create/")
    print(f"[41] auditor attempts /sites/create/ -> Status {code} (Expected 403)")
    assert code == 403, f"Expected 403, got {code}"

    # 16. Site Manager direct routes & IDOR isolation
    code, html = get_url(opener_sm, f"{BASE_URL}/projects/")
    print(f"[42] site_manager accesses /projects/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_sm, f"{BASE_URL}/projects/1/")
    print(f"[43] site_manager accesses assigned /projects/1/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_sm, f"{BASE_URL}/projects/2/")
    print(f"[44] IDOR attempt: site_manager accesses unassigned /projects/2/ -> Status {code} (Expected 403)")
    assert code == 403, f"Expected 403, got {code}"

    code, html = get_url(opener_sm, f"{BASE_URL}/sites/")
    print(f"[45] site_manager accesses /sites/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_sm, f"{BASE_URL}/sites/1/")
    print(f"[46] site_manager accesses assigned /sites/1/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_sm, f"{BASE_URL}/sites/2/")
    print(f"[47] IDOR attempt: site_manager accesses unassigned /sites/2/ -> Status {code} (Expected 403)")
    assert code == 403, f"Expected 403, got {code}"

    # 17. Phase 06 Activity Master Catalog & RBAC Live Verification
    code, html = get_url(opener_op, f"{BASE_URL}/activity-master/")
    print(f"[48] meil_operator accesses /activity-master/: Status {code} (Expected 200)")
    assert code == 200
    assert "Authoritative ESG Activity Master Catalog" in html
    assert "FUEL-DIESEL" in html

    code, html = get_url(opener_op, f"{BASE_URL}/activity-master/1/")
    print(f"[49] meil_operator accesses /activity-master/1/: Status {code} (Expected 200)")
    assert code == 200
    assert "Activity Specification" in html

    code, html = get_url(opener_op, f"{BASE_URL}/activity-master/create/")
    print(f"[50] meil_operator accesses /activity-master/create/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_op, f"{BASE_URL}/activity-master/categories/")
    print(f"[51] meil_operator accesses /activity-master/categories/: Status {code} (Expected 200)")
    assert code == 200
    assert "Governed ESG Categories" in html

    code, html = get_url(opener_op, f"{BASE_URL}/activity-master/units/")
    print(f"[52] meil_operator accesses /activity-master/units/: Status {code} (Expected 200)")
    assert code == 200
    assert "Standard Measurement Units" in html

    code, html = get_url(opener_esg, f"{BASE_URL}/activity-master/")
    print(f"[53] esg_manager accesses /activity-master/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_esg, f"{BASE_URL}/activity-master/create/")
    print(f"[54] esg_manager accesses /activity-master/create/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_esg, f"{BASE_URL}/activity-master/1/edit/")
    print(f"[55] esg_manager accesses /activity-master/1/edit/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_aud, f"{BASE_URL}/activity-master/")
    print(f"[56] auditor accesses /activity-master/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_aud, f"{BASE_URL}/activity-master/1/")
    print(f"[57] auditor accesses /activity-master/1/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_aud, f"{BASE_URL}/activity-master/create/")
    print(f"[58] auditor attempts /activity-master/create/ -> Status {code} (Expected 403)")
    assert code == 403, f"Expected 403, got {code}"

    code, html = get_url(opener_aud, f"{BASE_URL}/activity-master/1/edit/")
    print(f"[59] auditor attempts /activity-master/1/edit/ -> Status {code} (Expected 403)")
    assert code == 403, f"Expected 403, got {code}"

    code, html = get_url(opener_sm, f"{BASE_URL}/activity-master/")
    print(f"[60] site_manager accesses /activity-master/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_sm, f"{BASE_URL}/activity-master/1/")
    print(f"[61] site_manager accesses /activity-master/1/: Status {code} (Expected 200)")
    assert code == 200

    code, html = get_url(opener_sm, f"{BASE_URL}/activity-master/create/")
    print(f"[62] site_manager attempts /activity-master/create/ -> Status {code} (Expected 403)")
    assert code == 403, f"Expected 403, got {code}"

    code, html = get_url(opener_sm, f"{BASE_URL}/activity-master/1/edit/")
    print(f"[63] site_manager attempts /activity-master/1/edit/ -> Status {code} (Expected 403)")
    assert code == 403, f"Expected 403, got {code}"

    code, html = get_url(opener_sub, f"{BASE_URL}/activity-master/create/")
    print(f"[64] subsidiary_manager attempts /activity-master/create/ -> Status {code} (Expected 403)")
    assert code == 403, f"Expected 403, got {code}"

    # 15. Phase 07 — Site Manager Dashboard Verification
    # Site Manager accesses /site-manager/dashboard/
    code, html = get_url(opener_sm, f"{BASE_URL}/site-manager/dashboard/")
    print(f"[65] site_manager accesses /site-manager/dashboard/: Status {code} (Expected 200)")
    assert code == 200
    assert "Site Manager Operational Dashboard" in html
    assert "My Authorized Operational Sites" in html
    assert "SITE-POL-101" in html
    assert "SITE-POL-102" not in html, "Cross-site data leak detected: unassigned site present in site_manager view"

    # Site Manager accesses alias /dashboard/site-manager/
    code, html = get_url(opener_sm, f"{BASE_URL}/dashboard/site-manager/")
    print(f"[66] site_manager accesses /dashboard/site-manager/ alias: Status {code} (Expected 200/302)")
    assert code in (200, 302)

    # IDOR parameter tampering attempt (?site_id=2)
    code, html = get_url(opener_sm, f"{BASE_URL}/site-manager/dashboard/?site_id=2")
    print(f"[67] IDOR query param tampering on /site-manager/dashboard/?site_id=2: Status {code} (Expected 200 with no leak)")
    assert code == 200
    assert "SITE-POL-101" in html
    assert "SITE-POL-102" not in html

    # MEIL Operator (supervisor) accesses Site Manager dashboard
    code, html = get_url(opener_op, f"{BASE_URL}/site-manager/dashboard/")
    print(f"[68] meil_operator supervisor accesses /site-manager/dashboard/: Status {code} (Expected 200)")
    assert code == 200

    # Subsidiary Manager denied access to Site Manager dashboard
    code, html = get_url(opener_sub, f"{BASE_URL}/site-manager/dashboard/")
    print(f"[69] subsidiary_manager attempts /site-manager/dashboard/ -> Status {code} (Expected 403)")
    assert code == 403, f"Expected 403, got {code}"

    # ESG Manager denied access to Site Manager dashboard
    code, html = get_url(opener_esg, f"{BASE_URL}/site-manager/dashboard/")
    print(f"[70] esg_manager attempts /site-manager/dashboard/ -> Status {code} (Expected 403)")
    assert code == 403, f"Expected 403, got {code}"

    # 16. Phase 08 — ESG Data Entry Verification
    # A. site_manager accesses /data-entry/
    code, html = get_url(opener_sm, f"{BASE_URL}/data-entry/")
    print(f"[72] site_manager accesses /data-entry/: Status {code} (Expected 200)")
    assert code == 200
    assert "Activity Records" in html
    assert "SITE-POL-101" in html

    # B. site_manager accesses /data-entry/create/
    code, html = get_url(opener_sm, f"{BASE_URL}/data-entry/create/")
    print(f"[73] site_manager accesses /data-entry/create/: Status {code} (Expected 200)")
    assert code == 200
    assert "Log New ESG Activity Telemetry" in html
    assert "Polavaram Dam Headworks Site" in html
    assert "Polavaram Spillway & Powerhouse Site" not in html, "Unassigned site exposed in create dropdown"

    # C. AJAX API endpoint /data-entry/api/activity-units/?activity_id=1
    code, body = get_url(opener_sm, f"{BASE_URL}/data-entry/api/activity-units/?activity_id=1")
    print(f"[74] site_manager queries /data-entry/api/activity-units/?activity_id=1: Status {code} (Expected 200)")
    assert code == 200
    assert '"units":' in body

    # D. site_manager creates a new activity record as DRAFT
    create_url = f"{BASE_URL}/data-entry/create/"
    token = get_csrf_token(opener_sm, create_url)
    post_data = urllib.parse.urlencode({
        "csrfmiddlewaretoken": token,
        "site": "1",
        "reporting_period": "2",
        "activity": "1",
        "measurement_date": "2025-06-15",
        "quantity": "450.50",
        "unit": "1",
        "notes": "Live E2E test generator consumption",
        "status": "DRAFT",
    }).encode("utf-8")
    req = urllib.request.Request(create_url, data=post_data, headers={"Referer": create_url})
    resp = opener_sm.open(req)
    final_url = resp.geturl()
    body = resp.read().decode("utf-8")
    print(f"[75] site_manager creates draft ActivityRecord: Final URL {final_url}")
    assert "/data-entry/" in final_url
    assert "Draft saved" in body or "450.50" in body

    # Extract created record ID from response URL or body
    match = re.search(r'/data-entry/(\d+)/', final_url)
    if not match:
        match = re.search(r'/data-entry/(\d+)/', body)
    assert match, "Failed to identify created record ID"
    rec_id = match.group(1)
    print(f"Created ActivityRecord ID: {rec_id}")

    # E. site_manager views detail of created record
    code, html = get_url(opener_sm, f"{BASE_URL}/data-entry/{rec_id}/")
    print(f"[76] site_manager views /data-entry/{rec_id}/: Status {code} (Expected 200)")
    assert code == 200
    assert "450.50" in html
    assert "Litre" in html
    assert "Draft" in html
    assert "SITE-POL-101" in html

    # F. IDOR test: site_manager attempts to create record for unassigned site (site 2)
    token = get_csrf_token(opener_sm, create_url)
    post_data_idor = urllib.parse.urlencode({
        "csrfmiddlewaretoken": token,
        "site": "2",
        "reporting_period": "2",
        "activity": "1",
        "measurement_date": "2025-06-15",
        "quantity": "100.00",
        "unit": "1",
        "status": "DRAFT",
    }).encode("utf-8")
    req_idor = urllib.request.Request(create_url, data=post_data_idor, headers={"Referer": create_url})
    try:
        resp_idor = opener_sm.open(req_idor)
        idor_body = resp_idor.read().decode("utf-8")
        # Form validation should fail and re-render with validation error
        assert "Select a valid choice" in idor_body or "not authorized" in idor_body or resp_idor.status == 403
        print(f"[77] IDOR site tampering prevented on /data-entry/create/: Form validation rejected unauthorized site")
    except urllib.error.HTTPError as e:
        print(f"[77] IDOR site tampering rejected with HTTP {e.code}")
        assert e.code in (400, 403)

    # G. site_manager edits the created record
    edit_url = f"{BASE_URL}/data-entry/{rec_id}/edit/"
    token = get_csrf_token(opener_sm, edit_url)
    edit_data = urllib.parse.urlencode({
        "csrfmiddlewaretoken": token,
        "site": "1",
        "reporting_period": "2",
        "activity": "1",
        "measurement_date": "2025-06-16",
        "quantity": "520.00",
        "unit": "1",
        "notes": "Updated during live E2E test",
        "status": "READY",
    }).encode("utf-8")
    req_edit = urllib.request.Request(edit_url, data=edit_data, headers={"Referer": edit_url})
    resp_edit = opener_sm.open(req_edit)
    body_edit = resp_edit.read().decode("utf-8")
    print(f"[78] site_manager edits ActivityRecord to READY: Final URL {resp_edit.geturl()}")
    assert "520.00" in body_edit

    # H. Auditor views data ledger (read-only allowed)
    code, html = get_url(opener_aud, f"{BASE_URL}/data-entry/")
    print(f"[79] auditor accesses /data-entry/: Status {code} (Expected 200)")
    assert code == 200
    assert "Activity Records" in html

    # I. Auditor attempts to access /data-entry/create/ (forbidden)
    code, html = get_url(opener_aud, f"{BASE_URL}/data-entry/create/")
    print(f"[80] auditor attempts /data-entry/create/: Status {code} (Expected 403)")
    assert code == 403

    # J. Unauthenticated access to /data-entry/ redirects to login
    opener_anon, _ = create_session()
    code, html = get_url(opener_anon, f"{BASE_URL}/data-entry/")
    print(f"[81] anonymous user attempts /data-entry/: Status {code} (Expected 302/redirect to login)")
    assert code in (200, 302)  # urllib auto-follows 302 to /auth/login/ which returns 200
    assert "Login" in html or "Sign In" in html

    # =========================================================================
    # PHASE 09: EVIDENCE MANAGEMENT LIVE E2E VERIFICATION
    # =========================================================================
    print("\n--- Testing Phase 09 Evidence Management ---")

    # 1. Site Manager accesses /evidence/
    code, html = get_url(opener_sm, f"{BASE_URL}/evidence/")
    print(f"[82] site_manager accesses /evidence/: Status {code} (Expected 200)")
    assert code == 200
    assert "Audit Evidence Repository" in html
    assert "Total Documents" in html

    # 2. Site Manager accesses evidence upload form for created record
    upload_url = f"{BASE_URL}/data-entry/{rec_id}/evidence/upload/"
    code, html = get_url(opener_sm, upload_url)
    print(f"[83] site_manager accesses {upload_url}: Status {code} (Expected 200)")
    assert code == 200
    assert "Upload Supporting Document" in html

    # 3. Site Manager uploads PDF invoice
    csrf_up = get_csrf_token(opener_sm, upload_url)
    sample_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    boundary = "----WebKitFormBoundaryE2EEvidenceUpload"
    body_parts = bytearray()
    body_parts.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"csrfmiddlewaretoken\"\r\n\r\n{csrf_up}\r\n".encode("utf-8"))
    body_parts.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"evidence_type\"\r\n\r\nINVOICE\r\n".encode("utf-8"))
    body_parts.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"description\"\r\n\r\nLive E2E Verification Tax Invoice IOCL-001\r\n".encode("utf-8"))
    body_parts.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"iocl_invoice_001.pdf\"\r\nContent-Type: application/pdf\r\n\r\n".encode("utf-8"))
    body_parts.extend(sample_pdf)
    body_parts.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    req_up = urllib.request.Request(
        upload_url,
        data=bytes(body_parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Referer": upload_url},
    )
    resp_up = opener_sm.open(req_up)
    final_up_url = resp_up.geturl()
    body_up = resp_up.read().decode("utf-8")
    print(f"[84] site_manager uploads PDF evidence: Status {resp_up.status}, Final URL: {final_up_url}")
    assert resp_up.status == 200
    assert f"/data-entry/{rec_id}/" in final_up_url

    # 4. Check evidence table rendered on record detail
    code, html = get_url(opener_sm, f"{BASE_URL}/data-entry/{rec_id}/")
    assert code == 200
    assert "iocl_invoice_001.pdf" in html
    assert "Supporting Audit Evidence" in html
    print("[85] Evidence table on ActivityRecord detail displays uploaded file")

    # Extract created evidence ID
    ev_match = re.search(r'/evidence/(\d+)/', html)
    assert ev_match, "Failed to find created evidence ID in HTML"
    ev_id = ev_match.group(1)
    print(f"Created Evidence ID: #{ev_id}")

    # 5. Site Manager inspects evidence detail /evidence/<ev_id>/
    code, html = get_url(opener_sm, f"{BASE_URL}/evidence/{ev_id}/")
    print(f"[86] site_manager accesses /evidence/{ev_id}/: Status {code} (Expected 200)")
    assert code == 200
    assert "iocl_invoice_001.pdf" in html
    assert "Cryptographic SHA-256 Checksum" in html
    assert "ESG Operational Lineage Path" in html

    # 6. Site Manager downloads evidence binary
    req_dl = urllib.request.Request(f"{BASE_URL}/evidence/{ev_id}/download/")
    with opener_sm.open(req_dl) as resp_dl:
        code = resp_dl.status
        content_disp = resp_dl.headers.get("Content-Disposition", "")
        print(f"[87] site_manager downloads /evidence/{ev_id}/download/: Status {code} (Expected 200)")
        assert code == 200
        assert "attachment" in content_disp
        assert "iocl_invoice_001.pdf" in content_disp

    # 7. Site Manager previews evidence inline
    req_prev = urllib.request.Request(f"{BASE_URL}/evidence/{ev_id}/preview/")
    with opener_sm.open(req_prev) as resp_prev:
        code = resp_prev.status
        content_type = resp_prev.headers.get("Content-Type", "")
        print(f"[88] site_manager previews /evidence/{ev_id}/preview/: Status {code} (Expected 200)")
        assert code == 200
        assert content_type == "application/pdf"

    # 8. IDOR test: site_manager attempts upload against unassigned site's activity
    # Operator creates an activity record on Site 2 (unassigned to site_manager)
    token_op = get_csrf_token(opener_op, create_url)
    post_data_op = urllib.parse.urlencode({
        "csrfmiddlewaretoken": token_op,
        "site": "2",
        "reporting_period": "2",
        "activity": "1",
        "measurement_date": "2025-06-15",
        "quantity": "888.00",
        "unit": "1",
        "notes": "Record on unassigned site 2 for IDOR test",
        "status": "DRAFT",
    }).encode("utf-8")
    req_op_rec = urllib.request.Request(create_url, data=post_data_op, headers={"Referer": create_url})
    resp_op_rec = opener_op.open(req_op_rec)
    final_op_url = resp_op_rec.geturl()
    body_op_rec = resp_op_rec.read().decode("utf-8")
    match_op = re.search(r'/data-entry/(\d+)/', final_op_url)
    if not match_op:
        match_op = re.search(r'/data-entry/(\d+)/', body_op_rec)
    assert match_op, "Failed to identify created foreign record ID"
    foreign_rec_id = match_op.group(1)

    code, html = get_url(opener_sm, f"{BASE_URL}/data-entry/{foreign_rec_id}/evidence/upload/")
    print(f"[89] IDOR attempt: site_manager uploads to unassigned record /data-entry/{foreign_rec_id}/evidence/upload/: Status {code} (Expected 403)")
    assert code == 403

    # 9. Auditor accesses /evidence/ (200 OK)
    code, html = get_url(opener_aud, f"{BASE_URL}/evidence/")
    print(f"[90] auditor accesses /evidence/: Status {code} (Expected 200)")
    assert code == 200
    assert "iocl_invoice_001.pdf" in html

    # 10. Auditor downloads evidence (200 OK)
    req_aud_dl = urllib.request.Request(f"{BASE_URL}/evidence/{ev_id}/download/")
    with opener_aud.open(req_aud_dl) as resp_aud_dl:
        code = resp_aud_dl.status
        print(f"[91] auditor downloads /evidence/{ev_id}/download/: Status {code} (Expected 200)")
        assert code == 200

    # 11. Auditor attempts upload -> 403 Forbidden
    code, html = get_url(opener_aud, f"{BASE_URL}/data-entry/{rec_id}/evidence/upload/")
    print(f"[92] auditor attempts /data-entry/{rec_id}/evidence/upload/: Status {code} (Expected 403)")
    assert code == 403

    # 12. Unauthenticated access to /evidence/ redirects to login
    code, html = get_url(opener_anon, f"{BASE_URL}/evidence/")
    print(f"[93] anonymous user attempts /evidence/: Status {code} (Expected 200/302)")
    assert code in (200, 302)
    assert "Login" in html or "Sign In" in html

    # 13. Site Manager retires evidence with justification
    retire_url = f"{BASE_URL}/evidence/{ev_id}/retire/"
    csrf_ret = get_csrf_token(opener_sm, retire_url)
    ret_data = urllib.parse.urlencode({
        "csrfmiddlewaretoken": csrf_ret,
        "reason": "Superseded during master live E2E test verification run",
    }).encode("utf-8")
    req_ret = urllib.request.Request(retire_url, data=ret_data, headers={"Referer": retire_url})
    resp_ret = opener_sm.open(req_ret)
    body_ret = resp_ret.read().decode("utf-8")
    print(f"[94] site_manager retires evidence: Final URL {resp_ret.geturl()}")
    assert f"/evidence/{ev_id}/" in resp_ret.geturl()
    assert "Retired" in body_ret or "Superseded" in body_ret

    print("\nALL 94 LIVE E2E HTTP VERIFICATIONS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run()


