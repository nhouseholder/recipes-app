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


def login(username: str, password: str, two_factor_code: str = "") -> dict:
    """
    Log in to Instagram. Caches the session for future use.
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

        # Persist credentials for auto-fetch later
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


def fetch_saved_recipes(username: str, password: str = "", progress_callback=None) -> list[dict]:
    """
    Fetch all video posts from the user's saved posts on Instagram.
    Downloads each video to data/videos/.
    """
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    L = _get_loader()
    session_file = SESSION_DIR / f"{username}.session"

    # Also check for sessions saved under alternative credentials (email, phone)
    if not session_file.exists():
        # Try any session file we have
        available_sessions = list(SESSION_DIR.glob("*.session"))
        if available_sessions:
            session_file = available_sessions[0]

    # Load session
    if session_file.exists():
        try:
            L.load_session_from_file(session_file.stem, str(session_file))
        except Exception:
            if password:
                L.login(username, password)
                L.save_session_to_file(str(session_file))
            else:
                raise Exception("Session expired. Please log in again.")
    elif password:
        L.login(username, password)
        L.save_session_to_file(str(session_file))
    else:
        raise Exception("Not logged in. Please log in first.")

    def update(current, total, msg):
        if progress_callback:
            progress_callback("fetch", current, total, msg)

    # Get the actual username from the session context (avoids API lookups)
    actual_username = L.context.username
    if not actual_username:
        actual_username = username

    update(0, 0, f"Scanning @{actual_username}'s saved posts for recipe videos...")

    # Use get_saved_posts from the Profile — but get profile via context user_id
    # to avoid the search endpoint that requires extra permissions
    profile = None
    for attempt in range(MAX_RETRIES):
        try:
            user_id = L.context.user_id
            profile = instaloader.Profile.from_id(L.context, user_id)
            break
        except (instaloader.exceptions.ConnectionException,
                instaloader.exceptions.QueryReturnedBadRequestException) as e:
            err = str(e).lower()
            if "401" in err or "429" in err or "wait" in err or "please wait" in err:
                wait = INITIAL_BACKOFF * (2 ** attempt)
                update(0, 0, f"Instagram says wait — retrying in {wait}s ({attempt+1}/{MAX_RETRIES})...")
                time.sleep(wait)
            else:
                raise
        except Exception:
            profile = instaloader.Profile.from_username(L.context, actual_username)
            break

    if profile is None:
        raise Exception("Instagram rate limit. Please wait 10-15 minutes and try again.")

    posts = []
    count = 0
    video_count = 0

    try:
        for post in profile.get_saved_posts():
            count += 1

            if not post.is_video:
                if count % 25 == 0:
                    update(video_count, 0, f"Scanning... {count} posts checked, {video_count} videos found so far")
                continue

            video_count += 1
            shortcode = post.shortcode

            post_data = {
                "shortcode": shortcode,
                "url": f"https://www.instagram.com/reel/{shortcode}/",
                "caption": (post.caption or "")[:500],
                "owner": post.owner_username,
                "date": post.date_utc.isoformat() if post.date_utc else "",
                "is_video": True,
            }

            # Download video
            video_path = VIDEOS_DIR / f"{shortcode}.mp4"
            if not video_path.exists():
                try:
                    L.download_post(post, target=str(VIDEOS_DIR))
                    update(video_count, 0, f"Downloaded video {video_count}: {shortcode}")
                except Exception as e:
                    update(video_count, 0, f"Retrying {shortcode} with backup method...")
                    _try_ytdlp_download(post_data["url"], video_path)
            else:
                update(video_count, 0, f"Already have video {video_count}: {shortcode}")

            # Find the actual video file (instaloader may name it slightly differently)
            mp4_files = [f for f in VIDEOS_DIR.glob(f"{shortcode}*") if f.suffix in ('.mp4', '.mov', '.webm')]
            post_data["video_path"] = str(mp4_files[0]) if mp4_files else str(video_path)

            posts.append(post_data)
            time.sleep(2)  # Rate limiting — 2 seconds between posts

    except instaloader.exceptions.LoginRequiredException:
        raise Exception("Session expired. Please log in again.")
    except instaloader.exceptions.QueryReturnedBadRequestException:
        update(video_count, video_count, f"Instagram rate limited us. Got {video_count} videos so far — that's enough to start!")
    except Exception as e:
        if video_count == 0:
            raise
        update(video_count, video_count, f"Got {video_count} videos before stopping. Good enough to start!")

    _save_metadata(posts)
    update(video_count, video_count, f"Done! Found {video_count} recipe videos from your saved posts.")
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
