#!/usr/bin/env python3
"""Debug collection fetch - try with different params."""
import json
import requests
from pathlib import Path

cookie_file = Path("data/session/nicholas.householder.cookies")
with open(cookie_file) as f:
    cookies = json.load(f)

session = requests.Session()
for name, val in cookies.items():
    session.cookies.set(name, val, domain=".instagram.com")
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "X-IG-App-ID": "936619743392459",
    "X-Requested-With": "XMLHttpRequest",
})

collection_id = "18140096713464751"
url = f"https://www.instagram.com/api/v1/feed/collection/{collection_id}/"

# First, see what the 400 error says
r = session.get(url, timeout=15)
print(f"No params: {r.status_code}")
try:
    print(f"Response: {json.dumps(r.json(), indent=2)[:500]}")
except:
    print(f"Response text: {r.text[:500]}")

# Try with POST
print("\n--- POST ---")
r2 = session.post(url, timeout=15)
print(f"POST no params: {r2.status_code}")
try:
    print(f"Response: {json.dumps(r2.json(), indent=2)[:500]}")
except:
    print(f"Response text: {r2.text[:500]}")

# Try with common params
print("\n--- With params ---")
r3 = session.get(url, params={"count": 20}, timeout=15)
print(f"With count: {r3.status_code}")
try:
    d = r3.json()
    items = d.get("items", [])
    print(f"Items: {len(items)}, more: {d.get('more_available')}")
    if items:
        media = items[0].get("media", {})
        print(f"First: code={media.get('code')} type={media.get('media_type')}")
        vv = media.get("video_versions", [])
        print(f"Has video versions: {bool(vv)}")
except Exception as e:
    print(f"Parse error: {e}")
    print(f"Response text: {r3.text[:500]}")
