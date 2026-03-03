#!/usr/bin/env python3
"""Debug collection fetch - fix user agent."""
import json
import requests
from pathlib import Path

cookie_file = Path("data/session/nicholas.householder.cookies")
with open(cookie_file) as f:
    cookies = json.load(f)

session = requests.Session()
for name, val in cookies.items():
    session.cookies.set(name, val, domain=".instagram.com")

# Try different user agents
user_agents = {
    "ig_mobile": "Instagram 275.0.0.27.98 Android (33/13; 420dpi; 1080x2400; samsung; SM-G991B; o1s; exynos2100; en_US; 458229258)",
    "chrome_real": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

collection_id = "18140096713464751"
url = f"https://www.instagram.com/api/v1/feed/collection/{collection_id}/"

for name, ua in user_agents.items():
    print(f"\n--- {name} ---")
    session.headers.update({
        "User-Agent": ua,
        "X-IG-App-ID": "936619743392459",
        "X-Requested-With": "XMLHttpRequest",
    })
    r = session.get(url, timeout=15)
    print(f"Status: {r.status_code}")
    try:
        d = r.json()
        if "items" in d:
            items = d["items"]
            print(f"Items: {len(items)}, more: {d.get('more_available')}")
            if items:
                media = items[0].get("media", {})
                print(f"First: code={media.get('code')} type={media.get('media_type')}")
        else:
            print(f"Response: {json.dumps(d)[:300]}")
    except:
        print(f"Text: {r.text[:300]}")

# Also try i.instagram.com with mobile UA
print("\n--- i.instagram.com + mobile UA ---")
session.headers["User-Agent"] = user_agents["ig_mobile"]
url2 = f"https://i.instagram.com/api/v1/feed/collection/{collection_id}/"
r2 = session.get(url2, timeout=15)
print(f"Status: {r2.status_code}")
try:
    d2 = r2.json()
    if "items" in d2:
        items2 = d2["items"]
        print(f"Items: {len(items2)}, more: {d2.get('more_available')}")
        if items2:
            media = items2[0].get("media", {})
            print(f"First: code={media.get('code')} type={media.get('media_type')}")
            vv = media.get("video_versions", [])
            print(f"Has video_versions: {bool(vv)}, count={len(vv)}")
    else:
        print(f"Response: {json.dumps(d2)[:300]}")
except:
    print(f"Text: {r2.text[:300]}")
