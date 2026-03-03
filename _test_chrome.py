"""Quick test: can we use chrome cookies to authenticate with Instagram?"""
import browser_cookie3
import requests

cj = browser_cookie3.chrome(domain_name='.instagram.com')
cookies = {}
for c in cj:
    cookies[c.name] = c.value

print(f"Found {len(cookies)} Instagram cookies from Chrome")
print(f"Has sessionid: {bool(cookies.get('sessionid'))}")
print(f"ds_user_id: {cookies.get('ds_user_id', 'not found')}")

# Test via direct API
session = requests.Session()
for name, val in cookies.items():
    session.cookies.set(name, val, domain='.instagram.com')

session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'X-IG-App-ID': '936619743392459',
    'X-Requested-With': 'XMLHttpRequest',
})

# Test 1: web_form_data
print("\n--- Test 1: accounts/edit/web_form_data ---")
try:
    r = session.get('https://www.instagram.com/api/v1/accounts/edit/web_form_data/', timeout=10)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        username = data.get("form_data", {}).get("username", "")
        print(f"Username: {username}")
    else:
        print(f"Body: {r.text[:300]}")
except Exception as e:
    print(f"Error: {e}")

# Test 2: Try Instaloader with these cookies
print("\n--- Test 2: Instaloader with injected session ---")
try:
    import instaloader
    L = instaloader.Instaloader(quiet=True)
    
    isession = requests.Session()
    for name, val in cookies.items():
        isession.cookies.set(name, val, domain='.instagram.com')
    isession.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'X-IG-App-ID': '936619743392459',
        'X-Requested-With': 'XMLHttpRequest',
    })
    L.context._session = isession
    
    try:
        username = L.context.username
        print(f"Instaloader username: {username}")
    except Exception as e:
        print(f"Instaloader context.username failed: {e}")
    
    try:
        uid = L.context.user_id
        print(f"Instaloader user_id: {uid}")
    except Exception as e:
        print(f"Instaloader context.user_id failed: {e}")

except Exception as e:
    print(f"Instaloader test error: {e}")
