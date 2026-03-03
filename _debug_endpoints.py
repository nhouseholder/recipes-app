#!/usr/bin/env python3
"""Test different API endpoints for fetching collection items."""
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

# Try multiple possible endpoints
endpoints = [
    f"https://www.instagram.com/api/v1/feed/collection/{collection_id}/",
    f"https://www.instagram.com/api/v1/feed/saved/collection/{collection_id}/",
    f"https://www.instagram.com/api/v1/feed/saved/{collection_id}/",
    f"https://i.instagram.com/api/v1/feed/collection/{collection_id}/",
]

for url in endpoints:
    try:
        r = session.get(url, timeout=15)
        print(f"{r.status_code} - {url}")
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            more = data.get("more_available", False)
            print(f"  Items: {len(items)}, more_available: {more}")
            if items:
                media = items[0].get("media", {})
                code = media.get("code", "?")
                mt = media.get("media_type")
                print(f"  First item: {code} type={mt}")
            break
    except Exception as e:
        print(f"ERROR - {url}: {e}")
