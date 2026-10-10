import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for sub_path in ['ui-preview/index.html', 'components/index.html']:
    full_path = os.path.join(BASE_DIR, sub_path)
    if not os.path.exists(full_path):
        continue
    with open(full_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # Replace /health/
    html = html.replace('href="/health/"', 'href="../#"')
    html = html.replace('href=\'/health/\'', 'href=\'../#\'')

    # Replace dead backend routes with javascript alert
    backend_routes = [
        '/submissions/', '/data-entry/', '/anomalies/', '/dashboard/', 
        '/audit-logs/', '/evidence/', '/reports/', '/scope3/', '/procurement/',
        '/transport/', '/cems/', '/admin/', '/emission-factors/'
    ]
    for r in backend_routes:
        html = html.replace(f'href="{r}"', 'href="#" onclick="alert(\'Live transactional routes require the active Django backend server: python manage.py runserver\'); return false;"')
        html = html.replace(f"href='{r}'", "href='#' onclick=\"alert('Live transactional routes require the active Django backend server: python manage.py runserver'); return false;\"")

    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Cleaned {sub_path}")
