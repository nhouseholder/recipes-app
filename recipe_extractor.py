"""
Recipe Extractor
Takes video transcripts + captions and uses an LLM to extract clean,
simplified recipes that meet Nick's requirements:
  - As few ingredients as possible
  - NO seed oils (no canola, vegetable, soybean, corn, sunflower, safflower, grapeseed, cottonseed oil)
  - Prep time under 1 hour
  - Basic equipment only (frying pan, baking sheet, oven, microwave, sauce pot)
"""

import json
import os
import re
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
RECIPES_FILE = DATA_DIR / "recipes.json"

SEED_OILS = [
    "canola oil", "vegetable oil", "soybean oil", "corn oil",
    "sunflower oil", "safflower oil", "grapeseed oil", "grape seed oil",
    "cottonseed oil", "rice bran oil", "peanut oil",
]

SAFE_FATS = [
    "butter", "ghee", "olive oil", "extra virgin olive oil", "avocado oil",
    "coconut oil", "tallow", "lard", "duck fat", "bacon fat", "schmaltz",
]

ALLOWED_EQUIPMENT = [
    "frying pan", "skillet", "baking sheet", "sheet pan", "oven",
    "microwave", "sauce pot", "saucepan", "pot", "mixing bowl", "bowl",
    "cutting board", "knife", "spatula", "tongs", "whisk", "wooden spoon",
    "measuring cups", "measuring spoons", "colander", "strainer",
    "aluminum foil", "parchment paper", "baking dish", "casserole dish",
]

SYSTEM_PROMPT = """You are a recipe simplification expert. Your job is to take a video transcript 
(and optional caption) from a cooking video and extract a clean, simple recipe.

STRICT RULES:
1. MINIMIZE INGREDIENTS - Use as few ingredients as possible. Remove garnishes, optional items, 
   and anything that doesn't fundamentally change the dish.
2. NO SEED OILS - Never include: canola oil, vegetable oil, soybean oil, corn oil, sunflower oil, 
   safflower oil, grapeseed oil, cottonseed oil, rice bran oil.
   ALWAYS SUBSTITUTE with: butter, ghee, olive oil, avocado oil, or coconut oil.
3. PREP TIME UNDER 1 HOUR - If the original recipe takes longer, simplify steps or suggest shortcuts.
4. BASIC EQUIPMENT ONLY - Only use: frying pan/skillet, baking sheet, oven, microwave, sauce pot/saucepan, 
   mixing bowls, cutting board & knife, basic utensils.
   NO: air fryer, instant pot, sous vide, food processor, blender (unless it's a smoothie), 
   stand mixer, deep fryer, grill, smoker, specialty pans.

OUTPUT FORMAT (JSON):
{
  "title": "Recipe Name",
  "description": "One sentence describing the dish",
  "prep_time": "X minutes",
  "cook_time": "X minutes", 
  "total_time": "X minutes",
  "servings": "X",
  "ingredients": [
    {"amount": "1 lb", "item": "chicken thighs"},
    {"amount": "2 tbsp", "item": "butter"}
  ],
  "instructions": [
    "Step 1 description",
    "Step 2 description"
  ],
  "equipment": ["frying pan", "cutting board"],
  "tips": "Optional helpful tip",
  "substitutions_made": ["Replaced vegetable oil with butter"],
  "category": "dinner|lunch|breakfast|snack|dessert|side"
}

If the transcript doesn't contain a recipe, return: {"error": "No recipe found in this video"}
"""


def extract_recipe_with_openai(transcript: str, caption: str = "", api_key: str = "") -> dict:
    """Use OpenAI GPT to extract and simplify a recipe."""
    from openai import OpenAI

    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY", "")

    if not api_key:
        return extract_recipe_local(transcript, caption)

    client = OpenAI(api_key=api_key)

    user_message = f"""Extract and simplify the recipe from this cooking video.

VIDEO CAPTION:
{caption or '(no caption)'}

VIDEO TRANSCRIPT:
{transcript}

Remember: Minimize ingredients, NO seed oils (sub with butter/olive oil/avocado oil), 
under 1 hour total, basic equipment only."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        return _validate_and_clean_recipe(result)

    except Exception as e:
        print(f"[OpenAI] Error: {e}")
        return extract_recipe_local(transcript, caption)


def extract_recipe_local(transcript: str, caption: str = "") -> dict:
    """
    Extract recipe using rule-based parsing (no API needed).
    Less sophisticated but works offline.
    """
    text = f"{caption}\n{transcript}".lower()

    if len(text.strip()) < 20:
        return {"error": "Transcript too short to extract recipe"}

    # Try to identify the dish name from the first sentence
    title = _extract_title(caption, transcript)

    # Extract ingredients by looking for measurement patterns
    ingredients = _extract_ingredients(text)

    # Extract steps
    instructions = _extract_instructions(transcript)

    if not ingredients and not instructions:
        return {"error": "Could not parse recipe from transcript"}

    # Replace seed oils
    ingredients = _replace_seed_oils(ingredients)

    recipe = {
        "title": title,
        "description": f"Simple {title} recipe",
        "prep_time": "10 minutes",
        "cook_time": "20 minutes",
        "total_time": "30 minutes",
        "servings": "2-4",
        "ingredients": ingredients,
        "instructions": instructions if instructions else ["Follow along with the video for detailed steps."],
        "equipment": _guess_equipment(text),
        "tips": "Adjust seasoning to taste.",
        "substitutions_made": [],
        "category": _guess_category(text),
    }

    return _validate_and_clean_recipe(recipe)


def _extract_title(caption: str, transcript: str) -> str:
    """Try to extract recipe title from caption or transcript."""
    # Check caption first
    if caption:
        # Look for common patterns like "Easy Chicken Pasta" or "How to make..."
        patterns = [
            r"(?:how to (?:make|cook)\s+)([\w\s]+)",
            r"(?:easy|simple|quick|best|homemade)\s+([\w\s]+?)(?:\s*recipe|\s*!|\s*\n|$)",
            r"^([\w\s]+?)(?:\s*recipe|\s*!|\s*\n)",
        ]
        for pattern in patterns:
            match = re.search(pattern, caption, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                if 3 < len(title) < 50:
                    return title.title()

    # Fall back to first meaningful line of transcript
    lines = transcript.strip().split('.')
    if lines:
        first = lines[0].strip()[:60]
        if first:
            return first.title()

    return "Untitled Recipe"


def _extract_ingredients(text: str) -> list[dict]:
    """Extract ingredients from text using pattern matching."""
    ingredients = []
    seen = set()

    # Common measurement patterns
    measurement_pattern = r'(\d+[\./]?\d*\s*(?:cup|cups|tbsp|tablespoon|tsp|teaspoon|oz|ounce|lb|pound|g|gram|kg|ml|liter|clove|cloves|piece|pieces|bunch|can|cans|package|pkg|stick|sticks|pinch|dash|handful|slice|slices)s?\s+(?:of\s+)?)([\w\s]+?)(?:\.|,|\n|$|and\s)'

    for match in re.finditer(measurement_pattern, text):
        amount = match.group(1).strip()
        item = match.group(2).strip()
        item = re.sub(r'\s+', ' ', item)[:40]

        if item and item not in seen and len(item) > 1:
            seen.add(item)
            ingredients.append({"amount": amount, "item": item})

    # Also look for common ingredients by keyword
    common_ingredients = [
        "chicken", "beef", "pork", "salmon", "shrimp", "tofu",
        "rice", "pasta", "noodles", "bread",
        "onion", "garlic", "tomato", "potato", "pepper", "broccoli",
        "cheese", "cream", "milk", "egg", "butter",
        "salt", "pepper", "paprika", "cumin", "oregano",
        "olive oil", "soy sauce", "honey", "lemon",
    ]

    for ingredient in common_ingredients:
        if ingredient in text and ingredient not in seen:
            seen.add(ingredient)
            ingredients.append({"amount": "to taste" if ingredient in ["salt", "pepper"] else "", "item": ingredient})

    return ingredients[:15]  # Cap at 15 ingredients


def _extract_instructions(transcript: str) -> list[str]:
    """Extract cooking steps from transcript."""
    sentences = re.split(r'[.!]\s+', transcript)
    steps = []

    # Filter for instruction-like sentences
    action_words = [
        "add", "mix", "stir", "cook", "bake", "heat", "pour", "place",
        "cut", "chop", "dice", "slice", "season", "salt", "pepper",
        "put", "set", "preheat", "flip", "turn", "remove", "let",
        "combine", "whisk", "fold", "spread", "top", "serve",
        "brown", "sear", "saute", "boil", "simmer", "fry", "roast",
        "drain", "rinse", "marinate", "cover", "wrap",
    ]

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence or len(sentence) < 10:
            continue

        words = sentence.lower().split()
        if any(word in action_words for word in words[:5]):
            # Clean up the instruction
            step = sentence[0].upper() + sentence[1:]
            if not step.endswith('.'):
                step += '.'
            steps.append(step)

    # If we couldn't find structured steps, chunk the transcript
    if not steps and len(transcript) > 50:
        chunks = [s.strip() for s in transcript.split('.') if len(s.strip()) > 15]
        steps = [c[0].upper() + c[1:] + '.' for c in chunks[:10]]

    return steps[:12]  # Cap at 12 steps


def _replace_seed_oils(ingredients: list[dict]) -> list[dict]:
    """Replace any seed oils with healthy alternatives."""
    cleaned = []
    substitutions = []

    for ing in ingredients:
        item_lower = ing["item"].lower()
        is_seed_oil = any(oil in item_lower for oil in SEED_OILS)

        if is_seed_oil:
            substitutions.append(f"Replaced {ing['item']} with butter")
            ing["item"] = "butter"

        # Also replace "cooking spray" with butter
        if "cooking spray" in item_lower or "spray" in item_lower:
            substitutions.append(f"Replaced cooking spray with butter")
            ing["item"] = "butter"
            ing["amount"] = "1 tbsp"

        cleaned.append(ing)

    return cleaned


def _guess_equipment(text: str) -> list[str]:
    """Guess what equipment is needed based on the text."""
    equipment = set()
    text_lower = text.lower()

    equipment_keywords = {
        "frying pan": ["fry", "frying pan", "skillet", "pan fry", "saute", "sear"],
        "baking sheet": ["baking sheet", "sheet pan", "cookie sheet", "roast"],
        "oven": ["oven", "bake", "roast", "broil", "preheat"],
        "sauce pot": ["pot", "boil", "simmer", "soup", "stew", "sauce"],
        "microwave": ["microwave", "nuke", "reheat"],
        "mixing bowl": ["bowl", "mix", "combine", "whisk"],
        "cutting board": ["cut", "chop", "dice", "slice", "mince"],
    }

    for equip, keywords in equipment_keywords.items():
        if any(kw in text_lower for kw in keywords):
            equipment.add(equip)

    if not equipment:
        equipment.add("frying pan")

    return sorted(equipment)


def _guess_category(text: str) -> str:
    """Guess the meal category."""
    text_lower = text.lower()

    if any(w in text_lower for w in ["breakfast", "morning", "egg", "pancake", "waffle", "oatmeal", "brunch"]):
        return "breakfast"
    if any(w in text_lower for w in ["dessert", "cake", "cookie", "brownie", "sweet", "chocolate", "ice cream"]):
        return "dessert"
    if any(w in text_lower for w in ["snack", "appetizer", "dip", "chips"]):
        return "snack"
    if any(w in text_lower for w in ["side", "salad", "slaw"]):
        return "side"
    if any(w in text_lower for w in ["lunch", "sandwich", "wrap", "light"]):
        return "lunch"

    return "dinner"


def _validate_and_clean_recipe(recipe: dict) -> dict:
    """Validate recipe meets all requirements and clean it up."""
    if "error" in recipe:
        return recipe

    # Ensure no seed oils snuck through
    if "ingredients" in recipe:
        for ing in recipe["ingredients"]:
            item_lower = ing.get("item", "").lower()
            if any(oil in item_lower for oil in SEED_OILS):
                ing["item"] = "butter"
                if "substitutions_made" not in recipe:
                    recipe["substitutions_made"] = []
                recipe["substitutions_made"].append(f"Replaced seed oil with butter")

    # Ensure basic fields exist
    defaults = {
        "title": "Untitled Recipe",
        "description": "",
        "prep_time": "15 minutes",
        "cook_time": "20 minutes",
        "total_time": "35 minutes",
        "servings": "2-4",
        "ingredients": [],
        "instructions": [],
        "equipment": ["frying pan"],
        "tips": "",
        "substitutions_made": [],
        "category": "dinner",
    }

    for key, default in defaults.items():
        if key not in recipe or not recipe[key]:
            recipe[key] = default

    return recipe


def save_recipes(recipes: list[dict]):
    """Save all recipes to the JSON file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(RECIPES_FILE, 'w') as f:
        json.dump(recipes, f, indent=2)
    print(f"[Recipes] Saved {len(recipes)} recipes to {RECIPES_FILE}")


def load_recipes() -> list[dict]:
    """Load recipes from the JSON file."""
    if RECIPES_FILE.exists():
        with open(RECIPES_FILE, 'r') as f:
            return json.load(f)
    return []
