"""
Live HTTP and Integration Verification Script for Redesigned Login Page.
Executes against the running Django development server at http://127.0.0.1:8000.
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


def test_login_page_elements():
    print("[1] Testing GET /auth/login/ structure & glassmorphism elements...")
    opener, _ = create_session()
    token, html = get_csrf_token(opener, f"{BASE_URL}/auth/login/")
    assert token, "CSRF middleware token not found on login page"

    # Core glassmorphism classes & imagery
    assert "login-glass-card" in html, "Missing .login-glass-card CSS class"
    assert "auth-page-wrapper" in html, "Missing .auth-page-wrapper CSS class"
    assert "sustainable-building.jpg" in html, "Missing sustainable-building.jpg reference"
    assert "auth-glass.css" in html, "Missing auth-glass.css reference"

    # Branding & Header
    assert "ESG CONTROL TOWER" in html, "Missing 'ESG CONTROL TOWER' brand text"
    assert "Environmental &bull; Social &bull; Governance" in html or "Environmental • Social • Governance" in html, "Missing subtitle"
    assert "MEIL" in html, "Missing MEIL badge"

    # Form headings & fields
    assert "Welcome Back" in html, "Missing 'Welcome Back' heading"
    assert "Sign in to continue to your ESG workspace." in html, "Missing supporting text"
    assert "Username / Enterprise ID" in html, "Missing Username / Enterprise ID label"
    assert "Password" in html, "Missing Password label"
    assert "togglePasswordBtn" in html, "Missing password visibility toggle button"
    assert "Remember this session for 8 hours" in html, "Missing Remember Me checkbox label"
    assert "Sign In to ESG Platform" in html, "Missing 'Sign In to ESG Platform' button text"
    assert 'id="loginSubmitBtn"' in html, "Missing id='loginSubmitBtn'"

    # Links & Taglines
    assert "Forgot password?" in html, "Missing Forgot password link"
    assert "Request Access" in html, "Missing Request Access modal trigger"
    assert "accessRequestModal" in html, "Missing accessRequestModal element"
    assert "Building a more sustainable tomorrow." in html, "Missing sustainability tagline"
    assert "Return to Public Sustainability Portal" in html, "Missing Return to Public Sustainability Portal link"

    # Dev credentials box & roles
    assert "RBAC Test Accounts &amp; Quick Credentials" in html or "RBAC Test Accounts & Quick Credentials" in html, "Missing test accounts accordion"
    assert "site_manager" in html, "Missing site_manager test role"
    assert "subsidiary_manager" in html, "Missing subsidiary_manager test role"
    assert "esg_manager" in html, "Missing esg_manager test role"
    assert "auditor" in html, "Missing auditor test role"
    assert "meil_operator" in html, "Missing meil_operator test role"

    print("    -> PASS: Login page markup, glassmorphism card, branding, and dev credentials verified.")


def test_static_assets():
    print("[2] Testing static assets HTTP status...")
    opener, _ = create_session()

    # Sustainable building image
    img_url = f"{BASE_URL}/static/images/auth/sustainable-building.jpg"
    req = urllib.request.Request(img_url)
    with opener.open(req) as resp:
        assert resp.status == 200, f"Image returned status {resp.status}"
        length = int(resp.headers.get("Content-Length", 0))
        assert length > 100000, f"Image length too small: {length}"
        print(f"    -> PASS: sustainable-building.jpg returned 200 OK ({length} bytes).")

    # Auth glass stylesheet
    css_url = f"{BASE_URL}/static/css/auth-glass.css"
    req = urllib.request.Request(css_url)
    with opener.open(req) as resp:
        assert resp.status == 200, f"CSS returned status {resp.status}"
        css_text = resp.read().decode("utf-8")
        assert ".login-glass-card" in css_text, "CSS missing .login-glass-card"
        assert "backdrop-filter" in css_text, "CSS missing backdrop-filter"
        print("    -> PASS: auth-glass.css returned 200 OK with glassmorphism tokens.")


def test_invalid_login_flow():
    print("[3] Testing invalid credentials handling...")
    opener, _ = create_session()
    login_url = f"{BASE_URL}/auth/login/"
    token, _ = get_csrf_token(opener, login_url)

    data = urllib.parse.urlencode({
        "csrfmiddlewaretoken": token,
        "username": "non_existent_user",
        "password": "BadPassword123!",
    }).encode("utf-8")

    req = urllib.request.Request(login_url, data=data, headers={"Referer": login_url})
    with opener.open(req) as resp:
        assert resp.status == 200, f"Expected 200 on form error, got {resp.status}"
        html = resp.read().decode("utf-8")
        assert "Invalid credentials" in html, "Error message 'Invalid credentials' not displayed"
        assert "glass-alert-danger" in html or "alert-danger" in html, "Danger alert class not displayed"
        print("    -> PASS: Failed authentication displays styled error alert.")


def test_valid_login_and_logout_message():
    print("[4] Testing successful login & logout message banner...")
    opener, _ = create_session()
    login_url = f"{BASE_URL}/auth/login/"
    token, _ = get_csrf_token(opener, login_url)

    # Class to track redirect
    class RedirectTracker(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            self.last_redirect = newurl
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    tracker = RedirectTracker()
    opener.add_handler(tracker)

    data = urllib.parse.urlencode({
        "csrfmiddlewaretoken": token,
        "username": "site_manager",
        "password": "SiteManagerPass123!",
    }).encode("utf-8")

    req = urllib.request.Request(login_url, data=data, headers={"Referer": login_url})
    with opener.open(req) as resp:
        assert resp.status == 200, f"Expected successful load after redirect, got {resp.status}"
        final_url = resp.geturl()
        assert "/site-manager/" in final_url or "/dashboard/" in final_url, f"Unexpected post-login destination: {final_url}"
        print(f"    -> PASS: site_manager successfully logged in and redirected to {final_url}.")

    # Logout and check logout message on login page
    logout_url = f"{BASE_URL}/auth/logout/"
    req = urllib.request.Request(logout_url)
    with opener.open(req) as resp:
        assert resp.status == 200, f"Expected 200 after logout redirect, got {resp.status}"
        html = resp.read().decode("utf-8")
        assert "You have been securely signed out of MEIL ESG Control Tower." in html, "Logout confirmation message missing"
        assert "glass-alert-info" in html or "alert-info" in html or "glass-alert" in html, "Logout message styling missing"
        print("    -> PASS: User logged out; login page rendered confirmation message.")


def test_rbac_roles_deterministic_redirects():
    print("[5] Testing RBAC deterministic role routing...")
    roles_and_expected = [
        ("site_manager", "SiteManagerPass123!", "/site-manager/dashboard/"),
        ("subsidiary_manager", "SubManagerPass123!", "/subsidiary-manager/dashboard/"),
        ("esg_manager", "ESGManagerPass123!", "/esg-manager/dashboard/"),
        ("auditor", "AuditorPass123!", "/auditor/dashboard/"),
        ("meil_operator", "OperatorPass123!", "/meil-operator/dashboard/"),
    ]

    for user, pwd, expected_dest in roles_and_expected:
        opener, _ = create_session()
        login_url = f"{BASE_URL}/auth/login/"
        token, _ = get_csrf_token(opener, login_url)
        data = urllib.parse.urlencode({
            "csrfmiddlewaretoken": token,
            "username": user,
            "password": pwd,
        }).encode("utf-8")
        req = urllib.request.Request(login_url, data=data, headers={"Referer": login_url})
        with opener.open(req) as resp:
            final_url = resp.geturl()
            assert expected_dest in final_url, f"User {user} expected {expected_dest}, got {final_url}"
            print(f"    -> PASS: Role '{user}' routes to '{expected_dest}'.")


if __name__ == "__main__":
    try:
        test_login_page_elements()
        test_static_assets()
        test_invalid_login_flow()
        test_valid_login_and_logout_message()
        test_rbac_roles_deterministic_redirects()
        print("\n=== ALL REDESIGNED LOGIN VERIFICATION CHECKS PASSED ===")
    except Exception as exc:
        print(f"\n[FAIL] Verification error: {exc}")
        sys.exit(1)
