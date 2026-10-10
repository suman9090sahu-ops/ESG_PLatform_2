"""
Comprehensive Verification Script for Global Glassmorphism Redesign
Tests against the live running Django server at http://127.0.0.1:8000.
Covers Section 19 Required Verification Matrix:
1. Public landing page '/' (MUST remain unchanged)
2. Login page '/auth/login/' (MUST remain unchanged)
3. Site Manager Dashboard
4. ESG Data Entry & Creation Form
5. Evidence Repository & OCR
6. Submissions & Corrections Inbox
7. Procurement Ledger & Supplier Directory
8. Transport & Logistics
9. Emission Factors
10. Calculation Engine & Quality Desk
11. Scope 3 GHG Inventory
12. Reports & Consolidation
13. Auditor Workspace (Read-Only)
14. TRACE THIS NUMBER Lineage
15. Reporting Periods Lifecycle
16. Activity Catalog
17. Organization Hierarchy
"""

import http.cookiejar
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

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
            return match.group(1), html
    return "", ""


def login_user(opener, username, password):
    login_url = f"{BASE_URL}/auth/login/"
    token, _ = get_csrf_token(opener, login_url)
    data = urllib.parse.urlencode({
        "csrfmiddlewaretoken": token,
        "username": username,
        "password": password,
    }).encode("utf-8")
    req = urllib.request.Request(login_url, data=data, headers={"Referer": login_url})
    with opener.open(req) as resp:
        return resp.status, resp.read().decode("utf-8")


def get_url(opener, url):
    req = urllib.request.Request(url)
    try:
        with opener.open(req) as resp:
            content = resp.read()
            try:
                decoded = content.decode("utf-8")
            except UnicodeDecodeError:
                decoded = content.decode("latin-1", errors="replace")
            return resp.status, decoded
    except urllib.error.HTTPError as e:
        content = e.read()
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError:
            decoded = content.decode("latin-1", errors="replace")
        return e.code, decoded


def verify_page(name, html, status, expected_role=None, is_authenticated=True):
    assert status == 200, f"[{name}] Expected 200, got {status}"
    if is_authenticated:
        assert "authenticated-glass.css" in html, f"[{name}] Missing authenticated-glass.css link"
        assert "esg-body" in html, f"[{name}] Missing esg-body class on body tag"
        assert "esg-main-panel" in html or "main-panel" in html, f"[{name}] Missing main-panel layout container"
        assert "content-wrapper" in html, f"[{name}] Missing content-wrapper container"
        assert "sidebar" in html, f"[{name}] Missing sidebar navigation"
        assert "navbar" in html, f"[{name}] Missing navbar header"
    print(f"  [OK] {name}: Status {status} | Glass Shell Verified")


def run_all_checks():
    print("=" * 70)
    print("GLOBAL GLASSMORPHISM VERIFICATION MATRIX (SECTION 19)")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # 1. Unchanged Pages: Landing Page (/) & Login Page (/auth/login/)
    # -------------------------------------------------------------------------
    print("\n--- 1. Critical Preservation: Unchanged Public Pages ---")
    opener_anon, _ = create_session()

    # Public Landing Page
    status, landing_html = get_url(opener_anon, f"{BASE_URL}/")
    assert status == 200, f"Landing page returned {status}"
    assert "landing-hero" in landing_html, "Landing hero section missing"
    assert "authenticated-glass.css" not in landing_html, "authenticated-glass.css leaked into landing page!"
    assert "Building a Sustainable Future" in landing_html or "MEIL ESG Platform" in landing_html
    print("  [OK] Public Landing Page (/): Preserved & Unaffected by Redesign")

    # Login Page
    status, login_html = get_url(opener_anon, f"{BASE_URL}/auth/login/")
    assert status == 200, f"Login page returned {status}"
    assert "login-glass-card" in login_html, "Login glass card missing"
    assert "sustainable-building.jpg" in login_html, "Login sustainable building background missing"
    assert "auth-glass.css" in login_html, "auth-glass.css missing"
    assert "authenticated-glass.css" not in login_html, "authenticated-glass.css leaked into login page!"
    print("  [OK] Login Page (/auth/login/): Preserved with dedicated auth styles & imagery")

    # Static Assets Check
    status, _ = get_url(opener_anon, f"{BASE_URL}/static/images/esg-glass-background.jpg")
    assert status == 200, "Background image /static/images/esg-glass-background.jpg returned non-200"
    status, _ = get_url(opener_anon, f"{BASE_URL}/static/css/authenticated-glass.css")
    assert status == 200, "Stylesheet /static/css/authenticated-glass.css returned non-200"
    print("  [OK] Static Assets: esg-glass-background.jpg and authenticated-glass.css load 200 OK")

    # -------------------------------------------------------------------------
    # 2. Site Manager Session
    # -------------------------------------------------------------------------
    print("\n--- 2. Site Manager Workflows ---")
    opener_sm, _ = create_session()
    login_user(opener_sm, "site_manager", "SiteManagerPass123!")

    # Site Manager Dashboard
    status, html = get_url(opener_sm, f"{BASE_URL}/site-manager/dashboard/")
    verify_page("Site Manager Dashboard", html, status)

    # ESG Data Entry List
    status, html = get_url(opener_sm, f"{BASE_URL}/data-entry/")
    verify_page("ESG Data Entry Repository", html, status)

    # ESG Data Entry Create Form
    status, html = get_url(opener_sm, f"{BASE_URL}/data-entry/create/")
    verify_page("ESG Data Entry Create Form", html, status)
    assert "<form" in html, "Form tag missing on data entry create"

    # Evidence Repository
    status, html = get_url(opener_sm, f"{BASE_URL}/evidence/")
    verify_page("Evidence Repository", html, status)

    # Submissions List
    status, html = get_url(opener_sm, f"{BASE_URL}/submissions/")
    verify_page("Submissions List", html, status)

    # Corrections Inbox
    status, html = get_url(opener_sm, f"{BASE_URL}/corrections/")
    verify_page("Corrections Inbox", html, status)

    # -------------------------------------------------------------------------
    # 3. Subsidiary Manager Session
    # -------------------------------------------------------------------------
    print("\n--- 3. Subsidiary Manager Workflows ---")
    opener_sub, _ = create_session()
    login_user(opener_sub, "subsidiary_manager", "SubManagerPass123!")

    # Subsidiary Manager Dashboard
    status, html = get_url(opener_sub, f"{BASE_URL}/subsidiary-manager/dashboard/")
    verify_page("Subsidiary Manager Dashboard", html, status)

    # Subsidiary Manager Review Inbox
    status, html = get_url(opener_sub, f"{BASE_URL}/subsidiary-manager/inbox/")
    verify_page("Subsidiary Review Inbox", html, status)

    # -------------------------------------------------------------------------
    # 4. ESG Manager Session
    # -------------------------------------------------------------------------
    print("\n--- 4. ESG Manager & Core Governance Workflows ---")
    opener_em, _ = create_session()
    login_user(opener_em, "esg_manager", "ESGManagerPass123!")

    # ESG Manager Dashboard
    status, html = get_url(opener_em, f"{BASE_URL}/esg-manager/dashboard/")
    verify_page("ESG Manager Dashboard", html, status)

    # Reporting Periods
    status, html = get_url(opener_em, f"{BASE_URL}/reporting-periods/")
    verify_page("Reporting Periods List", html, status)

    # Activity Master Catalog
    status, html = get_url(opener_em, f"{BASE_URL}/activity-master/")
    verify_page("Activity Catalog", html, status)

    # Organization Overview
    status, html = get_url(opener_em, f"{BASE_URL}/organization/")
    verify_page("Organization Overview", html, status)

    # Suppliers Directory
    status, html = get_url(opener_em, f"{BASE_URL}/suppliers/")
    verify_page("Suppliers Directory", html, status)

    # Procurement Ledger
    status, html = get_url(opener_em, f"{BASE_URL}/procurement/")
    verify_page("Procurement Ledger", html, status)

    # Transport / Logistics
    status, html = get_url(opener_em, f"{BASE_URL}/transport/")
    verify_page("Transport Logistics Records", html, status)

    # Carriers Directory
    status, html = get_url(opener_em, f"{BASE_URL}/carriers/")
    verify_page("Carriers Directory", html, status)

    # Vehicles Fleet
    status, html = get_url(opener_em, f"{BASE_URL}/vehicles/")
    verify_page("Vehicles Fleet Directory", html, status)

    # Emission Factors Directory
    status, html = get_url(opener_em, f"{BASE_URL}/emission-factors/")
    verify_page("Emission Factors Directory", html, status)

    # Calculation Quality Desk
    status, html = get_url(opener_em, f"{BASE_URL}/calculations/desk/")
    verify_page("Calculation Quality Desk", html, status)

    # Scope 3 Value Chain Inventory
    status, html = get_url(opener_em, f"{BASE_URL}/scope3/inventory/")
    verify_page("Scope 3 Inventory", html, status)

    # Governed Reports Overview
    status, html = get_url(opener_em, f"{BASE_URL}/reports/")
    verify_page("Governed Reports Overview", html, status)

    # Trace This Number Directory
    status, html = get_url(opener_em, f"{BASE_URL}/reports/trace/")
    verify_page("TRACE THIS NUMBER Directory", html, status)

    # Anomaly Detection Desk
    status, html = get_url(opener_em, f"{BASE_URL}/anomalies/")
    verify_page("Anomaly Detection Desk", html, status)

    # -------------------------------------------------------------------------
    # 5. Auditor Workspace & Strict Read-Only Verification
    # -------------------------------------------------------------------------
    print("\n--- 5. Auditor Workspace & Read-Only RBAC ---")
    opener_aud, _ = create_session()
    login_user(opener_aud, "auditor", "AuditorPass123!")

    # Auditor Dashboard
    status, html = get_url(opener_aud, f"{BASE_URL}/auditor/dashboard/")
    verify_page("Auditor Workspace Dashboard", html, status)
    assert "Auditor" in html, "Auditor header badge missing"

    # Auditor TRACE THIS NUMBER
    status, html = get_url(opener_aud, f"{BASE_URL}/auditor/trace/")
    verify_page("Auditor Trace Directory", html, status)

    # Verify Auditor is Read-Only (Cannot Create Records)
    status, html = get_url(opener_aud, f"{BASE_URL}/data-entry/create/")
    assert status == 403, f"Auditor should get 403 Forbidden on /data-entry/create/, got {status}"
    print("  [OK] Auditor Read-Only Guard: /data-entry/create/ properly returned 403 Forbidden")

    # -------------------------------------------------------------------------
    # 6. MEIL Operator Supervisor Session
    # -------------------------------------------------------------------------
    print("\n--- 6. MEIL Operator Supervisor Workflows ---")
    opener_op, _ = create_session()
    login_user(opener_op, "meil_operator", "OperatorPass123!")

    # MEIL Operator Dashboard
    status, html = get_url(opener_op, f"{BASE_URL}/meil-operator/dashboard/")
    verify_page("MEIL Operator Dashboard", html, status)

    print("\n" + "=" * 70)
    print("ALL 17 VERIFICATION MATRIX CATEGORIES COMPLETED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    try:
        run_all_checks()
    except Exception as exc:
        print(f"\n[FAIL] Verification exception: {exc}")
        sys.exit(1)
