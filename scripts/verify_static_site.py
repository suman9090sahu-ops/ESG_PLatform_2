import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pages = [
    os.path.join(BASE_DIR, 'index.html'),
    os.path.join(BASE_DIR, 'ui-preview', 'index.html'),
    os.path.join(BASE_DIR, 'components', 'index.html'),
    os.path.join(BASE_DIR, 'auth', 'login', 'index.html'),
]

all_passed = True

for page in pages:
    rel_page = os.path.relpath(page, BASE_DIR)
    if not os.path.exists(page):
        print(f"FAIL: {rel_page} does not exist!")
        all_passed = False
        continue
    
    with open(page, 'r', encoding='utf-8') as f:
        content = f.read()
    
    page_dir = os.path.dirname(page)
    # Check all src and href assets that are local files
    assets = re.findall(r'(?:src|href)=["\']([^"\'#:]+)["\']', content)
    
    missing = []
    for asset in assets:
        # ignore mailto, javascript, external links, empty
        if asset.startswith(('mailto:', 'javascript:', 'http://', 'https://', '#')) or not asset:
            continue
        
        # Clean query strings/hashes
        asset_clean = asset.split('?')[0].split('#')[0]
        if not asset_clean:
            continue
            
        full_asset_path = os.path.normpath(os.path.join(page_dir, asset_clean))
        if not os.path.exists(full_asset_path):
            missing.append((asset, full_asset_path))
    
    if missing:
        print(f"WARN in {rel_page}: {len(missing)} missing references:")
        for m, fp in missing[:5]:
            print(f"   -> {m} (looked for {fp})")
        all_passed = False
    else:
        print(f"PASS: {rel_page} - all local assets exist!")

if all_passed:
    print("\nSUCCESS: All static pages and their assets are verified!")
else:
    print("\nISSUES DETECTED: Check above warnings.")
