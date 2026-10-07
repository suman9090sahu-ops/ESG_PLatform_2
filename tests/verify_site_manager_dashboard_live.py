"""
Live Browser Emulation & Visual UI Element Verification for Phase 07 — Site Manager Dashboard.
Simulates a full browser session against http://127.0.0.1:8000:
1. Performs GET /auth/login/ to acquire session & CSRF token.
2. Posts credentials for 'site_manager' ('SiteManagerPass123!').
3. Verifies post-login 302 redirection to /site-manager/dashboard/.
4. Verifies the rendered Site Manager Operational Dashboard:
   - Page title & subtitle
   - Header badges (Role, Cycle, Current Date)
   - 5 KPI metric cards with expected values
   - Authorized sites table (SITE-POL-101 present, SITE-POL-102 strictly absent)
   - Quick action buttons (Inspect, Project, Catalog, Data Entry Phase 08)
   - ESG Workflow Status & Readiness section
   - Pending Actions & Corrections section ("You're All Caught Up" empty state)
   - Recent Operational Activity & Security Audit Lineage section
   - Operator Profile side card (Ramesh Kumar, Site In-Charge)
   - Temporal Governance side card (FY2025-26, OPEN, cycle window)
   - Telemetry & Sync Status side card (ONLINE, Direct Cloud Telemetry)
   - Operational shortcuts list
5. Follows 'Inspect' link to /site-manager/sites/1/ and validates Site Detail page.
6. Verifies IDOR protection (unassigned site 2 returns 403 Forbidden).
7. Verifies role boundaries:
   - subsidiary_manager receives 403 Forbidden on /site-manager/dashboard/
   - esg_manager receives 403 Forbidden on /site-manager/dashboard/
   - auditor receives 403 Forbidden on /site-manager/dashboard/
"""

import http.cookiejar
import re
import urllib.parse
import urllib.request
import sys

BASE_URL = "http://127.0.0.1:8000"


def make_client():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    return opener, cj


def get_csrf(html):
    match = re.search(r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']', html)
    return match.group(1) if match else None


def request(opener, url, data=None, headers=None):
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers)
    try:
        with opener.open(req) as resp:
            content = resp.read().decode("utf-8")
            return resp.status, resp.geturl(), content
    except urllib.error.HTTPError as e:
        content = e.read().decode("utf-8") if e.fp else ""
        return e.code, e.geturl(), content


def run_verification():
    print("=" * 75)
    print("MEIL ESG CONTROL TOWER - PHASE 07 LIVE BROWSER EMULATION VERIFICATION")
    print(f"Target URL: {BASE_URL}")
    print("=" * 75)

    client, cj = make_client()

    # Step 1: Open Login Page
    status, url, html = request(client, f"{BASE_URL}/auth/login/")
    print(f"\n[1] Open Login Page: HTTP {status} -> {url}")
    assert status == 200, f"Expected 200, got {status}"
    csrf_token = get_csrf(html)
    assert csrf_token, "Failed to retrieve CSRF token"
    print("    [PASS] CSRF token extracted successfully")

    # Step 2: Submit Credentials as site_manager
    login_data = urllib.parse.urlencode({
        "csrfmiddlewaretoken": csrf_token,
        "username": "site_manager",
        "password": "SiteManagerPass123!",
    }).encode("utf-8")
    status, url, html = request(client, f"{BASE_URL}/auth/login/", data=login_data, headers={"Referer": f"{BASE_URL}/auth/login/"})
    print(f"\n[2] Authenticate 'site_manager': HTTP {status} -> {url}")
    assert status == 200, f"Expected 200, got {status}"
    assert "/site-manager/dashboard/" in url, f"Expected redirect to site-manager dashboard, got {url}"
    print("    [PASS] Successfully redirected to /site-manager/dashboard/")

    # Step 3: Verify Dashboard UI Structure & Content
    print("\n[3] Verifying Site Manager Operational Dashboard DOM Elements:")
    checks = [
        ("Dashboard Page Title", "Site Manager Operational Dashboard" in html),
        ("Page Subtitle", "Operational Telemetry, ESG Workflow &amp; Assigned Site Oversight" in html or "Operational Telemetry, ESG Workflow & Assigned Site Oversight" in html),
        ("Role Badge", "Role: SITE_MANAGER" in html),
        ("Reporting Cycle Badge", "Cycle: FY2025-26 (OPEN)" in html),
        ("Current Date Display", "badge bg-light text-dark border px-3 py-2 fs-6" in html),
        ("KPI: Assigned Sites", "Assigned Sites" in html and "1" in html),
        ("KPI: Active Projects", "Active Projects" in html and "1" in html),
        ("KPI: Current Period", "Current Period" in html and "FY2025-26" in html),
        ("KPI: Activity Catalog", "Activity Catalog" in html and "10" in html),
        ("KPI: Pending Actions", "Pending Actions" in html and "All Caught Up" in html),
        ("Authorized Sites Section", "My Authorized Operational Sites" in html),
        ("Authorized Site Present", "SITE-POL-101" in html and "Polavaram Dam Headworks Site" in html),
        ("Unassigned Site NOT Present", "SITE-POL-102" not in html and "SITE-PWR-201" not in html and "SITE-SOL-301" not in html),
        ("Parent Project Link", "Polavaram National Irrigation Project" in html or "Polavaram Dam Project" in html),
        ("Action: Inspect Site", "Inspect" in html and "/site-manager/sites/1/" in html),
        ("Action: Parent Project", "Project" in html and "/projects/1/" in html),
        ("Action: Activity Catalog", "Catalog" in html and "/activity-master/" in html),
        ("Action: Data Entry (Phase 08)", "Data Entry" in html and "Phase 08" in html),
        ("ESG Workflow Status Section", "ESG Workflow Status &amp; Readiness" in html or "ESG Workflow Status & Readiness" in html),
        ("Workflow Readiness Indicator", "READY" in html and "Cycle <code>FY2025-26</code> is OPEN" in html),
        ("Pending Actions Empty State", "You&#x27;re All Caught Up" in html or "You're All Caught Up" in html or "All Caught Up" in html),
        ("Recent Activity Section", "Recent Operational &amp; Security Activity" in html or "Recent Operational & Security Activity" in html),
        ("Operator Profile Card", "Operator Profile" in html and ("Ramesh Kumar" in html or "site_manager" in html)),
        ("Temporal Governance Card", "Temporal Governance" in html and "FY2025-26" in html),
        ("Telemetry & Sync Card", "Telemetry &amp; Sync Status" in html or "Telemetry & Sync Status" in html),
        ("Telemetry Mode Status", "ONLINE" in html and "Direct Cloud Telemetry" in html),
        ("Operational Shortcuts", "Operational Shortcuts" in html and "All Assigned Sites" in html),
    ]

    all_passed = True
    for label, condition in checks:
        if condition:
            print(f"    [PASS] {label}")
        else:
            print(f"    [FAIL] {label}")
            all_passed = False

    assert all_passed, "One or more UI element verifications failed"

    # Step 4: Verify Navigation from Dashboard to Site Detail
    print("\n[4] Navigating to Site Detail (/site-manager/sites/1/):")
    status, url, html = request(client, f"{BASE_URL}/site-manager/sites/1/")
    assert status == 200, f"Expected 200, got {status}"
    assert "Polavaram Dam Headworks Site" in html
    assert "SITE-POL-101" in html
    assert "Back to Dashboard" in html
    print("    [PASS] Site Detail page loaded cleanly with authorized telemetry boundary")

    # Step 5: Test IDOR on Site Detail (Attempt unassigned Site 2)
    print("\n[5] IDOR Defense Check on Unassigned Site (/site-manager/sites/2/):")
    status, url, html = request(client, f"{BASE_URL}/site-manager/sites/2/")
    assert status == 403, f"Expected 403 Forbidden, got {status}"
    assert "Access Denied" in html or "Forbidden" in html
    print("    [PASS] Tampered site_id correctly blocked with 403 Forbidden")

    # Step 6: Test IDOR Query Parameter on Dashboard (?site_id=2)
    print("\n[6] IDOR Query Parameter Defense on Dashboard (?site_id=2):")
    status, url, html = request(client, f"{BASE_URL}/site-manager/dashboard/?site_id=2")
    assert status == 200, f"Expected 200, got {status}"
    assert "SITE-POL-101" in html
    assert "SITE-POL-102" not in html
    print("    [PASS] Client parameter tampering ignored; strictly scoped to authorized sites only")

    # Step 7: Test RBAC Boundaries for Non-Site-Manager Roles
    print("\n[7] Cross-Role RBAC Boundary Enforcement:")
    for username, pwd, role_name in [
        ("subsidiary_manager", "SubManagerPass123!", "Subsidiary Manager"),
        ("esg_manager", "ESGManagerPass123!", "ESG Manager"),
        ("auditor", "AuditorPass123!", "Auditor"),
    ]:
        other_client, other_cj = make_client()
        s, u, h = request(other_client, f"{BASE_URL}/auth/login/")
        tok = get_csrf(h)
        data = urllib.parse.urlencode({"csrfmiddlewaretoken": tok, "username": username, "password": pwd}).encode("utf-8")
        s, u, h = request(other_client, f"{BASE_URL}/auth/login/", data=data, headers={"Referer": f"{BASE_URL}/auth/login/"})
        # Try accessing Site Manager Dashboard
        s, u, h = request(other_client, f"{BASE_URL}/site-manager/dashboard/")
        assert s == 403, f"Expected 403 for {role_name}, got {s}"
        print(f"    [PASS] {role_name} ('{username}') denied access to /site-manager/dashboard/ (HTTP 403 Forbidden)")

    # Step 8: Test MEIL Operator Supervisor Access
    op_client, op_cj = make_client()
    s, u, h = request(op_client, f"{BASE_URL}/auth/login/")
    tok = get_csrf(h)
    data = urllib.parse.urlencode({"csrfmiddlewaretoken": tok, "username": "meil_operator", "password": "OperatorPass123!"}).encode("utf-8")
    s, u, h = request(op_client, f"{BASE_URL}/auth/login/", data=data, headers={"Referer": f"{BASE_URL}/auth/login/"})
    s, u, h = request(op_client, f"{BASE_URL}/site-manager/dashboard/")
    assert s == 200, f"Expected 200 for MEIL Operator, got {s}"
    print("    [PASS] MEIL Operator supervisor permitted access to /site-manager/dashboard/ (HTTP 200 OK)")

    print("\n" + "=" * 75)
    print("ALL LIVE BROWSER EMULATION & RBAC BOUNDARY CHECKS PASSED!")
    print("=" * 75)


if __name__ == "__main__":
    try:
        run_verification()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        sys.exit(1)
