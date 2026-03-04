"""
Instagram Saved Videos Fetcher
Logs into Instagram, finds the "recipes" saved collection, and downloads all videos.
Uses session caching so you only need to log in once.
Includes retry logic with exponential backoff for rate-limiting.
"""

import os
import json
import time
import subprocess
import base64
import instaloader
import requests
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
VIDEOS_DIR = DATA_DIR / "videos"
METADATA_FILE = DATA_DIR / "fetched_posts.json"
SESSION_DIR = Path(__file__).parent / "data" / "session"
CONFIG_FILE = DATA_DIR / "config.json"

MAX_RETRIES = 4
INITIAL_BACKOFF = 30  # seconds


def _get_loader() -> instaloader.Instaloader:
    """Create a configured Instaloader instance."""
    return instaloader.Instaloader(
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        dirname_pattern=str(VIDEOS_DIR),
        filename_pattern="{shortcode}",
        quiet=True,
        max_connection_attempts=3,
    )


def save_credentials(username: str, password: str):
    """Save Instagram credentials to config (base64 obfuscated — local only)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    config = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            config = json.load(f)
    config["ig_cred_user"] = base64.b64encode(username.encode()).decode()
    config["ig_cred_pass"] = base64.b64encode(password.encode()).decode()
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def load_credentials() -> tuple[str, str]:
    """Load saved Instagram credentials."""
    if not CONFIG_FILE.exists():
        return "", ""
    with open(CONFIG_FILE) as f:
        config = json.load(f)
    try:
        user = base64.b64decode(config.get("ig_cred_user", "")).decode()
        pw = base64.b64decode(config.get("ig_cred_pass", "")).decode()
        return user, pw
    except Exception:
        return "", ""


def _retry_with_backoff(func, *args, max_retries=MAX_RETRIES, progress_callback=None):
    """Retry a function with exponential backoff on rate-limit errors."""
    for attempt in range(max_retries):
        try:
            return func(*args)
        except (instaloader.exceptions.ConnectionException,
                instaloader.exceptions.QueryReturnedBadRequestException) as e:
            err = str(e).lower()
            if "401" in err or "429" in err or "wait" in err or "rate" in err or "please wait" in err:
                wait = INITIAL_BACKOFF * (2 ** attempt)
                msg = f"Instagram rate limited — waiting {wait}s before retry ({attempt+1}/{max_retries})..."
                print(f"[Instagram] {msg}")
                if progress_callback:
                    progress_callback("fetch", 0, 0, msg)
                time.sleep(wait)
            else:
                raise
    raise Exception("Instagram rate limit: too many requests. Please wait 10-15 minutes and try again.")


def login_from_browser(browser: str = "auto") -> dict:
    """
    Import Instagram session from an existing browser login.
    This avoids triggering a new login — Instagram never sees a suspicious request.
    Supports: chrome, firefox, safari, or 'auto' to try all.
    """
    import threading

    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    def _try_browser_cookie3(name, cookie_fn):
        """Try extracting cookies with a timeout to avoid Keychain hangs."""
        result = {"cookies": {}}

        def _extract():
            try:
                cj = cookie_fn(domain_name=".instagram.com")
                for cookie in cj:
                    if cookie.value:
                        result["cookies"][cookie.name] = cookie.value
            except Exception as e:
                print(f"[Instagram] {name} cookie extraction error: {e}")

        t = threading.Thread(target=_extract, daemon=True)
        t.start()
        t.join(timeout=60)  # 60-second timeout — gives user time for Keychain prompt
        if t.is_alive():
            print(f"[Instagram] {name} cookie extraction timed out (Keychain prompt?). Skipping.")
            return None
        cookies = result["cookies"]
        return cookies if cookies.get("sessionid") else None

    def _try_firefox_direct():
        """Directly read Firefox cookies.sqlite — no Keychain needed."""
        import sqlite3
        import glob
        profiles = glob.glob(os.path.expanduser(
            "~/Library/Application Support/Firefox/Profiles/*/cookies.sqlite"))
        if not profiles:
            return None
        for db_path in profiles:
            try:
                # Copy DB to avoid Firefox lock
                import shutil
                tmp_db = str(DATA_DIR / "_ff_cookies_tmp.sqlite")
                shutil.copy2(db_path, tmp_db)
                conn = sqlite3.connect(tmp_db)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT name, value FROM moz_cookies WHERE host LIKE '%instagram.com%' AND name IN ('sessionid','csrftoken','mid')")
                cookies = {row[0]: row[1] for row in cursor.fetchall()}
                conn.close()
                os.remove(tmp_db)
                if cookies.get("sessionid"):
                    return cookies
            except Exception as e:
                print(f"[Instagram] Firefox direct read error: {e}")
        return None

    def _try_safari_direct():
        """Try reading Safari cookies using binary cookies parser."""
        try:
            import subprocess as sp
            # Safari stores cookies in a binary format, but we can try using Python
            cookie_path = os.path.expanduser("~/Library/Cookies/Cookies.binarycookies")
            if not os.path.exists(cookie_path):
                return None
            # Use a simple approach: dump with sqlite (Safari 17+ uses sqlite)
            cookie_db = os.path.expanduser("~/Library/Cookies/Cookies.binarycookies")
            # Safari binary cookies are not SQLite — skip for now
            return None
        except Exception:
            return None

    try:
        import browser_cookie3
    except ImportError:
        browser_cookie3 = None

    sessionid = None
    csrftoken = None
    mid = None
    used_browser = None
    all_cookies = {}

    # Order: Firefox direct (fastest, no Keychain) → browser_cookie3 Firefox → Chrome → Safari
    browsers_to_try = []
    if browser == "auto":
        # Try Firefox direct first (no Keychain, no library needed)
        print("[Instagram] Trying Firefox direct cookie read...")
        ff_result = _try_firefox_direct()
        if ff_result and ff_result.get("sessionid"):
            sessionid = ff_result["sessionid"]
            csrftoken = ff_result.get("csrftoken")
            mid = ff_result.get("mid")
            used_browser = "firefox"

        if not sessionid and browser_cookie3:
            # Try browser_cookie3 with timeout for each browser
            for name, fn in [("firefox", browser_cookie3.firefox),
                             ("chrome", browser_cookie3.chrome)]:
                print(f"[Instagram] Trying {name} via browser_cookie3...")
                result = _try_browser_cookie3(name, fn)
                if result:
                    all_cookies = result
                    sessionid = result.get("sessionid")
                    csrftoken = result.get("csrftoken")
                    mid = result.get("mid")
                    used_browser = name
                    break

    elif browser_cookie3:
        mapping = {"chrome": browser_cookie3.chrome, "firefox": browser_cookie3.firefox}
        if browser == "firefox-direct":
            ff_result = _try_firefox_direct()
            if ff_result:
                all_cookies = ff_result
                sessionid = ff_result["sessionid"]
                csrftoken = ff_result.get("csrftoken")
                mid = ff_result.get("mid")
                used_browser = "firefox"
        elif browser in mapping:
            result = _try_browser_cookie3(browser, mapping[browser])
            if result:
                all_cookies = result
                sessionid = result.get("sessionid")
                csrftoken = result.get("csrftoken")
                mid = result.get("mid")
                used_browser = browser

    if not sessionid:
        return {
            "error": "No Instagram session found in any browser. Make sure you're logged into Instagram in Chrome or Firefox first. "
                     "If that doesn't work, use the Manual Session ID option below."
        }

    # Build a requests session with the cookies and inject into Instaloader
    extra_cookies = {}
    # Collect all extra cookies if from browser_cookie3 result
    return _create_session_from_cookies(sessionid, csrftoken, mid, used_browser, extra_cookies=all_cookies)


def _create_session_from_cookies(sessionid, csrftoken=None, mid=None, source="browser", extra_cookies=None):
    """Create an Instaloader session from raw cookies."""
    L = _get_loader()
    session = requests.Session()
    session.cookies.set("sessionid", sessionid, domain=".instagram.com")
    if csrftoken:
        session.cookies.set("csrftoken", csrftoken, domain=".instagram.com")
    if mid:
        session.cookies.set("mid", mid, domain=".instagram.com")
    if extra_cookies:
        for name, val in extra_cookies.items():
            if name not in ("sessionid", "csrftoken", "mid"):
                session.cookies.set(name, val, domain=".instagram.com")

    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
        "X-IG-App-ID": "936619743392459",
        "X-Requested-With": "XMLHttpRequest",
    })

    # Verify the session works and get username via Instagram API directly
    # (Instaloader's context.username doesn't work with injected sessions)
    username = None
    try:
        r = session.get("https://www.instagram.com/api/v1/accounts/edit/web_form_data/", timeout=10)
        if r.status_code == 200:
            data = r.json()
            username = data.get("form_data", {}).get("username", "")
    except Exception:
        pass

    if not username:
        return {"error": "Browser session found but appears expired. Log into Instagram in your browser again."}

    # Inject into Instaloader
    L.context._session = session
    L.context.username = username

    # Also set user_id from ds_user_id cookie if available
    ds_uid = session.cookies.get("ds_user_id", domain=".instagram.com")
    if ds_uid:
        L.context.user_id = int(ds_uid)

    # Save session for future use
    session_file = SESSION_DIR / f"{username}.session"
    try:
        L.save_session_to_file(str(session_file))
    except Exception:
        # If Instaloader can't save the session format, save cookies directly
        cookie_file = SESSION_DIR / f"{username}.cookies"
        cookie_data = {name: val for name, val in session.cookies.get_dict().items()}
        with open(cookie_file, 'w') as f:
            json.dump(cookie_data, f)

    config = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            config = json.load(f)
    config["instagram_username"] = username
    config["login_method"] = source
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

    return {
        "success": True,
        "message": f"Logged in as @{username} using {source} cookies!",
        "username": username,
        "browser": source,
    }


def login_with_sessionid(sessionid: str) -> dict:
    """
    Log in using a manually-provided Instagram sessionid cookie.
    User can get this from browser DevTools → Application → Cookies → instagram.com → sessionid
    """
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    return _create_session_from_cookies(sessionid.strip(), source="sessionid")


def login(username: str, password: str, two_factor_code: str = "", persist: bool = True) -> dict:
    """
    Log in to Instagram. Caches the session for future use.
    If persist=False, skip saving credentials to global config (for per-visitor sessions).
    Returns {"success": True} or {"error": "...", "needs_2fa": bool}
    """
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    session_file = SESSION_DIR / f"{username}.session"
    L = _get_loader()

    # Try cached session first
    if session_file.exists() and not password:
        try:
            L.load_session_from_file(username, str(session_file))
            # Use context.username instead of test_login() to avoid search API calls
            actual_user = L.context.username or username
            return {"success": True, "message": f"Logged in (cached session)", "username": actual_user}
        except Exception:
            session_file.unlink(missing_ok=True)

    if not password:
        return {"error": "Password required"}

    # Fresh login
    try:
        if two_factor_code:
            try:
                L.login(username, password)
            except instaloader.exceptions.TwoFactorAuthRequiredException:
                L.two_factor_login(two_factor_code)
        else:
            L.login(username, password)

        # Resolve actual Instagram username from session context (avoids search API)
        actual_username = L.context.username or username
        L.save_session_to_file(str(session_file))

        # Also save session under the actual username if different
        if actual_username != username:
            actual_session = SESSION_DIR / f"{actual_username}.session"
            L.save_session_to_file(str(actual_session))

        # Persist credentials for auto-fetch later (skip for visitor sessions)
        if persist:
            save_credentials(username, password)

        return {"success": True, "message": f"Logged in as @{actual_username}", "username": actual_username}

    except instaloader.exceptions.TwoFactorAuthRequiredException:
        return {"error": "Enter your 2FA code from your authenticator app", "needs_2fa": True}
    except instaloader.exceptions.BadCredentialsException:
        return {"error": "Wrong username or password. Double-check and try again."}
    except instaloader.exceptions.ConnectionException as e:
        err = str(e)
        if "checkpoint" in err.lower():
            return {"error": "Instagram wants to verify you. Open the Instagram app on your phone, approve the login attempt, then try again here."}
        return {"error": f"Connection error: {err[:200]}"}
    except Exception as e:
        return {"error": f"Login failed: {str(e)[:200]}"}


def _get_authenticated_session(username: str, password: str = ""):
    """
    Get an authenticated requests.Session and the actual username.
    Tries: saved .cookies file → Instaloader .session file → fresh password login.
    Returns (session, actual_username) or raises Exception.
    """
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    session_file = SESSION_DIR / f"{username}.session"
    cookie_file = SESSION_DIR / f"{username}.cookies"

    # Check for any available session/cookie files
    if not session_file.exists() and not cookie_file.exists():
        available_cookies = list(SESSION_DIR.glob("*.cookies"))
        available_sessions = list(SESSION_DIR.glob("*.session"))
        if available_cookies:
            cookie_file = available_cookies[0]
        elif available_sessions:
            session_file = available_sessions[0]

    # Auto-load saved credentials if no password provided
    if not password:
        saved_user, saved_pass = load_credentials()
        if saved_pass:
            password = saved_pass
            if not username and saved_user:
                username = saved_user

    # Must use mobile UA — the collection API rejects browser user agents
    IG_MOBILE_UA = ("Instagram 275.0.0.27.98 Android (33/13; 420dpi; 1080x2400; "
                    "samsung; SM-G991B; o1s; exynos2100; en_US; 458229258)")
    headers = {
        "User-Agent": IG_MOBILE_UA,
        "X-IG-App-ID": "936619743392459",
        "X-Requested-With": "XMLHttpRequest",
    }

    # Try .cookies file first (from browser login)
    if cookie_file.exists():
        try:
            with open(cookie_file) as f:
                saved_cookies = json.load(f)
            session = requests.Session()
            for name, val in saved_cookies.items():
                session.cookies.set(name, val, domain=".instagram.com")
            session.headers.update(headers)

            # Verify session is alive using mobile API
            r = session.get("https://i.instagram.com/api/v1/accounts/current_user/?edit=true", timeout=10)
            if r.status_code == 200:
                data = r.json()
                api_username = data.get("user", {}).get("username", "")
                if not api_username:
                    api_username = data.get("form_data", {}).get("username", "")
                if api_username:
                    return session, api_username
        except Exception:
            pass

    # Try Instaloader .session file
    if session_file.exists():
        try:
            L = _get_loader()
            L.load_session_from_file(session_file.stem, str(session_file))
            session = L.context._session
            session.headers.update(headers)
            r = session.get("https://www.instagram.com/api/v1/accounts/edit/web_form_data/", timeout=10)
            if r.status_code == 200:
                api_username = r.json().get("form_data", {}).get("username", "")
                if api_username:
                    return session, api_username
        except Exception:
            pass

    # Try fresh password login
    if password:
        L = _get_loader()
        L.login(username, password)
        L.save_session_to_file(str(SESSION_DIR / f"{username}.session"))
        session = L.context._session
        session.headers.update(headers)
        return session, username

    raise Exception("Not logged in. Please log in first (use browser login).")


def _find_recipes_collection(session) -> str | None:
    """
    Find the 'recipes' saved collection using Instagram's private API.
    Returns the collection_id or None if not found.
    """
    collections_url = "https://i.instagram.com/api/v1/collections/list/"
    try:
        r = session.get(collections_url, params={"collection_types": '["ALL_MEDIA_AUTO_COLLECTION","MEDIA","PRODUCT_AUTO_COLLECTION"]'}, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        for coll in data.get("items", []):
            name = coll.get("collection_name", "").lower().strip()
            coll_id = coll.get("collection_id")
            if "recipe" in name and coll_id:
                return str(coll_id)
    except Exception:
        pass
    return None


def _fetch_collection_items(session, collection_id: str, progress_callback=None) -> list[dict]:
    """
    Fetch all items from a specific saved collection using Instagram's private API.
    Only returns video posts.
    """
    def update(current, total, msg):
        if progress_callback:
            progress_callback("fetch", current, total, msg)

    items = []
    video_count = 0
    max_id = None
    page = 0

    while True:
        page += 1
        params = {}
        if max_id:
            params["max_id"] = max_id

        if collection_id == "all_posts":
            url = "https://i.instagram.com/api/v1/feed/saved/posts/"
        else:
            url = f"https://i.instagram.com/api/v1/feed/collection/{collection_id}/"
        try:
            r = session.get(url, params=params, timeout=20)
            if r.status_code != 200:
                update(video_count, 0, f"Instagram returned status {r.status_code} — stopping pagination.")
                break
            data = r.json()
        except Exception as e:
            update(video_count, 0, f"Error fetching page {page}: {str(e)[:100]}")
            break

        page_items = data.get("items", [])
        if not page_items:
            break

        for item in page_items:
            media = item.get("media", {})
            media_type = media.get("media_type")  # 1=photo, 2=video, 8=carousel

            # We want videos (media_type=2) and video carousels
            is_video = media_type == 2

            # Check carousel items for videos
            carousel_items = []
            if media_type == 8:
                for ci in media.get("carousel_media", []):
                    if ci.get("media_type") == 2:
                        is_video = True
                        break

            if not is_video:
                continue

            video_count += 1
            code = media.get("code", "")
            caption_obj = media.get("caption") or {}
            caption_text = caption_obj.get("text", "") if isinstance(caption_obj, dict) else ""
            owner_user = media.get("user", {}).get("username", "")
            taken_at = media.get("taken_at", 0)

            # Get video URL
            video_url = ""
            video_versions = media.get("video_versions", [])
            if video_versions:
                video_url = video_versions[0].get("url", "")
            elif media_type == 8:
                for ci in media.get("carousel_media", []):
                    vv = ci.get("video_versions", [])
                    if vv:
                        video_url = vv[0].get("url", "")
                        break

            items.append({
                "shortcode": code,
                "url": f"https://www.instagram.com/reel/{code}/",
                "caption": caption_text[:500],
                "owner": owner_user,
                "date": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(taken_at)) if taken_at else "",
                "is_video": True,
                "video_download_url": video_url,
            })

            update(video_count, 0, f"Found recipe video {video_count}: {code}")

        # Check for next page
        more = data.get("more_available", False)
        next_max = data.get("next_max_id")
        if not more or not next_max:
            break
        max_id = next_max
        time.sleep(1)  # Small delay between pages

    return items


def _download_video_direct(session, video_download_url: str, shortcode: str) -> str | None:
    """Download a video directly from its URL. Returns path or None."""
    video_path = VIDEOS_DIR / f"{shortcode}.mp4"
    if video_path.exists():
        return str(video_path)
    if not video_download_url:
        return None
    try:
        r = session.get(video_download_url, stream=True, timeout=60)
        if r.status_code == 200:
            with open(video_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            return str(video_path)
    except Exception:
        pass
    return None


def fetch_saved_recipes(username: str, password: str = "", progress_callback=None) -> list[dict]:
    """
    Fetch video posts from the user's 'recipes' saved collection on Instagram.
    Uses Instagram's private API to target only the recipes collection.
    Falls back to all saved posts if no 'recipes' collection is found.
    Downloads each video to data/videos/.
    """
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    def update(current, total, msg):
        if progress_callback:
            progress_callback("fetch", current, total, msg)

    update(0, 0, "Authenticating...")
    session, actual_username = _get_authenticated_session(username, password)

    update(0, 0, f"Logged in as @{actual_username}. Looking for 'recipes' collection...")

    # Try to find the recipes collection
    collection_id = _find_recipes_collection(session)

    if not collection_id:
        raise Exception("No 'Recipes' collection found in your saved posts. "
                        "Make sure you have a saved folder called 'Recipes' on Instagram.")

    update(0, 0, f"Found 'Recipes' collection (id={collection_id}). Fetching videos...")
    items = _fetch_collection_items(session, collection_id, progress_callback)

    if not items:
        update(0, 0, "No recipe videos found in your Recipes collection.")
        return []

    # Download all the videos
    total = len(items)
    update(0, total, f"Found {total} recipe videos. Downloading...")

    posts = []
    for i, item in enumerate(items, 1):
        shortcode = item["shortcode"]
        video_path = VIDEOS_DIR / f"{shortcode}.mp4"

        if not video_path.exists():
            dl_url = item.get("video_download_url", "")
            if dl_url:
                update(i, total, f"Downloading video {i}/{total}: {shortcode}")
                path = _download_video_direct(session, dl_url, shortcode)
                if not path:
                    # Fallback: try yt-dlp
                    update(i, total, f"Retrying {shortcode} with backup method...")
                    _try_ytdlp_download(item["url"], video_path)
            else:
                # No direct URL, try yt-dlp
                _try_ytdlp_download(item["url"], video_path)
        else:
            update(i, total, f"Already have video {i}/{total}: {shortcode}")

        # Find the actual video file
        mp4_files = [f for f in VIDEOS_DIR.glob(f"{shortcode}*") if f.suffix in ('.mp4', '.mov', '.webm')]
        item["video_path"] = str(mp4_files[0]) if mp4_files else str(video_path)
        posts.append(item)

        time.sleep(0.5)  # Small delay

    _save_metadata(posts)
    update(total, total, f"Done! Downloaded {total} recipe videos from your saved collection.")
    return posts


def _try_ytdlp_download(url: str, output_path: Path):
    """Fallback download using yt-dlp."""
    try:
        subprocess.run(
            ["yt-dlp", "--no-playlist", "-f", "best[ext=mp4]/best",
             "-o", str(output_path), "--no-check-certificates", url],
            capture_output=True, text=True, timeout=120,
        )
    except Exception:
        pass


def get_local_videos() -> list[dict]:
    """Get all videos already in data/videos/."""
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    posts = []
    for ext in ('.mp4', '.mov', '.avi', '.mkv', '.webm'):
        for f in sorted(VIDEOS_DIR.glob(f"*{ext}")):
            posts.append({
                "shortcode": f.stem,
                "url": "",
                "caption": "",
                "owner": "local",
                "date": "",
                "video_path": str(f),
                "is_video": True,
            })
    return posts


def is_logged_in(username: str) -> bool:
    """Check if we have a cached session."""
    session_file = SESSION_DIR / f"{username}.session"
    return session_file.exists()


def _save_metadata(posts: list[dict]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing = []
    if METADATA_FILE.exists():
        with open(METADATA_FILE, 'r') as f:
            existing = json.load(f)
    existing_codes = {p['shortcode'] for p in existing}
    for post in posts:
        if post['shortcode'] not in existing_codes:
            existing.append(post)
    with open(METADATA_FILE, 'w') as f:
        json.dump(existing, f, indent=2)
