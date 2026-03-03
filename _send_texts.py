#!/usr/bin/env python3
"""Send 3 plain text recipes via iMessage for testing."""
import json, random, subprocess, time, sys
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
RECIPES_FILE = DATA_DIR / "recipes.json"

def send_text(phone, text):
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
    r = subprocess.run(["osascript", "-e", script, "--", phone, text],
                       capture_output=True, text=True, timeout=30)
    print(f"  osascript exit={r.returncode}, stderr={r.stderr.strip()[:100] if r.stderr else 'none'}")
    return r.returncode == 0

phone = "+14804540020"
recipes = json.load(open(RECIPES_FILE))
selected = random.sample(recipes, min(3, len(recipes)))

print(f"Sending {len(selected)} recipes to {phone}...")
sys.stdout.flush()

ok = send_text(phone, f"Here are {len(selected)} recipes for you!")
print(f"  Intro sent: {'OK' if ok else 'FAILED'}")
sys.stdout.flush()
time.sleep(1.5)

for recipe in selected:
    title = recipe.get("title", "Recipe")
    ingredients = recipe.get("ingredients", [])
    steps = recipe.get("instructions", [])

    lines = []
    lines.append(f"--- {title.upper()} ---")
    lines.append("")
    lines.append("INGREDIENTS:")
    for ing in ingredients:
        item = ing.get("item", "")
        amount = ing.get("amount", "")
        if amount:
            lines.append(f"  - {amount} {item}")
        else:
            lines.append(f"  - {item}")
    lines.append("")
    lines.append("STEPS:")
    for i, step in enumerate(steps, 1):
        step_text = step if isinstance(step, str) else step.get("step", str(step))
        lines.append(f"  {i}. {step_text}")

    msg = "\n".join(lines)
    print(f"\nSending: {title} ({len(msg)} chars)")
    sys.stdout.flush()
    ok = send_text(phone, msg)
    print(f"  Result: {'OK' if ok else 'FAILED'}")
    sys.stdout.flush()
    time.sleep(2)

print("\nAll done!")
