"""
Recipe Extractor v2
Takes video transcripts + captions and extracts clean, simplified recipes.

Requirements:
  - As few ingredients as possible
  - NO seed oils
  - Prep time under 1 hour
  - Basic equipment only
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
    "coconut oil", "tallow", "lard", "duck fat", "bacon fat",
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
        return _validate_and_clean(result)
    except Exception as e:
        print(f"[OpenAI] Error: {e}")
        return extract_recipe_local(transcript, caption)


# ═══════════════════════════════════════════════════════════
#  Cooking vocabulary
# ═══════════════════════════════════════════════════════════

COOKING_VERBS = {
    "add", "mix", "stir", "cook", "bake", "heat", "pour", "place",
    "cut", "chop", "dice", "slice", "season", "put", "set", "preheat",
    "flip", "turn", "remove", "let", "combine", "whisk", "fold",
    "spread", "top", "serve", "brown", "sear", "saute", "sauté",
    "boil", "simmer", "fry", "roast", "drain", "rinse", "marinate",
    "cover", "wrap", "melt", "bring", "reduce", "toss", "drizzle",
    "layer", "stuff", "fill", "blend", "mash", "grate", "shred",
    "coat", "dip", "roll", "knead", "baste", "glaze", "caramelize",
    "deglaze", "steam", "poach", "broil", "toast", "cool", "chill",
    "refrigerate", "freeze", "peel", "trim", "pound", "press",
    "crack", "beat", "scramble", "brush", "squeeze", "scoop",
    "grab", "take", "throw", "toss", "air-fry", "airfry",
}

FOOD_WORDS = {
    "chicken", "beef", "pork", "salmon", "shrimp", "tofu", "steak", "lamb",
    "fish", "turkey", "bacon", "sausage",
    "rice", "pasta", "noodle", "noodles", "bread", "flour", "tortilla",
    "onion", "garlic", "tomato", "potato", "pepper", "broccoli",
    "carrot", "celery", "mushroom", "spinach", "avocado", "cucumber",
    "cheese", "cream", "milk", "yogurt", "butter", "egg", "eggs",
    "sugar", "honey", "maple", "cinnamon", "vanilla", "cocoa",
    "chocolate", "strawberry", "blueberry", "banana", "lemon", "lime",
    "salt", "paprika", "cumin", "oregano", "basil", "thyme",
    "olive oil", "soy sauce", "vinegar", "ginger",
    "cook", "bake", "fry", "roast", "grill", "boil", "simmer",
    "stir", "chop", "slice", "dice", "mix", "combine", "whisk",
    "pan", "oven", "skillet", "pot", "bowl",
    "minutes", "degrees", "tablespoon", "teaspoon", "cup",
    "protein", "healthy", "recipe", "ingredient", "delicious", "tasty",
}

# Known real food items
KNOWN_FOODS = {
    # proteins
    "chicken", "chicken breast", "chicken breasts", "chicken thigh", "chicken thighs",
    "chicken wings", "chicken tenders",
    "beef", "ground beef", "steak", "flank steak", "sirloin", "ribeye",
    "pork", "pork chops", "pork belly", "pork loin",
    "salmon", "shrimp", "prawns", "tofu", "tempeh", "turkey", "lamb",
    "bacon", "sausage", "ham", "fish", "tuna", "cod", "tilapia",
    "lobster", "crab", "scallops",
    # grains
    "rice", "pasta", "spaghetti", "noodles", "ramen", "bread",
    "flour", "oats", "oatmeal", "tortilla", "tortillas", "pita",
    "couscous", "quinoa", "breadcrumbs", "panko",
    # dairy
    "cheese", "mozzarella", "parmesan", "cheddar", "cream cheese",
    "greek yogurt", "yogurt", "milk", "heavy cream", "cream",
    "sour cream", "cottage cheese", "butter", "ghee",
    "whipped cream", "egg", "eggs", "egg whites", "egg yolks",
    # vegetables
    "onion", "onions", "garlic", "tomato", "tomatoes", "potato", "potatoes",
    "pepper", "peppers", "bell pepper", "bell peppers",
    "jalapeño", "jalapeno", "serrano",
    "broccoli", "carrot", "carrots", "celery",
    "mushroom", "mushrooms", "spinach", "kale", "lettuce",
    "avocado", "cucumber", "zucchini", "corn", "peas",
    "green beans", "sweet potato", "sweet potatoes", "cabbage",
    "ginger", "scallions", "green onion", "green onions",
    "cilantro", "parsley", "basil", "bean sprouts",
    "edamame", "chickpeas", "black beans", "kidney beans",
    "lentils", "cauliflower", "asparagus", "artichoke",
    # fruits
    "banana", "bananas", "strawberry", "strawberries",
    "blueberry", "blueberries", "raspberry", "raspberries",
    "lemon", "lime", "orange", "apple", "pineapple", "mango",
    "watermelon", "berries", "pumpkin", "coconut", "peach", "pear",
    # fats
    "olive oil", "extra virgin olive oil", "avocado oil",
    "coconut oil", "sesame oil", "butter", "ghee",
    # sauces & condiments
    "soy sauce", "sriracha", "hot sauce", "ketchup", "mustard",
    "mayo", "mayonnaise", "fish sauce", "oyster sauce",
    "teriyaki sauce", "bbq sauce", "barbecue sauce",
    "gochujang", "gochugaru", "tahini", "pesto",
    "rice wine vinegar", "apple cider vinegar", "balsamic vinegar",
    "worcestershire sauce", "hoisin sauce",
    # sweeteners
    "sugar", "brown sugar", "honey", "maple syrup",
    "monk fruit sweetener", "stevia", "agave",
    # baking
    "baking soda", "baking powder", "vanilla", "vanilla extract",
    "cocoa powder", "chocolate", "chocolate chips", "dark chocolate",
    "peanut butter", "almond butter", "almond flour", "coconut flour",
    "protein powder", "whey protein", "powdered egg whites",
    # spices
    "salt", "pepper", "black pepper", "paprika", "smoked paprika",
    "cumin", "oregano", "thyme", "rosemary",
    "chili powder", "chili flakes", "red pepper flakes",
    "cayenne", "cayenne pepper",
    "garlic powder", "onion powder", "cinnamon", "nutmeg",
    "turmeric", "italian seasoning", "everything bagel seasoning",
    "curry powder", "garam masala", "five spice",
    # misc
    "broth", "chicken broth", "beef broth", "vegetable broth", "stock",
    "water", "cornstarch", "arrowroot",
    "peanut butter powder", "wonton wrappers",
    "rice paper", "nori", "sesame seeds",
}

# Words that should NOT be treated as ingredients
NOT_FOOD = {
    "minutes", "seconds", "hours", "time", "degrees",
    "video", "recipe", "step", "way", "thing", "stuff", "hack", "hacks",
    "one", "two", "three", "four", "five", "six",
    "people", "everyone", "guys", "friends", "family", "guests",
    "life", "world", "game", "day", "morning", "night", "week",
    "side", "top", "bottom", "middle", "bit",
    "flavor", "taste", "look", "texture", "color",
    "bite", "piece", "batch", "serving", "portion",
    "fridge", "freezer", "counter", "plate", "container",
    "subscribe", "follow", "comment", "like",
    "health", "bonus", "secret", "secrets",
}


# ═══════════════════════════════════════════════════════════
#  Transcript quality check
# ═══════════════════════════════════════════════════════════

def _is_garbage_transcript(transcript: str) -> bool:
    """Check if the transcript is music/lyrics/gibberish."""
    text = transcript.lower().strip()

    # Too short
    if len(text) < 30:
        return True

    # Transcript is just filler
    clean = text.strip('.!? ')
    if clean in ('music', 'thank you', 'thanks', 'like and subscribe', 'that\'s so good'):
        return True

    # Count meaningful food/cooking words
    words = set(re.findall(r'\b\w+\b', text))
    food_hits = len(words & FOOD_WORDS)
    cooking_hits = len(words & COOKING_VERBS)
    total_words = len(text.split())

    # Very few food/cooking words means probably not a recipe
    if total_words > 20 and (food_hits + cooking_hits) < 2:
        return True

    return False


# ═══════════════════════════════════════════════════════════
#  Ingredient extraction
# ═══════════════════════════════════════════════════════════

def _extract_ingredients_smart(transcript: str) -> list[dict]:
    """
    Extract ingredients by looking for things being USED in cooking context.
    Avoids metaphors and descriptions.
    """
    text_lower = transcript.lower()
    ingredients = []
    seen = set()

    def _add(amount: str, item: str):
        item = _clean_item(item)
        if not item or item in seen or not _is_food(item):
            return
        # Extra check: reject items that look like partial sentences
        if len(item.split()) > 4:
            return
        seen.add(item)
        ingredients.append({"amount": amount.strip(), "item": item})

    # ── 1. Explicit measurements ────────────────────────
    # "2 cups of flour", "1 tbsp butter", "200g chicken"
    meas = r'(\d+[\./]?\d*\s*(?:cup|cups|tbsp|tablespoons?|tsp|teaspoons?|oz|ounces?|lb|lbs?|pounds?|g|grams?|kg|ml|liters?|cloves?|pieces?|cans?|sticks?|pinch(?:es)?|dash(?:es)?|handfuls?|slices?|bunch(?:es)?|scoops?|strips?|fillets?|heads?)s?)\s+(?:of\s+)?([\w][\w\s]{1,30}?)(?:\.|,|\band\b|\bthen\b|\buntil\b|\binto\b|\bto\b|\bin\s+(?:a|the|your)\b|\bfor\b|$)'
    for m in re.finditer(meas, text_lower):
        _add(m.group(1), m.group(2))

    # "a cup of X", "a scoop of X", "a splash of X"
    a_meas = r'(?:a|one)\s+(cup|tbsp|tablespoon|tsp|teaspoon|scoop|splash|drizzle|pinch|handful|dash|stick|can|clove|slice|piece)\s+(?:of\s+)?([\w][\w\s]{1,30}?)(?:\.|,|\band\b|\bthen\b|\buntil\b|$)'
    for m in re.finditer(a_meas, text_lower):
        _add(f"1 {m.group(1)}", m.group(2))

    # ── 2. Action-based: "add X", "grab X", "use X" ────
    action_pat = r'(?:add|grab|take|get|use|need|pour|throw in|toss in|mix in|stir in|fold in|top with|drizzle|layer)\s+(?:some|your|the|a|an|in\s+)?\s*([\w][\w\s]{1,40}?)(?:\.|,|\band\s+then\b|\bthen\b|\buntil\b|\binto\b|\bin\s+(?:a|the)\b|\bon\s+(?:a|the)\b|$)'
    for m in re.finditer(action_pat, text_lower):
        raw = m.group(1).strip()
        # Could be a list: "chicken, rice, and garlic"
        parts = re.split(r',\s*(?:and\s+)?|\s+and\s+', raw)
        for part in parts:
            _add("", part.strip())

    # ── 3. "you'll need X" / "ingredients: X" ──────────
    need_pat = r'(?:you.?ll need|you need|you.?re gonna need|ingredients?\s*:?)\s*([\w][\w\s,and]{5,150}?)(?:\.\s|\n|$)'
    for m in re.finditer(need_pat, text_lower):
        raw = m.group(1).strip()
        parts = re.split(r',\s*(?:and\s+)?|\s+and\s+', raw)
        for part in parts:
            _add("", part.strip())

    # ── 4. Scan for known food items in cooking context ─
    # Only add known foods if they appear near cooking verbs
    sentences = re.split(r'[.!?]+', text_lower)
    for sent in sentences:
        words = sent.split()
        has_cooking = any(w.strip('.,!?;:') in COOKING_VERBS for w in words)
        if not has_cooking and len(words) > 5:
            continue
        for food in KNOWN_FOODS:
            if food in sent and food not in seen:
                # Make sure it's used as an actual ingredient, not a metaphor
                # e.g., "look like baby shrimp" should NOT add shrimp
                metaphor_check = re.search(
                    rf'(?:like|looks?\s+like|resemble|reminds?\s+(?:me\s+)?of|as\s+(?:a|an))\s+[\w\s]{{0,15}}{re.escape(food)}',
                    sent
                )
                if metaphor_check:
                    continue
                _add("", food)

    # Deduplicate overlapping items
    ingredients = _dedupe(ingredients)

    return ingredients[:15]


def _clean_item(raw: str) -> str:
    """Clean an extracted ingredient name."""
    raw = raw.strip().lower()
    # Strip leading filler words
    raw = re.sub(
        r'^(some|your|the|a|an|our|my|this|that|those|these|sliced|diced|chopped|'
        r'minced|fresh|frozen|canned|dried|whole|large|small|medium|thin|thick|'
        r'extra|little|big|nice|good|really|just|also|basically|about)\s+', '', raw
    )
    raw = re.sub(r'^(some|your|the|a|an)\s+', '', raw)  # second pass
    # Strip trailing filler
    raw = re.sub(r'\s+(and|then|until|or|so|now|just|too|also|really|basically|actually|is|are|was|it|them|this|that)$', '', raw)
    raw = raw.strip(' .,;:!?')
    if len(raw) < 2 or len(raw) > 45 or not re.search(r'[a-z]', raw):
        return ""
    return raw


def _is_food(item: str) -> bool:
    """Check if an item is a real food ingredient."""
    item_lower = item.lower().strip()

    # Reject known non-food
    if item_lower in NOT_FOOD:
        return False
    if len(item_lower) < 2:
        return False

    # Accept known foods
    if item_lower in KNOWN_FOODS:
        return True
    # Check if it contains a known food word
    for food in KNOWN_FOODS:
        if food in item_lower:
            return True
        if item_lower in food:
            return True

    # Accept if it ends with a food-like suffix
    food_endings = ['sauce', 'powder', 'flour', 'cream', 'milk', 'juice',
                    'oil', 'butter', 'cheese', 'sugar', 'syrup', 'paste',
                    'seeds', 'nuts', 'broth', 'stock', 'vinegar', 'seasoning']
    if any(item_lower.endswith(e) for e in food_endings):
        return True

    # Accept short multi-word items that look like food
    words = item_lower.split()
    if 1 <= len(words) <= 3 and all(w.isalpha() for w in words):
        # Final sanity check — not a common English non-food word
        single_rejects = {"really", "super", "very", "gonna", "gotta", "wanna",
                          "that", "this", "what", "here", "there", "where",
                          "about", "every", "along", "through", "around", "behind"}
        if item_lower in single_rejects:
            return False
        return True

    return False


def _dedupe(ingredients: list[dict]) -> list[dict]:
    """Remove duplicate/overlapping ingredients."""
    result = []
    seen_bases = set()
    for ing in ingredients:
        item = ing["item"].lower()
        # Base form: "bananas" -> "banana", "sliced chicken" -> "chicken"
        base = item.split()[-1].rstrip('s')
        if len(base) < 2:
            base = item.split()[-1]
        if base not in seen_bases:
            seen_bases.add(base)
            # Prefer version with amount
            result.append(ing)
    return result


# ═══════════════════════════════════════════════════════════
#  Instruction extraction
# ═══════════════════════════════════════════════════════════

def _extract_instructions_smart(transcript: str) -> list[str]:
    """Extract cooking steps from transcript."""
    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', transcript)

    # Also split very long sentences at "then", "and then", "next"
    expanded = []
    for s in sentences:
        if len(s) > 150:
            parts = re.split(r'\s+(?:[Tt]hen|[Aa]nd then|[Nn]ext|[Aa]fter that|[Nn]ow|[Ss]o then)\s+', s)
            expanded.extend(parts)
        else:
            expanded.append(s)
    sentences = expanded

    steps = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence or len(sentence) < 12:
            continue
        if _is_filler(sentence):
            continue

        words = sentence.lower().split()
        has_action = any(w.strip('.,!?;:') in COOKING_VERBS for w in words[:8])
        has_food = any(w.strip('.,!?;:s') in FOOD_WORDS for w in words)

        if has_action or (has_food and len(sentence) > 25):
            step = sentence[0].upper() + sentence[1:]
            if not step.endswith(('.', '!', '?')):
                step += '.'
            if len(step) > 200:
                step = step[:197] + '...'
            steps.append(step)

    # Fallback: if we got very few steps from a decent-length transcript
    if len(steps) < 2 and len(transcript) > 80:
        steps = _extract_instructions_fallback(transcript)

    return steps[:12]


def _extract_instructions_fallback(transcript: str) -> list[str]:
    """Fallback: chunk transcript into reasonable steps."""
    chunks = re.split(
        r'(?<=[.!?])\s+|\s+(?:[Tt]hen|[Aa]nd then|[Nn]ext|[Aa]fter that|[Nn]ow you|[Ss]o you)\s+',
        transcript
    )
    steps = []
    for chunk in chunks:
        chunk = chunk.strip()
        if len(chunk) < 15 or _is_filler(chunk):
            continue
        step = chunk[0].upper() + chunk[1:]
        if not step.endswith(('.', '!', '?')):
            step += '.'
        if len(step) > 200:
            step = step[:197] + '...'
        steps.append(step)
    return steps[:12]


def _is_filler(sentence: str) -> bool:
    """Check if a sentence is just commentary, not a real instruction."""
    s = sentence.lower().strip()
    filler_starts = [
        "hey guys", "what's up", "welcome back", "hello everyone",
        "subscribe", "like and", "follow me", "check out",
        "let me know", "comment below", "share this",
        "i love this", "i think this", "i really love",
        "one of my", "this is one of", "this is my favorite",
        "you guys are", "i hope you", "thanks for watching",
        "peace", "see you", "bye", "that's it for",
        "don't forget to", "hit the", "smash the",
        "trust me", "you're gonna love",
        "nobody believes", "discover the secrets",
    ]
    for f in filler_starts:
        if s.startswith(f):
            return True
    # Very short exclamations
    if len(s) < 20 and any(w in s for w in ["wow", "bam", "boom", "yes", "oh my", "perfect", "amazing", "so good", "that's it"]):
        return True
    return False


# ═══════════════════════════════════════════════════════════
#  Title extraction
# ═══════════════════════════════════════════════════════════

def _extract_title(caption: str, transcript: str) -> str:
    """Extract or derive a clean recipe title."""
    # 1. Try caption
    if caption and len(caption.strip()) > 5:
        title = caption.strip()
        title = re.sub(r'#\w+', '', title).strip()
        title = title.split('\n')[0].strip()
        if len(title) > 60:
            title = title[:57] + '...'
        if len(title) > 5:
            return title.title()

    text = transcript.strip()

    # 2. "let's make X", "how to make X", "making X"
    name_patterns = [
        r"(?:[Ll]et'?s make|[Hh]ow to make|[Ww]e'?re making|[Ii]'?m making|[Mm]aking)\s+([\w\s]+?)(?:\.|!|,|\bfor\b|\bmy\b|\n|$)",
        r"(?:[Tt]his is|[Hh]ere'?s|[Tt]ry this)\s+(?:my|the|a|an)?\s*([\w\s]+?)\s*(?:recipe|that|which|\.|!|,|\n|$)",
    ]
    for pattern in name_patterns:
        match = re.search(pattern, text)
        if match:
            title = match.group(1).strip()
            if 3 < len(title) < 50:
                return title.title()

    # 3. Try to identify the main dish from the transcript
    main = _identify_main_dish(transcript)
    if main:
        return main.title()

    # 4. First sentence, cleaned — but keep it short and meaningful
    first = text.split('.')[0].strip() if text else ""
    if first and len(first) > 5:
        # Trim to something reasonable
        if len(first) > 45:
            first = first[:42].rsplit(' ', 1)[0] + '...'
        return first.title()

    return "Untitled Recipe"


def _identify_main_dish(transcript: str) -> str:
    """Identify the main dish name from transcript content."""
    text = transcript.lower()

    # Known dish names
    dishes = [
        "mongolian beef", "beef bulgogi", "bulgogi", "teriyaki chicken",
        "garlic chili chicken", "garlic butter ramen", "chicken ramen",
        "fried rice", "stir fry", "pad thai", "lo mein", "chow mein",
        "mac and cheese", "grilled cheese", "french toast", "garlic bread",
        "chicken tenders", "chicken wings", "fried chicken", "buffalo chicken",
        "nashville hot chicken", "baked chicken", "roast chicken",
        "orange chicken", "honey garlic chicken",
        "pasta", "ramen", "curry", "tacos", "burrito", "burger",
        "sandwich", "wrap", "quesadilla", "nachos", "pizza",
        "soup", "stew", "chili", "chowder",
        "pancakes", "waffles", "omelette",
        "brownies", "cookies", "brownie", "cake", "cheesecake",
        "smoothie", "parfait", "cinnamon rolls",
        "meatballs", "meatloaf",
        "pinwheel burger", "skillet cookie",
        "caramelized bananas", "protein bowl",
    ]
    for dish in dishes:
        if dish in text:
            return dish

    # "[modifier] [protein]" pattern
    proteins = ["chicken", "beef", "pork", "salmon", "shrimp", "turkey", "lamb", "fish"]
    for protein in proteins:
        if protein not in text:
            continue
        # Skip if only mentioned in a metaphor context
        metaphor = re.search(
            rf'(?:like|looks?\s+like|resemble)\s+[\w\s]{{0,15}}{re.escape(protein)}',
            text
        )
        non_metaphor = re.search(
            rf'(?:add|cook|fry|bake|season|marinate|slice|chop|grab|take|your)\s+[\w\s]{{0,10}}{re.escape(protein)}',
            text
        )
        if metaphor and not non_metaphor:
            continue  # only used as metaphor

        m = re.search(rf'([\w\s]{{2,25}})\s+{protein}', text)
        if m:
            mod = m.group(1).strip()
            mod_words = [w for w in mod.split()[-2:] if w not in {'the', 'a', 'an', 'your', 'my', 'this', 'some', 'and', 'with', 'or', 'of', 'in', 'on', 'is', 'are'}]
            if mod_words:
                return ' '.join(mod_words) + ' ' + protein
        return protein + " recipe"

    return ""


# ═══════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════

def _replace_seed_oils(ingredients: list[dict]) -> list[dict]:
    cleaned = []
    for ing in ingredients:
        item_lower = ing["item"].lower()
        if any(oil in item_lower for oil in SEED_OILS):
            ing["item"] = "butter"
        elif "cooking spray" in item_lower or item_lower == "spray":
            ing["item"] = "butter"
            ing["amount"] = ing["amount"] or "1 tbsp"
        cleaned.append(ing)
    return cleaned


def _guess_equipment(text: str) -> list[str]:
    equipment = set()
    t = text.lower()
    mapping = {
        "frying pan": ["fry", "frying pan", "skillet", "pan fry", "saute", "sear"],
        "baking sheet": ["baking sheet", "sheet pan", "cookie sheet"],
        "oven": ["oven", "bake", "roast", "broil", "preheat"],
        "sauce pot": ["pot", "boil", "simmer", "soup", "stew", "broth"],
        "microwave": ["microwave"],
        "mixing bowl": ["bowl", "mix", "combine", "whisk"],
        "cutting board": ["cut", "chop", "dice", "slice", "mince"],
    }
    for equip, keywords in mapping.items():
        if any(kw in t for kw in keywords):
            equipment.add(equip)
    return sorted(equipment) or ["frying pan"]


def _guess_category(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["breakfast", "morning", "oatmeal", "pancake", "waffle", "brunch", "cereal"]):
        return "breakfast"
    if any(w in t for w in ["dessert", "cake", "cookie", "brownie", "sweet treat", "chocolate chip", "ice cream", "cheesecake"]):
        return "dessert"
    if any(w in t for w in ["snack", "appetizer", "dip", "chips", "bite"]):
        return "snack"
    if any(w in t for w in ["salad", "light", "side dish"]):
        return "side"
    return "dinner"


# ═══════════════════════════════════════════════════════════
#  Main local extractor
# ═══════════════════════════════════════════════════════════

def extract_recipe_local(transcript: str, caption: str = "") -> dict:
    """Extract recipe using improved rule-based parsing (no API needed)."""
    if not transcript or len(transcript.strip()) < 20:
        return {"error": "Transcript too short to extract recipe"}

    if _is_garbage_transcript(transcript):
        return {"error": "Transcript appears to be music/lyrics/gibberish, not a recipe"}

    title = _extract_title(caption, transcript)
    ingredients = _extract_ingredients_smart(transcript)
    instructions = _extract_instructions_smart(transcript)

    ingredients = _replace_seed_oils(ingredients)

    if not ingredients and not instructions:
        return {"error": "Could not parse recipe from transcript"}

    text_lower = (caption + " " + transcript).lower()

    recipe = {
        "title": title,
        "description": f"Simple {title.lower()} recipe",
        "prep_time": "10 minutes",
        "cook_time": "20 minutes",
        "total_time": "30 minutes",
        "servings": "2-4",
        "ingredients": ingredients,
        "instructions": instructions or ["Follow along with the video for detailed steps."],
        "equipment": _guess_equipment(text_lower),
        "tips": "Adjust seasoning to taste.",
        "substitutions_made": [],
        "category": _guess_category(text_lower),
    }

    return _validate_and_clean(recipe)


def _validate_and_clean(recipe: dict) -> dict:
    if "error" in recipe:
        return recipe

    if "ingredients" in recipe:
        for ing in recipe["ingredients"]:
            if any(oil in ing.get("item", "").lower() for oil in SEED_OILS):
                ing["item"] = "butter"

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


# ═══════════════════════════════════════════════════════════
#  Save / Load
# ═══════════════════════════════════════════════════════════

def save_recipes(recipes: list[dict]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(RECIPES_FILE, 'w') as f:
        json.dump(recipes, f, indent=2)
    print(f"[Recipes] Saved {len(recipes)} recipes to {RECIPES_FILE}")


def load_recipes() -> list[dict]:
    if RECIPES_FILE.exists():
        with open(RECIPES_FILE, 'r') as f:
            return json.load(f)
    return []
