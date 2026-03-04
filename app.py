"""
Nick's Recipe Extractor — Flask Backend
Simple flow: Log in → Fetch saved videos → Transcribe → Extract recipes
Includes: Auto-check for new videos, weekly grocery list emails, background scheduler.
"""

import os
import json
import threading
import logging
import uuid
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_from_directory
from dotenv import load_dotenv

load_dotenv()

from flask_cors import CORS
from instagram_fetcher import (
    login, login_from_browser, login_with_sessionid,
    fetch_saved_recipes, get_local_videos, is_logged_in,
    save_credentials, load_credentials,
    _get_authenticated_session, _download_video_direct,
)
from transcriber import transcribe_video
from recipe_extractor import (
    extract_recipe_with_openai,
    extract_recipe_local,
    save_recipes,
    load_recipes,
)
from ai_extractor import extract_recipe_ai, reextract_all_recipes, create_recipe_from_caption
from grocery_list import pick_weekly_recipe, build_grocery_list, format_grocery_list_text, save_to_history
from notifier import send_weekly_grocery_email, send_test_email
from scheduler import start_scheduler, stop_scheduler, get_scheduler_status

app = Flask(__name__)
CORS(app, expose_headers=["X-Session-ID"])

# ── Per-visitor session store ──
# Each visitor gets independent Instagram auth via X-Session-ID header.
# The server owner's credentials remain in config.json for Try It / background tasks.
visitor_sessions = {}  # {session_id: {"username": str, "logged_in": bool}}

def _get_visitor_id() -> str:
    """Get the visitor's session ID from the X-Session-ID header."""
    return request.headers.get("X-Session-ID", "")

def _get_visitor_session() -> dict:
    """Get or create the current visitor's session state."""
    vid = _get_visitor_id()
    if not vid:
        return {}
    if vid not in visitor_sessions:
        visitor_sessions[vid] = {"username": "", "logged_in": False}
    return visitor_sessions[vid]

def _set_visitor_auth(username: str, logged_in: bool = True):
    """Store auth state for the current visitor."""
    vid = _get_visitor_id()
    if vid:
        visitor_sessions[vid] = {"username": username, "logged_in": logged_in}

DATA_DIR = Path(__file__).parent / "data"
VIDEOS_DIR = DATA_DIR / "videos"
RECIPES_FILE = DATA_DIR / "recipes.json"
CONFIG_FILE = DATA_DIR / "config.json"

# Live processing state (shared with frontend via polling)
state = {
    "active": False,
    "phase": "",        # login, fetch, transcribe, extract, done, error
    "current": 0,
    "total": 0,
    "message": "",
    "errors": [],
}


def _update(phase, current, total, message):
    state["phase"] = phase
    state["current"] = current
    state["total"] = total
    state["message"] = message


def _save_config(data: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing = _load_config()
    existing.update(data)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(existing, f, indent=2)


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


# ═══════════════════════════════════════════════════════════
#  Page Routes
# ═══════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


# ═══════════════════════════════════════════════════════════
#  API: Auth
# ═══════════════════════════════════════════════════════════

@app.route("/api/login", methods=["POST"])
def api_login():
    """Log in to Instagram (per-visitor session)."""
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    two_fa = data.get("two_factor_code", "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    # persist=False so visitor logins don't overwrite the server owner's saved credentials
    result = login(username, password, two_fa, persist=False)

    if result.get("success"):
        actual_username = result.get("username", username)
        _set_visitor_auth(actual_username, True)

    return jsonify(result)


@app.route("/api/login-browser", methods=["POST"])
def api_login_browser():
    """Log in using cookies from user's browser (Chrome/Firefox/Safari)."""
    data = request.json or {}
    browser = data.get("browser", "auto")

    result = login_from_browser(browser)

    if result.get("success"):
        actual_username = result.get("username", "")
        _set_visitor_auth(actual_username, True)

    return jsonify(result)


@app.route("/api/login-sessionid", methods=["POST"])
def api_login_sessionid():
    """Log in using a manually-provided Instagram sessionid cookie."""
    data = request.json or {}
    sessionid = data.get("sessionid", "").strip()

    if not sessionid:
        return jsonify({"error": "Session ID is required"}), 400

    result = login_with_sessionid(sessionid)

    if result.get("success"):
        actual_username = result.get("username", "")
        _set_visitor_auth(actual_username, True)

    return jsonify(result)


@app.route("/api/auth-status")
def api_auth_status():
    """Check if the current visitor is logged in (per-session)."""
    visitor = _get_visitor_session()
    username = visitor.get("username", "")
    logged_in = visitor.get("logged_in", False) and bool(username)

    # Verify the session file still exists if they claim to be logged in
    if logged_in and not is_logged_in(username):
        logged_in = False

    videos = get_local_videos()
    recipes = load_recipes()
    config = _load_config()

    return jsonify({
        "username": username if logged_in else "",
        "logged_in": logged_in,
        "videos_count": len(videos),
        "recipes_count": len([r for r in recipes if "error" not in r]),
        "has_openai_key": bool(config.get("openai_api_key") or os.getenv("OPENAI_API_KEY")),
    })


@app.route("/api/disconnect", methods=["POST"])
def api_disconnect():
    """Disconnect the current visitor's Instagram session."""
    vid = _get_visitor_id()
    if vid and vid in visitor_sessions:
        del visitor_sessions[vid]
    return jsonify({"success": True, "message": "Disconnected"})


# ═══════════════════════════════════════════════════════════
#  API: The Big Button — Fetch + Process Everything
# ═══════════════════════════════════════════════════════════

@app.route("/api/fetch-and-process", methods=["POST"])
def api_fetch_and_process():
    """
    The main pipeline:
    1. Fetch all saved recipe videos from Instagram
    2. Transcribe each with Whisper
    3. Extract simplified recipes
    """
    if state["active"]:
        return jsonify({"error": "Already processing. Please wait."}), 409

    # Use per-visitor session username if available, fall back to global config
    visitor = _get_visitor_session()
    username = visitor.get("username", "") if visitor.get("logged_in") else ""
    if not username:
        config = _load_config()
        username = config.get("instagram_username", "")
    if not username:
        return jsonify({"error": "Not logged in. Connect your Instagram account first."}), 401

    config = _load_config()

    def run():
        state["active"] = True
        state["errors"] = []
        model_size = config.get("whisper_model", os.getenv("WHISPER_MODEL", "base"))
        api_key = config.get("openai_api_key", os.getenv("OPENAI_API_KEY", ""))

        try:
            # ── Phase 1: Fetch videos from Instagram ─────────
            _update("fetch", 0, 0, "Connecting to Instagram and scanning your saved posts...")

            def on_fetch_progress(phase, current, total, msg):
                _update("fetch", current, total, msg)

            posts = fetch_saved_recipes(username, progress_callback=on_fetch_progress)

            if not posts:
                # Check if we have local videos already
                posts = get_local_videos()

            if not posts:
                _update("error", 0, 0, "No videos found in your saved posts.")
                state["active"] = False
                return

            # ── Phase 2 & 3: Transcribe + Extract ────────────
            total = len(posts)
            recipes = load_recipes()
            existing_ids = {r.get("source_id") for r in recipes}

            for i, video in enumerate(posts):
                vid_id = video["shortcode"]

                if vid_id in existing_ids:
                    _update("transcribe", i + 1, total, f"Skipping {vid_id} (already processed)")
                    continue

                # Transcribe
                _update("transcribe", i + 1, total, f"Transcribing video {i + 1} of {total}...")
                video_path = video.get("video_path", str(VIDEOS_DIR / f"{vid_id}.mp4"))

                transcript = transcribe_video(video_path, model_size)
                if transcript.get("error") or not transcript.get("text"):
                    state["errors"].append(f"{vid_id}: {transcript.get('error', 'empty transcript')}")
                    continue

                # Extract recipe
                _update("extract", i + 1, total, f"Creating recipe {i + 1} of {total}...")
                caption = video.get("caption", "")

                # Try AI extraction first (Cloudflare Workers AI), fall back to local
                try:
                    recipe = extract_recipe_ai(transcript["text"], caption,
                                              source_id=vid_id,
                                              source_url=video.get("url", ""))
                except Exception as ai_err:
                    print(f"[AI] Fallback to local: {ai_err}")
                    if api_key:
                        recipe = extract_recipe_with_openai(transcript["text"], caption, api_key)
                    else:
                        recipe = extract_recipe_local(transcript["text"], caption)
                    recipe["source_id"] = vid_id
                    recipe["source_url"] = video.get("url", "")
                    recipe["transcript"] = transcript["text"][:1000]

                if "error" in recipe:
                    state["errors"].append(f"{vid_id}: {recipe['error']}")
                    continue

                recipes.append(recipe)
                save_recipes(recipes)

            done_count = len([r for r in recipes if "error" not in r])
            _update("done", total, total, f"All done! You have {done_count} recipes ready.")

        except Exception as e:
            state["errors"].append(str(e))
            _update("error", 0, 0, f"Error: {str(e)[:200]}")
        finally:
            state["active"] = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"message": "Started! This will take a few minutes..."})


@app.route("/api/process-local", methods=["POST"])
def api_process_local():
    """Process videos already in the data/videos folder (no Instagram fetch)."""
    if state["active"]:
        return jsonify({"error": "Already processing"}), 409

    config = _load_config()

    def run():
        state["active"] = True
        state["errors"] = []
        model_size = config.get("whisper_model", os.getenv("WHISPER_MODEL", "base"))
        api_key = config.get("openai_api_key", os.getenv("OPENAI_API_KEY", ""))

        try:
            posts = get_local_videos()
            if not posts:
                _update("error", 0, 0, "No videos in data/videos/ folder.")
                state["active"] = False
                return

            total = len(posts)
            recipes = load_recipes()
            existing_ids = {r.get("source_id") for r in recipes}

            for i, video in enumerate(posts):
                vid_id = video["shortcode"]
                if vid_id in existing_ids:
                    continue

                _update("transcribe", i + 1, total, f"Transcribing video {i + 1} of {total}...")
                transcript = transcribe_video(video["video_path"], model_size)
                if transcript.get("error") or not transcript.get("text"):
                    state["errors"].append(f"{vid_id}: transcription failed")
                    continue

                _update("extract", i + 1, total, f"Creating recipe {i + 1} of {total}...")
                caption = video.get("caption", "")

                # Try AI extraction first (Cloudflare Workers AI), fall back to local
                try:
                    recipe = extract_recipe_ai(transcript["text"], caption,
                                              source_id=vid_id,
                                              source_url=video.get("url", ""))
                except Exception as ai_err:
                    print(f"[AI] Fallback to local: {ai_err}")
                    if api_key:
                        recipe = extract_recipe_with_openai(transcript["text"], caption, api_key)
                    else:
                        recipe = extract_recipe_local(transcript["text"], caption)
                    recipe["source_id"] = vid_id
                    recipe["source_url"] = video.get("url", "")
                    recipe["transcript"] = transcript["text"][:1000]

                if "error" in recipe:
                    state["errors"].append(f"{vid_id}: {recipe['error']}")
                    continue

                recipes.append(recipe)
                save_recipes(recipes)

            done_count = len([r for r in recipes if "error" not in r])
            _update("done", total, total, f"Done! {done_count} recipes ready.")
        except Exception as e:
            state["errors"].append(str(e))
            _update("error", 0, 0, str(e)[:200])
        finally:
            state["active"] = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"message": "Processing local videos..."})


# ═══════════════════════════════════════════════════════════
#  API: Recipes CRUD
# ═══════════════════════════════════════════════════════════

@app.route("/api/recipes")
def api_recipes():
    recipes = load_recipes()
    return jsonify({"recipes": [r for r in recipes if "error" not in r], "count": len(recipes)})


@app.route("/api/recipes/<int:idx>", methods=["DELETE"])
def api_delete_recipe(idx):
    recipes = load_recipes()
    if 0 <= idx < len(recipes):
        removed = recipes.pop(idx)
        save_recipes(recipes)
        return jsonify({"message": f"Deleted: {removed.get('title', 'recipe')}"})
    return jsonify({"error": "Not found"}), 404


@app.route("/api/status")
def api_status():
    return jsonify(state)


@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    config = _load_config()
    return jsonify({
        "openai_api_key_set": bool(config.get("openai_api_key")),
        "whisper_model": config.get("whisper_model", "base"),
        "smtp_email": config.get("smtp_email", ""),
        "smtp_password_set": bool(config.get("smtp_password")),
        "notification_email": config.get("notification_email", config.get("smtp_email", "")),
        "weekly_email_enabled": config.get("weekly_email_enabled", True),
        "auto_check_enabled": config.get("auto_check_enabled", True),
        "check_interval_hours": config.get("check_interval_hours", 6),
        # Frontend settings
        "phone": config.get("sms_phone", ""),
        "email": config.get("notification_email", config.get("smtp_email", "")),
        "delivery_method": config.get("delivery_method", "imessage"),
        "weekly_enabled": config.get("weekly_email_enabled", True),
        "weekly_day": config.get("weekly_day", "saturday"),
        "weekly_time": config.get("weekly_time", "09:00"),
        "recipes_per_week": config.get("recipes_per_week", 3),
    })


@app.route("/api/settings", methods=["POST", "PUT"])
def api_save_settings():
    data = request.json
    updates = {}
    for key in ["openai_api_key", "whisper_model",
                 "smtp_email", "smtp_password", "notification_email",
                 "weekly_email_enabled", "auto_check_enabled", "check_interval_hours",
                 "delivery_method", "weekly_day", "weekly_time", "recipes_per_week"]:
        if key in data:
            updates[key] = data[key]
    # Map frontend field names to config keys
    if "phone" in data:
        updates["sms_phone"] = data["phone"]
    if "email" in data:
        updates["notification_email"] = data["email"]
    if "weekly_enabled" in data:
        updates["weekly_email_enabled"] = data["weekly_enabled"]
    _save_config(updates)
    return jsonify({"message": "Settings saved!"})


@app.route("/api/videos")
def api_videos():
    return jsonify({"videos": get_local_videos()})


@app.route("/videos/<path:filename>")
def serve_video(filename):
    return send_from_directory(str(VIDEOS_DIR), filename)


@app.route("/api/cards/<path:filename>")
def serve_card(filename):
    """Serve recipe card images from data/cards/."""
    cards_dir = DATA_DIR / "cards"
    return send_from_directory(str(cards_dir), filename)


# ═══════════════════════════════════════════════════════════
#  API: Grocery List & Weekly Pick
# ═══════════════════════════════════════════════════════════

@app.route("/api/grocery/pick", methods=["POST"])
def api_grocery_pick():
    """Pick a random recipe and build its grocery list."""
    recipe = pick_weekly_recipe()
    if not recipe:
        return jsonify({"error": "No recipes available. Process some videos first!"}), 404

    grocery = build_grocery_list(recipe)
    return jsonify({"recipe": recipe, "grocery": grocery})


@app.route("/api/grocery/build/<int:idx>", methods=["GET", "POST"])
def api_grocery_build(idx):
    """Build grocery list for a specific recipe by index."""
    recipes = load_recipes()
    valid = [r for r in recipes if "error" not in r]
    if idx < 0 or idx >= len(valid):
        return jsonify({"error": "Recipe not found"}), 404

    grocery = build_grocery_list(valid[idx])
    return jsonify({"recipe": valid[idx], "grocery": grocery})


@app.route("/api/grocery/send-now", methods=["POST"])
def api_grocery_send_now():
    """Pick a recipe and send the grocery list email right now."""
    recipe = pick_weekly_recipe()
    if not recipe:
        return jsonify({"error": "No recipes available."}), 404

    grocery = build_grocery_list(recipe)
    result = send_weekly_grocery_email(grocery)

    if result.get("success"):
        save_to_history(recipe, grocery)
        return jsonify({"message": f"Grocery list for '{recipe['title']}' sent!", "recipe": recipe, "grocery": grocery})
    else:
        return jsonify({"error": result.get("error", "Failed to send")}), 500


# ═══════════════════════════════════════════════════════════
#  API: Notifications
# ═══════════════════════════════════════════════════════════

@app.route("/api/notifications/settings", methods=["GET"])
def api_get_notification_settings():
    config = _load_config()
    return jsonify({
        "smtp_email": config.get("smtp_email", ""),
        "notification_email": config.get("notification_email", config.get("smtp_email", "")),
        "smtp_configured": bool(config.get("smtp_email") and config.get("smtp_password")),
        "weekly_email_enabled": config.get("weekly_email_enabled", True),
        "auto_check_enabled": config.get("auto_check_enabled", True),
        "check_interval_hours": config.get("check_interval_hours", 6),
    })


@app.route("/api/notifications/settings", methods=["POST"])
def api_save_notification_settings():
    data = request.json
    updates = {}
    for key in ["smtp_email", "smtp_password", "notification_email",
                 "weekly_email_enabled", "auto_check_enabled", "check_interval_hours"]:
        if key in data:
            updates[key] = data[key]
    _save_config(updates)
    return jsonify({"message": "Notification settings saved!"})


@app.route("/api/notifications/test", methods=["POST"])
def api_test_email():
    result = send_test_email()
    if result.get("success"):
        return jsonify({"message": "Test email sent! Check your inbox."})
    return jsonify({"error": result.get("error", "Failed")}), 500


@app.route("/api/sms/send-recipes", methods=["POST"])
def api_sms_send_recipes():
    """Text random recipes to phone."""
    from notifier import send_recipe_texts
    data = request.json or {}
    count = data.get("count", 3)
    result = send_recipe_texts(count)
    if result.get("success"):
        return jsonify(result)
    return jsonify(result), 500


@app.route("/api/recipe-cards/send", methods=["POST"])
def api_send_recipe_cards():
    """Generate beautiful recipe card JPGs and email them."""
    from notifier import send_recipe_cards
    data = request.json or {}
    count = data.get("count", 3)
    result = send_recipe_cards(count)
    if result.get("success"):
        return jsonify(result)
    return jsonify(result), 500


@app.route("/api/recipe-cards/text", methods=["POST"])
def api_text_recipe_cards():
    """Generate recipe card JPGs and send via iMessage."""
    from notifier import imessage_recipe_cards
    data = request.json or {}
    count = data.get("count", 3)
    recipe_index = data.get("recipe_index", None)
    phone = data.get("phone", None)
    result = imessage_recipe_cards(count, recipe_index=recipe_index, phone=phone)
    if result.get("success"):
        return jsonify(result)
    return jsonify(result), 500


@app.route("/api/recipe-text/send", methods=["POST"])
def api_text_recipe_plain():
    """Send recipes as plain text via iMessage."""
    from notifier import imessage_recipe_text
    data = request.json or {}
    count = data.get("count", 3)
    phone = data.get("phone", None)
    result = imessage_recipe_text(count, phone=phone)
    if result.get("success"):
        return jsonify(result)
    return jsonify(result), 500


# ═══════════════════════════════════════════════════════════
#  API: Try It — One-off recipe from any Instagram URL
# ═══════════════════════════════════════════════════════════

# Per-job state keyed by job_id
try_jobs = {}


@app.route("/api/try-recipe", methods=["POST"])
def api_try_recipe():
    """
    Accept an Instagram video URL + phone number.
    Downloads video → Whisper transcribe → Llama extract → generate card → iMessage.
    Returns a job_id for status polling.
    """
    data = request.json or {}
    url = data.get("url", "").strip()
    phone = data.get("phone", "").strip()

    if not url:
        return jsonify({"error": "Instagram URL is required"}), 400
    if not phone:
        return jsonify({"error": "Phone number is required"}), 400

    # Basic URL validation
    if "instagram.com" not in url and "instagr.am" not in url:
        return jsonify({"error": "Please enter a valid Instagram URL"}), 400

    # Format phone
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        phone_formatted = f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        phone_formatted = f"+{digits}"
    else:
        phone_formatted = f"+{digits}"

    job_id = uuid.uuid4().hex[:12]
    try_jobs[job_id] = {
        "status": "queued",
        "phase": "starting",
        "message": "Starting...",
        "recipe": None,
        "error": None,
    }

    def run_try_recipe():
        import re
        import requests as req
        job = try_jobs[job_id]

        try:
            # ── Phase 1: Download video via Instagram API ─
            job["phase"] = "downloading"
            job["status"] = "running"
            job["message"] = "Downloading video from Instagram..."

            # Extract shortcode from URL
            shortcode_match = re.search(r'(?:reel|p|reels)/([A-Za-z0-9_-]+)', url)
            shortcode = shortcode_match.group(1) if shortcode_match else uuid.uuid4().hex[:11]

            video_path = VIDEOS_DIR / f"try_{shortcode}.mp4"

            # Step A: Get media_id + title from Instagram oembed (public, no auth needed)
            oembed_url = f"https://www.instagram.com/api/v1/oembed/?url={url}"
            oembed_title = ""
            try:
                oembed_r = req.get(oembed_url, timeout=10)
                if oembed_r.status_code == 200:
                    oembed_data = oembed_r.json()
                    oembed_title = oembed_data.get("title", "")
            except Exception:
                pass

            if not video_path.exists():
                if not oembed_title:
                    # Retry oembed — we need media_id
                    try:
                        oembed_r = req.get(oembed_url, timeout=10)
                    except Exception:
                        pass
                if not hasattr(oembed_r, 'status_code') or oembed_r.status_code != 200:
                    job["status"] = "error"
                    job["phase"] = "error"
                    job["error"] = "Couldn't find this post on Instagram. Make sure the URL is correct and the post is public."
                    job["message"] = job["error"]
                    return

                raw_media_id = oembed_r.json().get("media_id", "")
                media_id = raw_media_id.split("_")[0] if "_" in raw_media_id else raw_media_id
                if not media_id:
                    job["status"] = "error"
                    job["phase"] = "error"
                    job["error"] = "Couldn't get media info from Instagram."
                    job["message"] = job["error"]
                    return

                # Step B: Get authenticated session and fetch video URL via mobile API
                saved_user, saved_pass = load_credentials()
                session, _ = _get_authenticated_session(saved_user or "", saved_pass or "")

                info_r = session.get(f"https://i.instagram.com/api/v1/media/{media_id}/info/", timeout=15)
                video_download_url = ""
                if info_r.status_code == 200:
                    for item in info_r.json().get("items", []):
                        vv = item.get("video_versions", [])
                        if vv:
                            video_download_url = vv[0].get("url", "")
                            break
                        for ci in item.get("carousel_media", []):
                            cvv = ci.get("video_versions", [])
                            if cvv:
                                video_download_url = cvv[0].get("url", "")
                                break
                        if video_download_url:
                            break

                if video_download_url:
                    dl_result = _download_video_direct(session, video_download_url, f"try_{shortcode}")
                    if dl_result:
                        video_path = Path(dl_result)

                if not video_path.exists():
                    job["status"] = "error"
                    job["phase"] = "error"
                    job["error"] = "Couldn't download this video. It may not be a video or may be private."
                    job["message"] = job["error"]
                    return

            # ── Phase 2: Transcribe (use 'small' model for better quality) ─
            job["phase"] = "transcribing"
            job["message"] = "Transcribing audio with Whisper..."

            transcript = transcribe_video(str(video_path), "small")

            if transcript.get("error") or not transcript.get("text"):
                job["status"] = "error"
                job["phase"] = "error"
                job["error"] = "Couldn't transcribe the audio. The video may not have speech."
                job["message"] = job["error"]
                return

            # ── Phase 3: Extract recipe with Llama 3.3 70B ─
            job["phase"] = "extracting"
            job["message"] = "AI is creating your recipe with Llama 3.3 70B..."

            # Use oembed title as caption context for better AI extraction
            caption = oembed_title if oembed_title else ""
            try:
                recipe = extract_recipe_ai(transcript["text"], caption,
                                          source_id=f"try_{shortcode}",
                                          source_url=url)
            except Exception:
                recipe = extract_recipe_local(transcript["text"], caption)
                recipe["source_id"] = f"try_{shortcode}"
                recipe["source_url"] = url

            # If transcript-based extraction failed but we have a caption,
            # retry with caption-only prompt (for music/text-overlay videos)
            if recipe.get("error") and caption:
                job["message"] = "Transcript unclear — using video caption to create recipe..."
                try:
                    from ai_extractor import _clean_recipe
                    caption_recipe = create_recipe_from_caption(caption)
                    caption_recipe = _clean_recipe(caption_recipe)
                    if not caption_recipe.get("error"):
                        caption_recipe["source_id"] = f"try_{shortcode}"
                        caption_recipe["source_url"] = url
                        caption_recipe["transcript"] = transcript["text"][:500]
                        recipe = caption_recipe
                except Exception:
                    pass

            if recipe.get("error"):
                job["status"] = "error"
                job["phase"] = "error"
                job["error"] = "This video doesn't appear to contain a recipe."
                job["message"] = job["error"]
                return

            recipe["transcript"] = transcript["text"][:1000]
            job["recipe"] = recipe

            # ── Phase 4: Generate recipe card ────────────
            job["phase"] = "generating"
            job["message"] = "Generating your beautiful recipe card..."

            from recipe_card import generate_recipe_card
            grocery = build_grocery_list(recipe)
            card_path = generate_recipe_card(recipe, grocery)

            # ── Phase 5: Send via iMessage ───────────────
            job["phase"] = "sending"
            job["message"] = f"Texting recipe card to {phone}..."

            from notifier import _send_imessage_text
            from urllib.parse import quote

            CARDS_BASE_URL = "https://recipecardsai.pages.dev/api/cards"
            filename = Path(card_path).name
            card_url = f"{CARDS_BASE_URL}/{quote(filename)}"
            title = recipe.get("title", "Your Recipe")

            msg = f"🍳 {title}\n\nHere's your recipe card!\n{card_url}"
            success = _send_imessage_text(phone_formatted, msg)

            if success:
                job["status"] = "done"
                job["phase"] = "done"
                job["message"] = f"Recipe card for \"{title}\" sent to {phone}!"
            else:
                job["status"] = "error"
                job["phase"] = "error"
                job["error"] = "Recipe created but failed to send via iMessage. The server must be running on a Mac with Messages.app."
                job["message"] = job["error"]

        except Exception as e:
            job["status"] = "error"
            job["phase"] = "error"
            job["error"] = f"Something went wrong: {str(e)[:200]}"
            job["message"] = job["error"]

    threading.Thread(target=run_try_recipe, daemon=True).start()
    return jsonify({"job_id": job_id, "message": "Processing started!"})


@app.route("/api/try-recipe/<job_id>")
def api_try_recipe_status(job_id):
    """Poll the status of a try-recipe job."""
    job = try_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


# ═══════════════════════════════════════════════════════════
#  API: Scheduler
# ═══════════════════════════════════════════════════════════

@app.route("/api/scheduler/status")
def api_scheduler_status():
    return jsonify(get_scheduler_status())


@app.route("/api/scheduler/check-now", methods=["POST"])
def api_scheduler_check_now():
    """Manually trigger a check for new videos."""
    from scheduler import check_for_new_videos
    threading.Thread(target=check_for_new_videos, daemon=True).start()
    return jsonify({"message": "Checking for new videos in the background..."})


@app.route("/api/scheduler/send-weekly", methods=["POST"])
def api_scheduler_send_weekly():
    """Manually trigger the weekly grocery email."""
    from scheduler import send_weekly_grocery_list
    threading.Thread(target=send_weekly_grocery_list, daemon=True).start()
    return jsonify({"message": "Sending weekly grocery list..."})


# ═══════════════════════════════════════════════════════════
#  AI Re-extraction
# ═══════════════════════════════════════════════════════════

reextract_state = {"active": False, "current": 0, "total": 0, "message": "", "results": None}

@app.route("/api/reextract", methods=["POST"])
def api_reextract():
    """Re-extract all recipes using Cloudflare Workers AI (Llama 3.3 70B)."""
    if reextract_state["active"]:
        return jsonify({"error": "Re-extraction already in progress"}), 409

    def run_reextract():
        reextract_state["active"] = True
        reextract_state["current"] = 0
        reextract_state["results"] = None
        try:
            def progress(current, total, title):
                reextract_state["current"] = current
                reextract_state["total"] = total
                reextract_state["message"] = f"Processing {current}/{total}: {title[:40]}"

            result = reextract_all_recipes(RECIPES_FILE, progress_callback=progress)
            reextract_state["results"] = {
                "total": result["total"],
                "improved": result["improved"],
                "failed": result["failed"],
                "removed": result["removed"],
                "recipe_count": len(result.get("recipes", [])),
            }
            reextract_state["message"] = f"Done! {result['improved']} improved, {result['failed']} failed, {result['removed']} removed"
        except Exception as e:
            reextract_state["message"] = f"Error: {str(e)[:200]}"
            reextract_state["results"] = {"error": str(e)[:200]}
        finally:
            reextract_state["active"] = False

    threading.Thread(target=run_reextract, daemon=True).start()
    return jsonify({"message": "Re-extraction started with Llama 3.3 70B..."})


@app.route("/api/reextract/status")
def api_reextract_status():
    """Check re-extraction progress."""
    return jsonify(reextract_state)


# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    # Start background scheduler
    start_scheduler()

    print("\n" + "=" * 55)
    print("  🍳 Nick's Recipe Extractor")
    print("=" * 55)
    print("  Open: http://localhost:5050")
    print("  📅 Weekly grocery emails: every Saturday 9 AM")
    print("  🔄 Auto-check for new recipes: every 6 hours")
    print("=" * 55 + "\n")

    app.run(debug=True, port=5050, host="0.0.0.0", use_reloader=False)
