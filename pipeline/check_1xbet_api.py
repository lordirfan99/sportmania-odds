"""Check 1xBet page for embedded data or API endpoints."""
import requests, re

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

# Login 
r1 = s.get('https://1xbet-malaysia.mobi/en/user/login', timeout=10)
csrf = re.search(r'name="_csrf"[^>]*value="([^"]+)"', r1.text)
data = {'LoginForm[username]': '1733712589', 'LoginForm[password]': 'Tapestry1Constrict1raking.', 'LoginForm[rememberMe]': '1'}
if csrf: data['_csrf'] = csrf.group(1)
s.post('https://1xbet-malaysia.mobi/en/user/login', data=data, timeout=10, allow_redirects=True)

# Get football page
r2 = s.get('https://1xbet-malaysia.mobi/en/line/football', timeout=10)
html = r2.text

# Find all script tags with potential data
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
print(f"Found {len(scripts)} script tags")

for i, sc in enumerate(scripts):
    if len(sc) > 1000 and ('{' in sc or '[' in sc):
        if 'window.__' in sc or 'initial' in sc.lower() or 'preload' in sc.lower() or 'state' in sc.lower():
            print(f"\nScript {i}: {len(sc)} chars")
            print(sc[:500])
            print("...")

# Look for API endpoints in script src
for sc in re.findall(r'<script[^>]*src="([^"]+)"', html):
    if 'api' in sc.lower() or 'line' in sc.lower() or 'game' in sc.lower():
        print(f"API script: {sc}")

# Check for JSON data in data-* attributes  
json_attrs = re.findall(r'data-(\w+)="({[^"]+})"', html)
if json_attrs:
    print(f"\nJSON data attrs: {len(json_attrs)}")
    for k, v in json_attrs[:3]:
        print(f"  {k}: {v[:200]}")

# Check if odds are embedded in page
has_1639 = '1.639' in html
has_spain = 'Spain' in html
print(f"\nHas odds (1.639): {has_1639}")
print(f"Has Spain: {has_spain}")
print(f"HTML size: {len(html)} bytes")

# Check for XMLHttpRequest or fetch URLs in scripts
xhr_urls = re.findall(r'["\'](https?://[^"\']*line[^"\']*)["\']', html)
for url in xhr_urls[:5]:
    print(f"Line URL found: {url}")
