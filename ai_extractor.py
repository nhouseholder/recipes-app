"""
Cloudflare Workers AI — Recipe Extraction with Llama 3.3 70B

Calls Cloudflare's inference API to convert raw video transcripts
into proper, structured recipes with real ingredient amounts and
clear professional instructions.
"""

import json
import re
import subprocess
import time
import urllib.request
import urllib.error
import ssl
from pathlib import Path
from typing import Optional, Union

# ── Config ──────────────────────────────────────────────────
ACCOUNT_ID = "e246c909cd0c462975902369c8aa7512"
MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
API_URL = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{MODEL}"

WRANGLER_CONFIG = Path.home() / "Library" / "Preferences" / ".wrangler" / "config" / "default.toml"

SEED_OILS = {"canola oil", "vegetable oil", "soybean oil", "corn oil",
             "sunflower oil", "safflower oil", "grapeseed oil", "cottonseed oil",
             "rice bran oil"}

SYSTEM_PROMPT = """You are a professional recipe writer. You receive raw transcripts from short cooking videos (Instagram Reels). Your job is to interpret the transcript and produce a clean, well-structured recipe.

CRITICAL RULES:
1. INTERPRET, don't transcribe — The transcript is casual speech. You must understand what dish is being made and write a proper recipe, NOT copy the transcript.
2. INFER AMOUNTS — Cooking videos rarely state exact amounts. Use your culinary knowledge to infer reasonable amounts (e.g., "a little oil" → "1 tbsp olive oil", "season it" → "1 tsp salt, ½ tsp pepper").
3. REAL INGREDIENT NAMES — Never list vague words like "mine", "it", "stuff". Always use specific ingredient names.
4. NO SEED OILS — Never include canola oil, vegetable oil, soybean oil, corn oil, sunflower oil, safflower oil, grapeseed oil, or cottonseed oil. Substitute with olive oil, butter, avocado oil, or coconut oil.
5. PROFESSIONAL INSTRUCTIONS — Write clear, numbered steps a home cook can follow. No casual speech, no "gonna", no "let's move on".
6. MINIMIZE INGREDIENTS — Remove optional garnishes and unnecessary items. Keep it simple.
7. KEEP TOTAL TIME UNDER 1 HOUR — If longer, simplify with shortcuts.
8. BASIC EQUIPMENT — Only: skillet/pan, baking sheet, oven, pot/saucepan, mixing bowl, cutting board, knife, basic utensils.

If the transcript has NO actual recipe or cooking content, respond with ONLY: {"error": "No recipe found"}

Otherwise respond with ONLY valid JSON (no markdown, no backticks, no extra text):
{
  "title": "Proper Recipe Name",
  "description": "One sentence about the dish",
  "prep_time": "X minutes",
  "cook_time": "X minutes",
  "servings": "X",
  "ingredients": [
    {"amount": "1 lb", "item": "chicken breast, diced"},
    {"amount": "2 tbsp", "item": "olive oil"}
  ],
  "instructions": [
    "Dice the chicken breast into 1-inch cubes.",
    "Heat olive oil in a skillet over medium-high heat."
  ],
  "equipment": ["skillet", "cutting board"],
  "category": "dinner|lunch|breakfast|snack|dessert|side"
}"""


def _get_token() -> str:
    """Read the current OAuth token from wrangler config."""
    if not WRANGLER_CONFIG.exists():
        raise RuntimeError(f"Wrangler config not found at {WRANGLER_CONFIG}. Run 'npx wrangler login' first.")
    text = WRANGLER_CONFIG.read_text()
    match = re.search(r'oauth_token\s*=\s*"([^"]+)"', text)
    if not match:
        raise RuntimeError("No oauth_token found in wrangler config.")
    return match.group(1)


def _refresh_token() -> str:
    """Force a token refresh by invoking wrangler whoami."""
    print("[AI] Token expired, refreshing via wrangler...", flush=True)
    env = dict(__import__("os").environ, PATH="/opt/homebrew/opt/node@22/bin:" + __import__("os").environ.get("PATH", ""))
    try:
        subprocess.run(["npx", "wrangler", "whoami"], capture_output=True, timeout=30, env=env)
    except Exception as e:
        print(f"[AI] wrangler refresh failed: {e}")
    return _get_token()


def _call_llama(transcript: str, caption: str = "", max_tokens: int = 2048) -> dict:
    """Call Cloudflare Workers AI with Llama 3.3 70B. Retries once on 401."""
    token = _get_token()

    user_msg = f"Convert this cooking video transcript into a proper recipe.\n\n"
    if caption:
        user_msg += f"Video caption: {caption}\n\n"
    user_msg += f"Transcript:\n{transcript}"

    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": max_tokens,
    }

    return _send_llama_request(token, payload)


def _send_llama_request(token: str, payload: dict) -> dict:
    """Send a request to Cloudflare Workers AI. Handles retries on 401."""
    ctx = ssl.create_default_context()

    for attempt in range(2):
        data = json.dumps(payload).encode()
        req = urllib.request.Request(API_URL, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=90, context=ctx) as resp:
                result = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt == 0:
                token = _refresh_token()
                continue
            raise

        if not result.get("success"):
            errors = result.get("errors", [])
            raise RuntimeError(f"Workers AI error: {errors}")

        ai_response = result.get("result", {}).get("response", "")
        # Workers AI auto-parses JSON responses into dicts
        if isinstance(ai_response, dict):
            return _normalize_recipe(ai_response)
        return _parse_ai_response(ai_response)


CAPTION_SYSTEM_PROMPT = """You are a professional recipe writer. You receive description of a dish from a cooking video. Your job is to create a clean, well-structured recipe for this dish using your culinary knowledge.

CRITICAL RULES:
1. Create a complete, authentic recipe for the described dish.
2. Use standard amounts and measurements.
3. NO SEED OILS — Use olive oil, butter, avocado oil, or coconut oil instead.
4. PROFESSIONAL INSTRUCTIONS — Write clear, numbered steps a home cook can follow.
5. MINIMIZE INGREDIENTS — Keep it simple and practical.
6. BASIC EQUIPMENT — Only: skillet/pan, baking sheet, oven, pot/saucepan, mixing bowl, cutting board, knife, basic utensils.

Respond with ONLY valid JSON (no markdown, no backticks, no extra text):
{
  "title": "Proper Recipe Name",
  "description": "One sentence about the dish",
  "prep_time": "X minutes",
  "cook_time": "X minutes",
  "servings": "X",
  "ingredients": [
    {"amount": "1 lb", "item": "chicken breast, diced"},
    {"amount": "2 tbsp", "item": "olive oil"}
  ],
  "instructions": [
    "Dice the chicken breast into 1-inch cubes.",
    "Heat olive oil in a skillet over medium-high heat."
  ],
  "equipment": ["skillet", "cutting board"],
  "category": "dinner|lunch|breakfast|snack|dessert|side"
}"""


def create_recipe_from_caption(caption: str) -> dict:
    """Generate a recipe based on a video caption/title when transcription fails."""
    token = _get_token()

    payload = {
        "messages": [
            {"role": "system", "content": CAPTION_SYSTEM_PROMPT},
            {"role": "user", "content": f"Create a recipe for this dish from a cooking video:\n\n{caption}"},
        ],
        "max_tokens": 2048,
    }

    return _send_llama_request(token, payload)


def _normalize_recipe(raw: dict) -> dict:
    """Normalize an AI-returned recipe dict that may have non-standard field names."""
    # If the recipe is nested (e.g. {"recipe": {...}})
    if "recipe" in raw and isinstance(raw["recipe"], dict) and "title" not in raw:
        raw = raw["recipe"]

    # Map common alternate field names
    field_map = {
        "name": "title",
        "recipe_name": "title",
        "dish": "title",
        "desc": "description",
        "summary": "description",
        "prep": "prep_time",
        "preparation_time": "prep_time",
        "cooking_time": "cook_time",
        "total": "total_time",
        "serves": "servings",
        "yield": "servings",
        "steps": "instructions",
        "directions": "instructions",
        "method": "instructions",
        "tools": "equipment",
        "type": "category",
        "meal_type": "category",
    }
    normalized = {}
    for key, val in raw.items():
        mapped = field_map.get(key, key)
        normalized[mapped] = val

    # Normalize ingredients if they use non-standard format
    if "ingredients" in normalized and isinstance(normalized["ingredients"], list):
        new_ings = []
        for ing in normalized["ingredients"]:
            if isinstance(ing, str):
                new_ings.append({"amount": "", "item": ing})
            elif isinstance(ing, dict):
                # Handle various formats: {name, quantity}, {ingredient, amount}, etc.
                item = ing.get("item", ing.get("name", ing.get("ingredient", "")))
                amount = ing.get("amount", ing.get("quantity", ing.get("measure", "")))
                if item:
                    new_ings.append({"amount": str(amount), "item": str(item)})
            else:
                new_ings.append({"amount": "", "item": str(ing)})
        normalized["ingredients"] = new_ings

    # Normalize instructions if they use non-standard format
    if "instructions" in normalized and isinstance(normalized["instructions"], list):
        new_steps = []
        for step in normalized["instructions"]:
            if isinstance(step, str):
                new_steps.append(step)
            elif isinstance(step, dict):
                # Handle {step, action}, {step_number, instruction}, etc.
                text = step.get("action", step.get("instruction", step.get("text", step.get("step", ""))))
                if isinstance(text, str) and text:
                    new_steps.append(text)
            else:
                new_steps.append(str(step))
        normalized["instructions"] = new_steps

    return normalized


def _parse_ai_response(text: str) -> dict:
    """Parse the AI response, handling possible markdown fences or extra text."""
    text = text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)

    # Try direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # If JSON is truncated, try to fix it
    if '{' in text:
        fixed = _fix_truncated_json(text)
        if fixed:
            return fixed

    return {"error": f"Could not parse AI response: {text[:200]}"}


def _fix_truncated_json(text: str) -> Optional[dict]:
    """Try to fix truncated JSON by closing brackets."""
    # Find the JSON start
    start = text.index('{')
    json_text = text[start:]

    # Count unclosed brackets
    open_braces = json_text.count('{') - json_text.count('}')
    open_brackets = json_text.count('[') - json_text.count(']')

    # Close any open strings
    if json_text.count('"') % 2 == 1:
        json_text += '"'

    # Close brackets/braces
    json_text += ']' * open_brackets
    json_text += '}' * open_braces

    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        return None


def _clean_recipe(recipe: dict, transcript: str = "") -> dict:
    """Post-process the AI recipe: fix seed oils, validate fields."""
    if "error" in recipe:
        return recipe

    # Ensure all required fields
    defaults = {
        "title": "Untitled Recipe",
        "description": "",
        "prep_time": "10 minutes",
        "cook_time": "20 minutes",
        "servings": "2-4",
        "ingredients": [],
        "instructions": [],
        "equipment": [],
        "category": "dinner",
    }
    for key, default in defaults.items():
        if key not in recipe or not recipe[key]:
            recipe[key] = default

    # Replace any seed oils that slipped through
    subs_made = []
    for ing in recipe.get("ingredients", []):
        item_lower = ing.get("item", "").lower()
        for oil in SEED_OILS:
            if oil in item_lower:
                ing["item"] = ing["item"].replace(oil, "olive oil").replace(oil.title(), "Olive oil")
                subs_made.append(f"Replaced {oil} with olive oil")

    if subs_made:
        recipe["substitutions_made"] = subs_made

    # Validate category
    valid_cats = {"dinner", "lunch", "breakfast", "snack", "dessert", "side"}
    if recipe.get("category", "").lower() not in valid_cats:
        recipe["category"] = "dinner"
    else:
        recipe["category"] = recipe["category"].lower()

    # Clean up title
    recipe["title"] = recipe["title"].strip().title()

    return recipe


def extract_recipe_ai(transcript: str, caption: str = "", source_id: str = "", source_url: str = "") -> dict:
    """
    Main entry point: Extract a recipe from a transcript using Cloudflare Workers AI.
    Falls back gracefully on errors.
    """
    if not transcript or len(transcript.strip()) < 20:
        return {"error": "Transcript too short"}

    try:
        recipe = _call_llama(transcript, caption)
        recipe = _clean_recipe(recipe, transcript)

        # Attach source info
        if source_id:
            recipe["source_id"] = source_id
        if source_url:
            recipe["source_url"] = source_url
        recipe["transcript"] = transcript

        return recipe

    except Exception as e:
        import traceback
        print(f"[AI] Error extracting recipe: {e}")
        traceback.print_exc()
        return {"error": f"AI extraction failed: {str(e)[:200]}"}


def reextract_all_recipes(recipes_file: Union[str, Path], progress_callback=None) -> dict:
    """
    Re-extract ALL recipes from their transcripts using AI.
    
    Args:
        recipes_file: Path to recipes.json
        progress_callback: Optional fn(current, total, title) for progress updates
    
    Returns:
        {"total": N, "improved": N, "failed": N, "removed": N, "recipes": [...]}
    """
    recipes_file = Path(recipes_file)
    if not recipes_file.exists():
        return {"error": "recipes.json not found"}

    old_recipes = json.loads(recipes_file.read_text())
    
    # Backup
    backup_path = recipes_file.parent / "recipes_pre_ai_backup.json"
    backup_path.write_text(json.dumps(old_recipes, indent=2))
    print(f"[AI] Backed up {len(old_recipes)} recipes to {backup_path.name}")

    new_recipes = []
    stats = {"total": len(old_recipes), "improved": 0, "failed": 0, "removed": 0}

    for i, old in enumerate(old_recipes):
        title = old.get("title", "?")
        transcript = old.get("transcript", "")
        source_id = old.get("source_id", "")
        source_url = old.get("source_url", "")

        if progress_callback:
            progress_callback(i + 1, len(old_recipes), title)

        print(f"[AI] [{i+1}/{len(old_recipes)}] Processing: {title[:50]}...", flush=True)

        if not transcript or len(transcript.strip()) < 20:
            print(f"  → Skipped (no/short transcript)")
            stats["removed"] += 1
            continue

        try:
            recipe = extract_recipe_ai(transcript, caption="", source_id=source_id, source_url=source_url)

            if "error" in recipe:
                error_msg = recipe["error"]
                if "No recipe found" in error_msg:
                    print(f"  → Removed (no recipe in video)")
                    stats["removed"] += 1
                else:
                    print(f"  → Failed: {error_msg[:100]}")
                    # Keep old recipe on AI failure
                    new_recipes.append(old)
                    stats["failed"] += 1
            else:
                new_recipes.append(recipe)
                stats["improved"] += 1
                print(f"  → ✓ {recipe['title']}")

        except Exception as e:
            print(f"  → Error: {e}")
            new_recipes.append(old)  # Keep old on error
            stats["failed"] += 1

        # Rate limit: ~10 req/min to be safe
        if i < len(old_recipes) - 1:
            time.sleep(2)

    # Save new recipes
    recipes_file.write_text(json.dumps(new_recipes, indent=2))
    print(f"\n[AI] Done! {stats['improved']} improved, {stats['failed']} failed, {stats['removed']} removed")
    print(f"[AI] {len(new_recipes)} recipes saved to {recipes_file.name}")

    stats["recipes"] = new_recipes
    return stats
