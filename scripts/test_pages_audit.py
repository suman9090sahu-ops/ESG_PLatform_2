import urllib.request
import re
from html.parser import HTMLParser

class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_title = False
        self.title = ""
        self.meta_desc = ""
        self.links = []
        self.buttons = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        if tag == "title":
            self.in_title = True
        elif tag == "meta" and attr_dict.get("name", "").lower() == "description":
            self.meta_desc = attr_dict.get("content", "")
        elif tag == "a":
            href = attr_dict.get("href", "")
            self.links.append((href, attr_dict.get("class", ""), attr_dict.get("id", "")))
        elif tag == "button":
            self.buttons.append((attr_dict.get("type", ""), attr_dict.get("class", ""), attr_dict.get("id", "")))
        elif tag == "img":
            self.images.append((attr_dict.get("src", ""), attr_dict.get("alt", "")))

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data

urls = [
    'http://127.0.0.1:8000/',
    'http://127.0.0.1:8000/auth/login/',
    'http://127.0.0.1:8000/auth/password-reset/',
    'http://127.0.0.1:8000/components/',
    'http://127.0.0.1:8000/ui-preview/',
]

for url in urls:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req)
        body = resp.read().decode('utf-8', errors='ignore')
        parser = MetaParser()
        parser.feed(body)
        print("="*60)
        print(f"[{resp.status}] {url}")
        print(f"   Title: {parser.title.strip()}")
        print(f"   Meta Desc: {parser.meta_desc.strip()}")
        print(f"   Links count: {len(parser.links)}")
        print(f"   Images: {parser.images}")
        # check links
        for h, c, i in parser.links[:10]:
            print(f"     -> {h} (class: {c})")
    except Exception as e:
        print(f"[ERR] {url} -> {e}")
