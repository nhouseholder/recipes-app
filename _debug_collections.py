#!/usr/bin/env python3
"""Debug script to list Instagram saved collections and test fetching."""
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

# Verify session
r = session.get("https://www.instagram.com/api/v1/accounts/edit/web_form_data/", timeout=10)
print(f"Auth check: status={r.status_code}")
if r.status_code == 200:
    uname = r.json().get("form_data", {}).get("username", "")
    print(f"Logged in as: {uname}")

# List collections
print("\n--- Collections ---")
r = session.get(
    "https://www.instagram.com/api/v1/collections/list/",
    params={"collection_types": '["ALL_MEDIA_AUTO_COLLECTION","MEDIA","PRODUCT_AUTO_COLLECTION"]'},
    timeout=15,
)
print(f"Collections status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    items = data.get("items", [])
    print(f"Found {len(items)} collections")
    for item in items:
        cname = item.get("collection_name", "(unnamed)")
        cid = item.get("collection_id", "?")
        ctype = item.get("collection_type", "?")
        media_count = item.get("collection_media_count", 0)
        print(f"  - '{cname}' id={cid} type={ctype} count={media_count}")
else:
    print(f"Error response: {r.text[:500]}")

# Try the "all saved posts" endpoint too
print("\n--- All Saved Posts (first page) ---")
r2 = session.get("https://www.instagram.com/api/v1/feed/saved/posts/", timeout=15)
print(f"Saved posts status: {r2.status_code}")
if r2.status_code == 200:
    data2 = r2.json()
    items2 = data2.get("items", [])
    print(f"First page has {len(items2)} items")
    more = data2.get("more_available", False)
    print(f"More available: {more}")
    videos = 0
    for it in items2[:5]:
        media = it.get("media", {})
        mt = media.get("media_type")
        code = media.get("code", "?")
        print(f"  - {code} media_type={mt}")
        if mt == 2:
            videos += 1
    print(f"Videos in first 5: {videos}")
else:
    print(f"Error: {r2.text[:500]}")
