"""
Notification System
Sends weekly grocery list emails on Saturday mornings.
Supports Gmail SMTP with App Passwords.
"""

import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
CONFIG_FILE = DATA_DIR / "config.json"


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def send_email(subject: str, body_text: str, body_html: str = "") -> dict:
    """
    Send an email using saved SMTP settings.
    Returns {"success": True} or {"error": "..."}
    """
    config = _load_config()
    smtp_email = config.get("smtp_email", "")
    smtp_password = config.get("smtp_password", "")
    recipient = config.get("notification_email", smtp_email)

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
