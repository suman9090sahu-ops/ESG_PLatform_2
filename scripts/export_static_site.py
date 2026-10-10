import os
import re
import sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
import django

os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.development'
django.setup()

from django.test import Client

client = Client()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pages_to_export = [
    ('/', ''),
    ('/ui-preview/', 'ui-preview'),
    ('/components/', 'components'),
    ('/auth/login/', 'auth/login'),
]

for url_path, sub_dir in pages_to_export:
    response = client.get(url_path)
    print(f"GET {url_path} -> HTTP {response.status_code}")
    if response.status_code == 200:
        html = response.content.decode('utf-8')
        
        target_dir = os.path.join(BASE_DIR, sub_dir) if sub_dir else BASE_DIR
        os.makedirs(target_dir, exist_ok=True)
        target_file = os.path.join(target_dir, 'index.html')
        
        depth = len(sub_dir.strip('/').split('/')) if sub_dir else 0
        rel_prefix = ('../' * depth) if depth > 0 else './'
        
        # Replace absolute /static/ with relative static/
        html = html.replace('/static/', rel_prefix + 'static/')
        
        # Replace root href="/" with relative root
        html = re.sub(r'href=["\']/(["\'])', r'href="' + rel_prefix + r'\1', html)
        
        # Replace /auth/login/ with relative path
        html = html.replace('href="/auth/login/"', f'href="{rel_prefix}auth/login/"')
        html = html.replace('href=\'/auth/login/\'', f'href=\'{rel_prefix}auth/login/\'')
        
        # Replace /ui-preview/ with relative path
        html = html.replace('href="/ui-preview/"', f'href="{rel_prefix}ui-preview/"')
        html = html.replace('href=\'/ui-preview/\'', f'href=\'{rel_prefix}ui-preview/\'')
        
        # Replace /components/ with relative path
        html = html.replace('href="/components/"', f'href="{rel_prefix}components/"')
        html = html.replace('href=\'/components/\'', f'href=\'{rel_prefix}components/\'')
        
        with open(target_file, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"Exported {target_file} ({len(html)} bytes)")

print("Static export complete!")
