"""
Live HTTP Verification Script for Public Sustainability Landing Page.
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


def test_public_homepage():
    opener, _ = create_session()
    print("[1] Testing Public Homepage GET / ...")
    req = urllib.request.Request(f"{BASE_URL}/")
    with opener.open(req) as resp:
        status = resp.status
        html = resp.read().decode("utf-8")
        assert status == 200, f"Expected 200, got {status}"
        assert "Building a" in html and "Sustainable Future." in html, "Headline missing"
        assert "One platform for responsible growth" in html, "Supporting text missing"
        assert "sustainable_hero.jpg" in html, "Hero image reference missing"
        assert "/auth/login/" in html, "Login URL link missing"
        assert "Sign Up" in html, "Sign Up button missing"
        assert "accessRequestModal" in html, "Access Policy modal missing"

        # Verify Control Tower is NOT rendered on public homepage
        assert "Executive ESG Dashboard" not in html, "Control Tower dashboard leaked on public homepage!"
        assert 'id="sidebar"' not in html, "Sidebar leaked on public homepage!"
        assert "Scope 1 Direct GHG" not in html, "KPI metrics leaked on public homepage!"
        print("    -> PASS: Root URL '/' is public, image-first, minimal, and contains no dashboard/KPIs.")


def test_static_hero_image():
    opener, _ = create_session()
    print("[2] Testing Hero Image static asset GET /static/images/landing/sustainable_hero.jpg ...")
    req = urllib.request.Request(f"{BASE_URL}/static/images/landing/sustainable_hero.jpg")
    with opener.open(req) as resp:
        status = resp.status
        content_type = resp.headers.get("Content-Type", "")
        content_length = int(resp.headers.get("Content-Length", 0))
        assert status == 200, f"Expected 200, got {status}"
        assert "image" in content_type or content_length > 100000, f"Unexpected content: {content_type}, {content_length}"
        print(f"    -> PASS: Static hero image loads with HTTP {status}, Length: {content_length} bytes.")


def test_protected_control_tower():
    opener, _ = create_session()
    print("[3] Testing Protected Control Tower GET /dashboard/ (unauthenticated) ...")
    req = urllib.request.Request(f"{BASE_URL}/dashboard/")
    try:
        # Avoid following redirect
        class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        custom_opener = urllib.request.build_opener(NoRedirectHandler)
        custom_opener.open(req)
        assert False, "Expected redirect to login"
    except urllib.error.HTTPError as e:
        assert e.code in (301, 302), f"Expected 302 Found, got {e.code}"
        loc = e.headers.get("Location", "")
        assert "/auth/login/" in loc, f"Expected redirect to /auth/login/, got {loc}"
        print(f"    -> PASS: Unauthenticated access to /dashboard/ redirected to {loc}")


def get_csrf_token(opener, url):
    req = urllib.request.Request(url)
    with opener.open(req) as resp:
        html = resp.read().decode("utf-8")
        match = re.search(r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']', html)
        if match:
            return match.group(1)
    return ""


def test_authenticated_dashboard_flow():
    opener, _ = create_session()
    print("[4] Testing Login Flow and Authenticated Access ...")
    login_url = f"{BASE_URL}/auth/login/"
    token = get_csrf_token(opener, login_url)
    data = urllib.parse.urlencode({
        "csrfmiddlewaretoken": token,
        "username": "meil_operator",
        "password": "OperatorPass123!",
    }).encode("utf-8")

    req = urllib.request.Request(login_url, data=data, headers={"Referer": login_url})
    with opener.open(req) as resp:
        assert resp.status == 200, f"Login failed with status {resp.status}"

    # Now access Control Tower at /dashboard/ as authenticated operator
    print("[5] Testing Control Tower GET /dashboard/ (authenticated) ...")
    req = urllib.request.Request(f"{BASE_URL}/dashboard/")
    with opener.open(req) as resp:
        status = resp.status
        html = resp.read().decode("utf-8")
        assert status == 200, f"Expected 200, got {status}"
        assert "Executive ESG Dashboard" in html, "Control Tower dashboard title missing"
        assert "Scope 1 Direct GHG" in html, "Scope 1 metric missing"
        assert "Scope 2 Electricity" in html, "Scope 2 metric missing"
        assert 'id="sidebar"' in html or "esg-sidebar" in html, "Sidebar missing on dashboard"
        print("    -> PASS: Authenticated user successfully loads Executive Control Tower at /dashboard/.")

    # Now verify visiting '/' when authenticated still serves public landing page with CTA
    print("[6] Testing Public Landing Page GET / (authenticated) ...")
    req = urllib.request.Request(f"{BASE_URL}/")
    with opener.open(req) as resp:
        status = resp.status
        html = resp.read().decode("utf-8")
        assert status == 200, f"Expected 200, got {status}"
        assert "Building a" in html and "Sustainable Future." in html, "Landing page title missing"
        assert "/dashboard/" in html or "/auth/logout/" in html, "Dashboard / logout CTA missing"
        print("    -> PASS: Authenticated user visiting '/' receives public landing page with dashboard CTA.")


if __name__ == "__main__":
    try:
        test_public_homepage()
        test_static_hero_image()
        test_protected_control_tower()
        test_authenticated_dashboard_flow()
        print("\n=== ALL LIVE HTTP VERIFICATION CHECKS PASSED ===")
    except Exception as exc:
        print(f"\n[FAIL] Live verification failed: {exc}")
        sys.exit(1)
