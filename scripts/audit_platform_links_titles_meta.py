import os
import sys
import re
import urllib.parse
from html.parser import HTMLParser

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
import django
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from django.urls import resolve, reverse, Resolver404

User = get_user_model()

class PageScanner(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.title = ""
        self.meta_desc = ""
        self.links = []
        self.buttons = []
        self.images = []
        self.footer_links = []
        self.in_footer = False

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        if tag == "title":
            self.in_title = True
        elif tag == "meta" and attr_dict.get("name", "").lower() == "description":
            self.meta_desc = attr_dict.get("content", "")
        elif tag == "footer":
            self.in_footer = True
        elif tag == "a":
            href = attr_dict.get("href", "")
            data_bs_toggle = attr_dict.get("data-bs-toggle", "")
            data_bs_target = attr_dict.get("data-bs-target", "")
            classes = attr_dict.get("class", "")
            link_info = {
                "href": href,
                "data_bs_toggle": data_bs_toggle,
                "data_bs_target": data_bs_target,
                "class": classes,
                "text": ""
            }
            self.links.append(link_info)
            if self.in_footer:
                self.footer_links.append(link_info)
        elif tag == "button":
            self.buttons.append({
                "type": attr_dict.get("type", ""),
                "data_bs_toggle": attr_dict.get("data-bs-toggle", ""),
                "data_bs_target": attr_dict.get("data-bs-target", ""),
                "onclick": attr_dict.get("onclick", ""),
                "class": attr_dict.get("class", ""),
                "id": attr_dict.get("id", "")
            })
        elif tag == "img":
            self.images.append({
                "src": attr_dict.get("src", ""),
                "alt": attr_dict.get("alt", "")
            })

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "footer":
            self.in_footer = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.links:
            self.links[-1]["text"] += data.strip()


def run_audit():
    client = Client()
    
    # 1. Test unauthenticated routes
    public_urls = [
        "/",
        "/landing/",
        "/auth/login/",
        "/auth/password-reset/",
        "/health/",
        "/components/",
        "/ui-preview/",
    ]

    print("=== PUBLIC ROUTES AUDIT ===")
    for url in public_urls:
        resp = client.get(url, follow=False)
        content = resp.content.decode("utf-8", errors="ignore")
        scanner = PageScanner()
        scanner.feed(content)
        print(f"\nURL: {url} -> HTTP {resp.status_code}")
        print(f"  Title: {scanner.title.strip()}")
        print(f"  Meta Desc: {scanner.meta_desc.strip()}")
        print(f"  Total Links: {len(scanner.links)}, Footer Links: {len(scanner.footer_links)}")
        print(f"  Images: {len(scanner.images)}")
        
        # Check for hash links
        hash_links = [l for l in scanner.links if l['href'] == '#' and not l['data_bs_toggle']]
        if hash_links:
            print(f"  [WARN] Unbound # links: {len(hash_links)}")
            for hl in hash_links[:5]:
                print(f"     -> text: '{hl['text']}' class: '{hl['class']}'")
        
        # Check footer links
        if scanner.footer_links:
            print("  Footer links:")
            for fl in scanner.footer_links:
                print(f"     -> href: '{fl['href']}' text: '{fl['text']}' toggle: '{fl['data_bs_toggle']}'")
        else:
            print("  [WARN] No footer links found in <footer>")

        # Check images
        for img in scanner.images:
            src = img['src']
            alt = img['alt']
            # test static file resolution
            if src.startswith('/static/'):
                rel_path = src[len('/static/'):]
                disk_path = os.path.join(BASE_DIR, 'static', rel_path.replace('/', os.sep))
                exists = os.path.exists(disk_path)
                status = "OK" if exists else "MISSING!"
                print(f"  Image: {src} -> {status} (alt: '{alt}')")
            elif src.startswith('/media/'):
                rel_path = src[len('/media/'):]
                disk_path = os.path.join(BASE_DIR, 'media', rel_path.replace('/', os.sep))
                exists = os.path.exists(disk_path)
                status = "OK" if exists else "MISSING!"
                print(f"  Image: {src} -> {status} (alt: '{alt}')")
            else:
                print(f"  Image: {src} (alt: '{alt}')")

    # 2. Test authenticated routes with esg_manager
    user = User.objects.filter(username="esg_manager").first() or User.objects.filter(is_superuser=True).first()
    if user:
        client.force_login(user)
        print(f"\n=== AUTHENTICATED AUDIT ({user.username}) ===")
        auth_urls = [
            "/dashboard/",
            "/organization/",
            "/organization/companies/",
            "/organization/subsidiaries/",
            "/organization/projects/",
            "/organization/sites/",
            "/reporting-periods/",
            "/activity-master/",
            "/data-entry/",
            "/evidence/",
            "/submissions/",
            "/corrections/",
            "/anomalies/",
            "/procurement/",
            "/transport/",
            "/reports/",
            "/emission-factors/",
            "/scope3/",
            "/components/",
            "/ui-preview/",
        ]
        for url in auth_urls:
            resp = client.get(url, follow=False)
            content = resp.content.decode("utf-8", errors="ignore")
            scanner = PageScanner()
            scanner.feed(content)
            title = scanner.title.strip().replace("\n", " ")
            title = re.sub(r'\s+', ' ', title)
            meta = scanner.meta_desc.strip()
            print(f"URL: {url:30} -> HTTP {resp.status_code:3} | Title: {title[:45]} | Meta: {'YES' if meta else 'NO'}")
            
            # Check footer links
            if scanner.footer_links:
                for fl in scanner.footer_links:
                    if fl['href'] == '#' and not fl['data_bs_toggle']:
                        print(f"   [WARN footer link #]: text: '{fl['text']}'")

    print("\n=== VIEWS CONTEXT CHECK ===")
    from apps.core.urls import urlpatterns
    for p in urlpatterns:
        pattern = str(p.pattern)
        if '<' not in pattern and not pattern.startswith('auth/reset') and not pattern.startswith('auth/logout') and not pattern.startswith('health'):
            url = '/' + pattern.lstrip('/')
            try:
                resp = client.get(url, follow=False)
                if resp.status_code == 200 and hasattr(resp, 'context') and resp.context:
                    ctx = resp.context
                    pt = ctx.get('page_title')
                    templates_used = [t.name for t in resp.templates if t.name] if hasattr(resp, 'templates') else []
                    if not pt:
                        print(f"NO page_title: {url:35} -> templates: {templates_used}")
            except Exception as e:
                pass

if __name__ == "__main__":
    run_audit()
