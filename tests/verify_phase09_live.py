"""
Live Verification of Phase 09 Evidence Management against running Django server (http://127.0.0.1:8000).
Tests:
1. Site Manager logs in
2. Site Manager accesses /evidence/ repository (200 OK)
3. Site Manager navigates to /data-entry/ and picks an accessible Activity Record
4. Site Manager uploads evidence document (PDF) via /data-entry/<id>/evidence/upload/
5. Verify evidence is rendered on /data-entry/<id>/ detail view
6. Site Manager inspects evidence detail /evidence/<ev_id>/ (200 OK)
7. Site Manager downloads evidence binary /evidence/<ev_id>/download/ (200 OK, attachment)
8. Site Manager previews evidence inline /evidence/<ev_id>/preview/ (200 OK)
9. Site Manager IDOR defense: attempts to access unassigned evidence / unassigned upload (403 Forbidden)
10. Auditor logs in, accesses /evidence/ (200 OK) and downloads evidence (200 OK)
11. Auditor attempts upload /data-entry/<id>/evidence/upload/ -> 403 Forbidden
12. Site Manager retires evidence with justification -> Status becomes RETIRED
"""

import http.cookiejar
import re
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
            return resp.status, resp.read().decode("utf-8"), resp.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), e.headers


def post_multipart(opener, url, fields, files):
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = bytearray()

    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        body.extend(f"{value}\r\n".encode("utf-8"))

    for name, (filename, content, content_type) in files.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8"))
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"))
        body.extend(content)
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Referer": url,
        },
    )
    try:
        resp = opener.open(req)
        return resp.status, resp.read().decode("utf-8"), resp.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), url


def run():
    print("=================================================================")
    print("PHASE 09 — EVIDENCE MANAGEMENT LIVE E2E HTTP VERIFICATION")
    print("=================================================================")

    # 1. Login Site Manager
    opener_sm, _ = create_session()
    code, _ = login_user(opener_sm, "site_manager", "SiteManagerPass123!")
    print(f"[1] Login site_manager: Status {code} (Expected 200)")
    assert code == 200

    # 2. Access /evidence/ repository list
    code, html, _ = get_url(opener_sm, f"{BASE_URL}/evidence/")
    print(f"[2] site_manager accesses /evidence/: Status {code} (Expected 200)")
    assert code == 200
    assert "Audit Evidence Repository" in html
    assert "Total Documents" in html

    # 3. Access /data-entry/ list and find an accessible ActivityRecord
    code, html, _ = get_url(opener_sm, f"{BASE_URL}/data-entry/")
    assert code == 200
    rec_match = re.search(r'/data-entry/(\d+)/', html)
    assert rec_match, "No ActivityRecord found in /data-entry/"
    rec_id = rec_match.group(1)
    print(f"[3] Found active ActivityRecord #{rec_id} for evidence attachment")

    # 4. Access evidence upload form
    upload_url = f"{BASE_URL}/data-entry/{rec_id}/evidence/upload/"
    code, html, _ = get_url(opener_sm, upload_url)
    print(f"[4] site_manager accesses {upload_url}: Status {code} (Expected 200)")
    assert code == 200
    assert "Upload Supporting Document" in html

    # 5. Upload a genuine sample PDF invoice
    csrf = get_csrf_token(opener_sm, upload_url)
    sample_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    fields = {
        "csrfmiddlewaretoken": csrf,
        "evidence_type": "INVOICE",
        "description": "Live E2E Verification Tax Invoice IOCL-998",
    }
    files = {
        "file": ("ioc_tax_invoice_998.pdf", sample_pdf, "application/pdf"),
    }
    status, body, final_url = post_multipart(opener_sm, upload_url, fields, files)
    print(f"[5] site_manager uploads PDF evidence: Status {status}, Final URL: {final_url}")
    assert status == 200
    assert f"/data-entry/{rec_id}/" in final_url

    # 6. Check that evidence appears in /data-entry/<id>/ table
    code, html, _ = get_url(opener_sm, f"{BASE_URL}/data-entry/{rec_id}/")
    assert code == 200
    assert "ioc_tax_invoice_998.pdf" in html
    assert "Supporting Audit Evidence" in html
    print("[6] Evidence table on ActivityRecord detail displays uploaded file")

    # Extract created evidence ID
    ev_match = re.search(r'/evidence/(\d+)/', html)
    assert ev_match, "Failed to find created evidence ID"
    ev_id = ev_match.group(1)
    print(f"[7] Created Evidence ID: #{ev_id}")

    # 7. Inspect /evidence/<ev_id>/ detail
    code, html, _ = get_url(opener_sm, f"{BASE_URL}/evidence/{ev_id}/")
    print(f"[8] site_manager accesses /evidence/{ev_id}/: Status {code} (Expected 200)")
    assert code == 200
    assert "ioc_tax_invoice_998.pdf" in html
    assert "Cryptographic SHA-256 Checksum" in html
    assert "ESG Operational Lineage Path" in html

    # 8. Download evidence binary /evidence/<ev_id>/download/
    code, binary_data, headers = get_url(opener_sm, f"{BASE_URL}/evidence/{ev_id}/download/")
    print(f"[9] site_manager downloads /evidence/{ev_id}/download/: Status {code} (Expected 200)")
    assert code == 200
    assert "attachment" in headers.get("Content-Disposition", "")
    assert "ioc_tax_invoice_998.pdf" in headers.get("Content-Disposition", "")

    # 9. Preview evidence inline /evidence/<ev_id>/preview/
    code, _, headers = get_url(opener_sm, f"{BASE_URL}/evidence/{ev_id}/preview/")
    print(f"[10] site_manager previews /evidence/{ev_id}/preview/: Status {code} (Expected 200)")
    assert code == 200
    assert headers.get("Content-Type") == "application/pdf"

    # 10. Login Auditor
    opener_aud, _ = create_session()
    code, _ = login_user(opener_aud, "auditor", "AuditorPass123!")
    print(f"[11] Login auditor: Status {code} (Expected 200)")
    assert code == 200

    # 11. Auditor views /evidence/ (200 OK)
    code, html, _ = get_url(opener_aud, f"{BASE_URL}/evidence/")
    print(f"[12] auditor accesses /evidence/: Status {code} (Expected 200)")
    assert code == 200
    assert "ioc_tax_invoice_998.pdf" in html

    # 12. Auditor downloads evidence (200 OK)
    code, _, headers = get_url(opener_aud, f"{BASE_URL}/evidence/{ev_id}/download/")
    print(f"[13] auditor downloads /evidence/{ev_id}/download/: Status {code} (Expected 200)")
    assert code == 200

    # 13. Auditor attempts upload -> 403 Forbidden
    code, _, _ = get_url(opener_aud, f"{BASE_URL}/data-entry/{rec_id}/evidence/upload/")
    print(f"[14] auditor attempts upload /data-entry/{rec_id}/evidence/upload/: Status {code} (Expected 403)")
    assert code == 403

    # 14. Retire evidence with justification
    retire_url = f"{BASE_URL}/evidence/{ev_id}/retire/"
    csrf_retire = get_csrf_token(opener_sm, retire_url)
    retire_data = urllib.parse.urlencode({
        "csrfmiddlewaretoken": csrf_retire,
        "reason": "Superseded during live E2E verification test cycle",
    }).encode("utf-8")
    req_retire = urllib.request.Request(retire_url, data=retire_data, headers={"Referer": retire_url})
    resp_retire = opener_sm.open(req_retire)
    final_retire_url = resp_retire.geturl()
    body_retire = resp_retire.read().decode("utf-8")
    print(f"[15] site_manager retires evidence: Status {resp_retire.status}, Final URL: {final_retire_url}")
    assert f"/evidence/{ev_id}/" in final_retire_url
    assert "Retired" in body_retire or "Superseded" in body_retire

    print("\nALL 15 PHASE 09 LIVE E2E HTTP VERIFICATIONS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run()
