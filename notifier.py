"""
Notification System
Sends weekly grocery list emails on Saturday mornings.
Supports Gmail SMTP with App Passwords and SMS via carrier email-to-SMS gateway.
"""

import smtplib
import json
import random
import subprocess
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
CONFIG_FILE = DATA_DIR / "config.json"
RECIPES_FILE = DATA_DIR / "recipes.json"

# Carrier email-to-SMS/MMS gateways
CARRIER_GATEWAYS = {
    "att":      "{number}@mms.att.net",
    "verizon":  "{number}@vzwpix.com",
    "tmobile":  "{number}@tmomail.net",
    "sprint":   "{number}@pm.sprint.com",
    "googlefi": "{number}@msg.fi.google.com",
    "uscellular": "{number}@mms.uscc.net",
}


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def _save_config(config: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def _get_sms_address(config: dict = None) -> str:
    """Get the email-to-SMS address from config."""
    if config is None:
        config = _load_config()
    phone = config.get("sms_phone", "")
    carrier = config.get("sms_carrier", "")
    if not phone or not carrier:
        return ""
    gateway = CARRIER_GATEWAYS.get(carrier, "")
    if not gateway:
        return ""
    # Strip non-digits from phone
    digits = "".join(c for c in phone if c.isdigit())
    return gateway.format(number=digits)


def send_email(subject: str, body_text: str, body_html: str = "", recipient_override: str = "") -> dict:
    """
    Send an email using saved SMTP settings.
    Returns {"success": True} or {"error": "..."}
    """
    config = _load_config()
    smtp_email = config.get("smtp_email", "")
    smtp_password = config.get("smtp_password", "")
    recipient = recipient_override or config.get("notification_email", smtp_email)

    if not smtp_email or not smtp_password:
        return {"error": "Email not configured. Set SMTP email and password in settings."}

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Nick's Recipe Bot <{smtp_email}>"
        msg["To"] = recipient

        msg.attach(MIMEText(body_text, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))

        # Try Gmail SMTP
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_email, smtp_password)
            server.send_message(msg)

        return {"success": True, "message": f"Email sent to {recipient}"}

    except smtplib.SMTPAuthenticationError:
        return {"error": "Email auth failed. For Gmail, use an App Password (not your regular password). Go to: https://myaccount.google.com/apppasswords"}
    except Exception as e:
        return {"error": f"Email failed: {str(e)[:200]}"}


def send_weekly_grocery_email(grocery: dict) -> dict:
    """Send the formatted weekly grocery list email."""
    from grocery_list import format_grocery_list_text, format_grocery_list_html

    subject = f"🍳 This Week's Recipe: {grocery.get('recipe_title', 'Your Weekly Recipe')}"
    body_text = format_grocery_list_text(grocery)
    body_html = format_grocery_list_html(grocery)

    return send_email(subject, body_text, body_html)


def send_test_email() -> dict:
    """Send a test email to verify settings work."""
    return send_email(
        "🍳 Recipe Bot Test — It Works!",
        "Your Recipe Bot email notifications are set up correctly!\n\n"
        "You'll receive a grocery list every Saturday morning with a randomly "
        "picked recipe from your Instagram saved collection.\n\n"
        "Happy cooking! 🎉",
        """<div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; 
            background: #1a1a2e; color: #e0e0e0; padding: 30px; border-radius: 12px; text-align: center;">
            <h1 style="color: #ff6b6b;">🍳 It Works!</h1>
            <p>Your Recipe Bot email notifications are set up correctly.</p>
            <p style="color: #888;">You'll receive a grocery list every Saturday morning 
            with a randomly picked recipe from your collection.</p>
            <p style="margin-top: 20px;">Happy cooking! 🎉</p>
        </div>"""
    )


def _format_recipe_for_sms(recipe: dict) -> str:
    """Format a recipe as a compact text message."""
    title = recipe.get("title", "Recipe")
    # Truncate title nicely
    if len(title) > 50:
        title = title[:50].rsplit(" ", 1)[0] + "..."

    lines = [f"🍳 {title}"]
    
    total_time = recipe.get("total_time", "")
    if total_time:
        lines.append(f"⏱ {total_time}")
    
    servings = recipe.get("servings", "")
    if servings:
        lines.append(f"🍽 Serves {servings}")

    lines.append("")
    lines.append("INGREDIENTS:")
    for ing in recipe.get("ingredients", [])[:12]:
        amt = ing.get("amount", "")
        item = ing.get("item", "")
        if amt:
            lines.append(f"• {amt} {item}")
        else:
            lines.append(f"• {item}")

    lines.append("")
    lines.append("STEPS:")
    for i, step in enumerate(recipe.get("instructions", [])[:8], 1):
        # Trim long steps for SMS
        if len(step) > 120:
            step = step[:120].rsplit(" ", 1)[0] + "..."
        lines.append(f"{i}. {step}")

    tips = recipe.get("tips", "")
    if tips:
        lines.append(f"\n💡 {tips[:100]}")

    return "\n".join(lines)


def send_sms(body_text: str) -> dict:
    """
    Send a text message via email-to-SMS gateway.
    Returns {"success": True} or {"error": "..."}
    """
    config = _load_config()
    sms_addr = _get_sms_address(config)
    if not sms_addr:
        return {"error": "SMS not configured. Set phone number and carrier in settings."}

    # For SMS gateway, send plain text only with minimal subject
    return send_email("", body_text, recipient_override=sms_addr)


def send_recipe_texts(count: int = 3) -> dict:
    """
    Pick `count` random recipes and text them individually.
    Returns {"success": True, "sent": count, "recipes": [...titles...]}
    """
    if not RECIPES_FILE.exists():
        return {"error": "No recipes found. Run the pipeline first."}

    with open(RECIPES_FILE) as f:
        recipes = json.load(f)

    if not recipes:
        return {"error": "No recipes available."}

    # Pick random recipes (without replacement if possible)
    pick_count = min(count, len(recipes))
    chosen = random.sample(recipes, pick_count)

    sent_titles = []
    errors = []

    for recipe in chosen:
        text = _format_recipe_for_sms(recipe)
        result = send_sms(text)
        title = recipe.get("title", "Unknown")[:50]
        if result.get("success"):
            sent_titles.append(title)
        else:
            errors.append(f"{title}: {result.get('error', 'unknown error')}")

    if sent_titles:
        return {
            "success": True,
            "sent": len(sent_titles),
            "recipes": sent_titles,
            "errors": errors if errors else None,
        }
    else:
        return {"error": f"Failed to send any texts: {'; '.join(errors)}"}


def send_recipe_cards(count: int = 3) -> dict:
    """
    Generate beautiful recipe card images and email them.
    Each recipe is a single JPG with ingredients, instructions, and grocery list.
    Returns {"success": True, "sent": N, "recipes": [...]}
    """
    from recipe_card import generate_cards_for_recipes
    
    if not RECIPES_FILE.exists():
        return {"error": "No recipes found. Run the pipeline first."}

    with open(RECIPES_FILE) as f:
        recipes = json.load(f)

    if not recipes:
        return {"error": "No recipes available."}

    # Generate card images
    try:
        results = generate_cards_for_recipes(recipes, count)
    except Exception as e:
        return {"error": f"Failed to generate cards: {str(e)[:200]}"}

    # Build email with all cards attached
    config = _load_config()
    smtp_email = config.get("smtp_email", "")
    smtp_password = config.get("smtp_password", "")
    recipient = config.get("notification_email", smtp_email)

    if not smtp_email or not smtp_password:
        return {"error": "Email not configured."}

    titles = [r[0].get("title", "Recipe")[:60] for r in results]

    try:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = f"🍳 {count} Recipe Cards for You!"
        msg["From"] = f"Nick's Recipe Bot <{smtp_email}>"
        msg["To"] = recipient

        # Brief HTML intro
        intro_html = f"""<div style="font-family: -apple-system, Arial, sans-serif; color: #ccc; 
            background: #1a1a2e; padding: 20px; border-radius: 12px; text-align: center;">
            <h2 style="color: #ff6b6b;">🍳 Your Recipe Cards</h2>
            <p>{count} recipes picked just for you — scroll down or check the images!</p>
            <p style="color: #888; font-size: 13px;">{'  •  '.join(titles)}</p>
        </div>"""
        msg.attach(MIMEText(intro_html, "html"))

        # Attach each card image
        for recipe, grocery, image_path in results:
            with open(image_path, "rb") as img_f:
                img_data = img_f.read()
            
            img_part = MIMEImage(img_data, _subtype="jpeg")
            clean_title = "".join(c if c.isalnum() or c in " -_" else "" for c in recipe.get("title", "recipe"))[:40]
            img_part.add_header("Content-Disposition", "inline", filename=f"{clean_title}.jpg")
            img_part.add_header("Content-ID", f"<recipe_{clean_title}>")
            msg.attach(img_part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_email, smtp_password)
            server.send_message(msg)

        return {
            "success": True,
            "sent": len(results),
            "recipes": titles,
            "message": f"Sent {len(results)} recipe card images to {recipient}",
        }

    except Exception as e:
        return {"error": f"Failed to send: {str(e)[:200]}"}


def _send_imessage_text(phone: str, text: str) -> bool:
    """Send a text via iMessage using AppleScript. Passes text as argv to handle newlines."""
    script = '\n'.join([
        'on run argv',
        '  set phoneNum to item 1 of argv',
        '  set msg to item 2 of argv',
        '  tell application "Messages"',
        '    set targetService to 1st account whose service type = iMessage',
        '    set targetBuddy to participant phoneNum of targetService',
        '    send msg to targetBuddy',
        '  end tell',
        'end run',
    ])
    try:
        result = subprocess.run(
            ["osascript", "-e", script, "--", phone, text],
            capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0
    except Exception:
        return False


# Public base URL for recipe card images served via Cloudflare Pages
CARDS_BASE_URL = "https://recipecardsai.pages.dev/api/cards"


def imessage_recipe_cards(count: int = 3, recipe_index: int = None) -> dict:
    """
    Generate recipe card images, host them on the server, and text the
    image URLs via iMessage.  iOS renders link previews inline so the
    recipient sees the card image directly in Messages.
    
    If recipe_index is provided, send that specific recipe instead of random picks.
    """
    from recipe_card import generate_recipe_card, generate_cards_for_recipes
    from grocery_list import build_grocery_list
    import time
    from pathlib import PurePosixPath

    config = _load_config()
    phone = config.get("sms_phone", "")
    if not phone:
        return {"error": "No phone number configured."}

    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        phone_formatted = f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        phone_formatted = f"+{digits}"
    else:
        phone_formatted = f"+{digits}"

    if not RECIPES_FILE.exists():
        return {"error": "No recipes found. Run the pipeline first."}

    with open(RECIPES_FILE) as f:
        recipes = json.load(f)

    if not recipes:
        return {"error": "No recipes available."}

    # Generate cards — either a specific recipe or random picks
    try:
        if recipe_index is not None:
            valid = [r for r in recipes if "error" not in r]
            if recipe_index < 0 or recipe_index >= len(valid):
                return {"error": f"Recipe index {recipe_index} out of range (0-{len(valid)-1})"}
            recipe = valid[recipe_index]
            grocery = build_grocery_list(recipe)
            image_path = generate_recipe_card(recipe, grocery)
            results = [(recipe, grocery, image_path)]
        else:
            results = generate_cards_for_recipes(recipes, count)
    except Exception as e:
        return {"error": f"Failed to generate cards: {str(e)[:200]}"}

    sent_titles = []
    errors = []

    for recipe, grocery, image_path in results:
        title = recipe.get("title", "Recipe")[:60]
        filename = Path(image_path).name
        # URL-encode the filename for spaces/special chars
        encoded_name = __import__('urllib.parse', fromlist=['quote']).quote(filename)
        card_url = f"{CARDS_BASE_URL}/{encoded_name}"

        # Send a text with the recipe title + the image URL
        msg = f"🍳 {title}\n{card_url}"
        success = _send_imessage_text(phone_formatted, msg)
        if success:
            sent_titles.append(title)
        else:
            errors.append(title)
        time.sleep(2)

    if sent_titles:
        return {
            "success": True,
            "sent": len(sent_titles),
            "recipes": sent_titles,
            "errors": errors if errors else None,
            "message": f"Texted {len(sent_titles)} recipe card links via iMessage",
        }
    else:
        return {"error": "Failed to send any messages via iMessage"}


def imessage_recipe_text(count: int = 3) -> dict:
    """
    Send recipes as plain text messages via iMessage.
    Each recipe is a single message with title, ingredients, steps, and grocery list.
    """
    from grocery_list import build_grocery_list
    import time

    config = _load_config()
    phone = config.get("sms_phone", "")
    if not phone:
        return {"error": "No phone number configured."}

    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        phone_formatted = f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        phone_formatted = f"+{digits}"
    else:
        phone_formatted = f"+{digits}"

    if not RECIPES_FILE.exists():
        return {"error": "No recipes found. Run the pipeline first."}

    with open(RECIPES_FILE) as f:
        recipes = json.load(f)

    if not recipes:
        return {"error": "No recipes available."}

    # Pick random recipes (avoid duplicates)
    pick_count = min(count, len(recipes))
    selected = random.sample(recipes, pick_count)

    # Send intro
    _send_imessage_text(phone_formatted, f"Here are {pick_count} recipes for you!")
    time.sleep(1.5)

    sent_titles = []
    errors = []

    for recipe in selected:
        title = recipe.get("title", "Recipe")
        ingredients = recipe.get("ingredients", [])
        steps = recipe.get("instructions", [])
        servings = recipe.get("servings", "2-4")
        total_time = recipe.get("total_time", "")

        # Build recipe text
        lines = []
        lines.append(f"--- {title.upper()} ---")
        if total_time:
            lines.append(f"Time: {total_time} | Servings: {servings}")
        lines.append("")

        # Ingredients
        lines.append("INGREDIENTS:")
        for ing in ingredients:
            item = ing.get("item", "")
            amount = ing.get("amount", "")
            if amount:
                lines.append(f"  - {amount} {item}")
            else:
                lines.append(f"  - {item}")
        lines.append("")

        # Steps
        lines.append("STEPS:")
        for i, step in enumerate(steps, 1):
            step_text = step if isinstance(step, str) else step.get("step", str(step))
            lines.append(f"  {i}. {step_text}")
        lines.append("")

        # Grocery list by aisle
        try:
            grocery = build_grocery_list(recipe)
            by_aisle = grocery.get("by_aisle", {})
            if by_aisle:
                lines.append("GROCERY LIST:")
                for aisle, items in by_aisle.items():
                    lines.append(f"  [{aisle}]")
                    for item in items:
                        amt = f" ({item['amount']})" if item.get("amount") else ""
                        lines.append(f"    - {item['item']}{amt}")
        except Exception:
            pass  # Skip grocery if it fails

        message = "\n".join(lines)

        success = _send_imessage_text(phone_formatted, message)
        if success:
            sent_titles.append(title)
        else:
            errors.append(title)
        time.sleep(2)

    if sent_titles:
        return {
            "success": True,
            "sent": len(sent_titles),
            "recipes": sent_titles,
            "errors": errors if errors else None,
            "message": f"Texted {len(sent_titles)} plain text recipes via iMessage",
        }
    else:
        return {"error": "Failed to send any messages via iMessage"}

