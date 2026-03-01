"""
Background Scheduler
Runs periodic tasks:
  1. Check Instagram for new saved recipe videos (every 6 hours)
  2. Pick a random recipe + send grocery list email (every Saturday at 9 AM)
"""

import json
import time
import threading
import logging
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
CONFIG_FILE = DATA_DIR / "config.json"
SCHEDULER_STATE_FILE = DATA_DIR / "scheduler_state.json"

logger = logging.getLogger("scheduler")

_scheduler_thread = None
_running = False


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def _load_scheduler_state() -> dict:
    if SCHEDULER_STATE_FILE.exists():
        with open(SCHEDULER_STATE_FILE) as f:
            return json.load(f)
    return {}


def _save_scheduler_state(state: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SCHEDULER_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def check_for_new_videos():
    """
    Check Instagram for new saved videos and process any new ones.
    Called periodically by the scheduler.
    """
    config = _load_config()
    username = config.get("instagram_username", "")
    if not username:
        logger.info("[Scheduler] No Instagram username configured, skipping check.")
        return

    from instagram_fetcher import fetch_saved_recipes, is_logged_in
    if not is_logged_in(username):
        logger.info("[Scheduler] Not logged in, skipping check.")
        return

    logger.info(f"[Scheduler] Checking for new saved videos for @{username}...")

    try:
        posts = fetch_saved_recipes(username)
        if not posts:
            logger.info("[Scheduler] No new videos found.")
            return

        # Process any unprocessed videos
        from transcriber import transcribe_video
        from recipe_extractor import (
            extract_recipe_with_openai, extract_recipe_local,
            save_recipes, load_recipes,
        )
        import os

        model_size = config.get("whisper_model", os.getenv("WHISPER_MODEL", "base"))
        api_key = config.get("openai_api_key", os.getenv("OPENAI_API_KEY", ""))

        recipes = load_recipes()
        existing_ids = {r.get("source_id") for r in recipes}
        new_count = 0

        for video in posts:
            vid_id = video["shortcode"]
            if vid_id in existing_ids:
                continue

            logger.info(f"[Scheduler] Processing new video: {vid_id}")
            video_path = video.get("video_path", "")
            if not video_path or not Path(video_path).exists():
                continue

            transcript = transcribe_video(video_path, model_size)
            if transcript.get("error") or not transcript.get("text"):
                continue

            caption = video.get("caption", "")
            if api_key:
                recipe = extract_recipe_with_openai(transcript["text"], caption, api_key)
            else:
                recipe = extract_recipe_local(transcript["text"], caption)

            if "error" not in recipe:
                recipe["source_id"] = vid_id
                recipe["source_url"] = video.get("url", "")
                recipe["transcript"] = transcript["text"][:1000]
                recipes.append(recipe)
                save_recipes(recipes)
                new_count += 1
                logger.info(f"[Scheduler] New recipe added: {recipe.get('title', vid_id)}")

        if new_count:
            logger.info(f"[Scheduler] Added {new_count} new recipe(s)!")
        else:
            logger.info("[Scheduler] No new unprocessed videos.")

        # Update state
        state = _load_scheduler_state()
        state["last_check"] = datetime.now().isoformat()
        state["last_check_result"] = f"Found {new_count} new recipe(s)"
        _save_scheduler_state(state)

    except Exception as e:
        logger.error(f"[Scheduler] Error checking for new videos: {e}")
        state = _load_scheduler_state()
        state["last_check"] = datetime.now().isoformat()
        state["last_check_error"] = str(e)[:200]
        _save_scheduler_state(state)


def send_weekly_grocery_list():
    """
    Pick a random recipe and email the grocery list.
    Called every Saturday morning.
    """
    from grocery_list import pick_weekly_recipe, build_grocery_list, save_to_history
    from notifier import send_weekly_grocery_email

    config = _load_config()
    if not config.get("smtp_email") or not config.get("notification_email"):
        logger.info("[Scheduler] Email not configured, skipping weekly grocery list.")
        return

    logger.info("[Scheduler] Picking this week's recipe...")

    recipe = pick_weekly_recipe()
    if not recipe:
        logger.info("[Scheduler] No recipes available to pick from.")
        return

    grocery = build_grocery_list(recipe)
    result = send_weekly_grocery_email(grocery)

    if result.get("success"):
        save_to_history(recipe, grocery)
        logger.info(f"[Scheduler] Weekly grocery list sent! Recipe: {recipe.get('title', '?')}")
    else:
        logger.error(f"[Scheduler] Failed to send email: {result.get('error')}")

    # Update state
    state = _load_scheduler_state()
    state["last_weekly_send"] = datetime.now().isoformat()
    state["last_weekly_recipe"] = recipe.get("title", "")
    state["last_weekly_result"] = "sent" if result.get("success") else result.get("error", "failed")
    _save_scheduler_state(state)


def _scheduler_loop():
    """Main scheduler loop running in background thread."""
    global _running
    logger.info("[Scheduler] Background scheduler started.")

    while _running:
        try:
            now = datetime.now()
            state = _load_scheduler_state()
            config = _load_config()

            check_interval_hours = config.get("check_interval_hours", 6)

            # ── Check for new videos periodically ──────────────
            last_check_str = state.get("last_check", "")
            should_check = True
            if last_check_str:
                try:
                    last_check = datetime.fromisoformat(last_check_str)
                    should_check = (now - last_check) > timedelta(hours=check_interval_hours)
                except ValueError:
                    pass

            if should_check and config.get("auto_check_enabled", True):
                try:
                    check_for_new_videos()
                except Exception as e:
                    logger.error(f"[Scheduler] Video check error: {e}")

            # ── Weekly grocery list on Saturday at 9 AM ────────
            if now.weekday() == 5 and 9 <= now.hour < 10:  # Saturday 9-10 AM
                last_send = state.get("last_weekly_send", "")
                sent_today = False
                if last_send:
                    try:
                        sent_today = datetime.fromisoformat(last_send).date() == now.date()
                    except ValueError:
                        pass

                if not sent_today and config.get("weekly_email_enabled", True):
                    try:
                        send_weekly_grocery_list()
                    except Exception as e:
                        logger.error(f"[Scheduler] Weekly email error: {e}")

        except Exception as e:
            logger.error(f"[Scheduler] Loop error: {e}")

        # Sleep 5 minutes between checks
        for _ in range(300):
            if not _running:
                break
            time.sleep(1)

    logger.info("[Scheduler] Background scheduler stopped.")


def start_scheduler():
    """Start the background scheduler thread."""
    global _scheduler_thread, _running

    if _scheduler_thread and _scheduler_thread.is_alive():
        logger.info("[Scheduler] Already running.")
        return

    _running = True
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True, name="recipe-scheduler")
    _scheduler_thread.start()
    logger.info("[Scheduler] Started background scheduler.")


def stop_scheduler():
    """Stop the background scheduler."""
    global _running
    _running = False
    logger.info("[Scheduler] Stopping...")


def get_scheduler_status() -> dict:
    """Get current scheduler state for the UI."""
    state = _load_scheduler_state()
    config = _load_config()
    return {
        "running": _running and _scheduler_thread is not None and _scheduler_thread.is_alive(),
        "auto_check_enabled": config.get("auto_check_enabled", True),
        "check_interval_hours": config.get("check_interval_hours", 6),
        "weekly_email_enabled": config.get("weekly_email_enabled", True),
        "last_check": state.get("last_check", "Never"),
        "last_check_result": state.get("last_check_result", ""),
        "last_weekly_send": state.get("last_weekly_send", "Never"),
        "last_weekly_recipe": state.get("last_weekly_recipe", ""),
    }
