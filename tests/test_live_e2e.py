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

    print("\nALL 18 LIVE E2E HTTP VERIFICATIONS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run()
