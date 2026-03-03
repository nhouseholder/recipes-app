#!/usr/bin/env python3
"""Test fetching from the Recipes collection."""
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

# Fetch first page from recipes collection
url = f"https://www.instagram.com/api/v1/feed/saved/{collection_id}/posts/"
r = session.get(url, timeout=20)
print(f"Status: {r.status_code}")

if r.status_code == 200:
    data = r.json()
    items = data.get("items", [])
    more = data.get("more_available", False)
    next_max = data.get("next_max_id", "")
    print(f"Items on page 1: {len(items)}")
    print(f"More available: {more}")
    print(f"Next max_id: {next_max}")
    
    videos = 0
    for it in items[:10]:
        media = it.get("media", {})
        mt = media.get("media_type")
        code = media.get("code", "?")
        vv = media.get("video_versions", [])
        has_url = bool(vv)
        print(f"  - {code} type={mt} has_video_url={has_url}")
        if mt == 2:
            videos += 1
    print(f"\nVideos in first 10: {videos}")
else:
    print(f"Error: {r.text[:500]}")
