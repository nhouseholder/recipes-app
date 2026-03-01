"""
Grocery List Generator
Picks a random recipe and builds a detailed grocery list
with specific aisle/section guidance for each ingredient.
"""

import json
import random
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
RECIPES_FILE = DATA_DIR / "recipes.json"
GROCERY_HISTORY_FILE = DATA_DIR / "grocery_history.json"

# ── Grocery store aisle mapping ──────────────────────────────
# Maps ingredient keywords → (aisle/section, specific location tip)
AISLE_MAP = {
    # Produce
    "onion": ("Produce", "Loose onions bin, usually near potatoes & garlic"),
    "garlic": ("Produce", "Near the onions/shallots, look for loose heads or pre-peeled jars"),
    "tomato": ("Produce", "Tomato section with vine, roma, cherry varieties"),
    "potato": ("Produce", "Root vegetable bin, near onions"),
    "pepper": ("Produce", "Bell peppers are in produce; black pepper is in the spice aisle"),
    "bell pepper": ("Produce", "Next to other fresh peppers — green, red, yellow"),
    "broccoli": ("Produce", "Refrigerated produce section with other fresh vegetables"),
    "spinach": ("Produce", "Bagged salads / leafy greens refrigerated section"),
    "lettuce": ("Produce", "Bagged salads / leafy greens refrigerated section"),
    "avocado": ("Produce", "Usually near the tomatoes and limes"),
    "lemon": ("Produce", "Citrus section — lemons, limes, oranges"),
    "lime": ("Produce", "Citrus section with lemons"),
    "ginger": ("Produce", "Near the garlic and specialty produce"),
    "cilantro": ("Produce", "Fresh herbs section, usually refrigerated near salads"),
    "parsley": ("Produce", "Fresh herbs section"),
    "basil": ("Produce", "Fresh herbs section, sometimes in clamshell containers"),
    "mushroom": ("Produce", "Refrigerated produce, near the herbs"),
    "zucchini": ("Produce", "Fresh vegetables section"),
    "carrot": ("Produce", "Root vegetables, or pre-cut/bagged near salads"),
    "celery": ("Produce", "Near the carrots and bagged salads"),
    "jalapeño": ("Produce", "Fresh peppers section"),
    "green onion": ("Produce", "Fresh herbs/greens section, bundled"),
    "scallion": ("Produce", "Fresh herbs/greens section, bundled — same as green onion"),
    "sweet potato": ("Produce", "Root vegetable section near regular potatoes"),
    "corn": ("Produce", "Seasonal fresh corn, or check canned/frozen aisle"),
    "cabbage": ("Produce", "Near the lettuce and leafy greens"),
    "kale": ("Produce", "Leafy greens, near spinach and bagged salads"),
    "cucumber": ("Produce", "Fresh vegetables near tomatoes"),

    # Meat & Protein
    "chicken": ("Meat & Seafood", "Fresh chicken — breasts, thighs, drumsticks in the meat cooler"),
    "beef": ("Meat & Seafood", "Fresh beef section — ground, steaks, roasts"),
    "ground beef": ("Meat & Seafood", "Ground meat section of the meat cooler"),
    "steak": ("Meat & Seafood", "Beef steaks section, ask butcher for recommendations"),
    "pork": ("Meat & Seafood", "Pork section — chops, tenderloin, ground pork"),
    "bacon": ("Meat & Seafood", "Packaged bacon, near the deli meats and hot dogs"),
    "sausage": ("Meat & Seafood", "Near the bacon and packaged meats"),
    "salmon": ("Meat & Seafood", "Fresh seafood counter or packaged fish cooler"),
    "shrimp": ("Meat & Seafood", "Fresh seafood counter, or frozen section (usually cheaper)"),
    "fish": ("Meat & Seafood", "Fresh seafood counter"),
    "turkey": ("Meat & Seafood", "Near the chicken — ground turkey, deli turkey"),
    "lamb": ("Meat & Seafood", "Specialty meats section, may need to ask butcher"),
    "tofu": ("Produce / Deli", "Refrigerated section near produce or in the natural foods aisle"),

    # Dairy & Eggs
    "egg": ("Dairy & Eggs", "Egg section — usually end of the dairy aisle"),
    "butter": ("Dairy & Eggs", "Butter/margarine section of dairy cooler"),
    "milk": ("Dairy & Eggs", "Dairy wall — whole, 2%, skim along the back wall"),
    "cream": ("Dairy & Eggs", "Near the milk — heavy cream, half & half"),
    "heavy cream": ("Dairy & Eggs", "With the milk and creamers on the dairy wall"),
    "sour cream": ("Dairy & Eggs", "Near the yogurt and cottage cheese"),
    "cream cheese": ("Dairy & Eggs", "Near the yogurt/sour cream or by the bagels"),
    "yogurt": ("Dairy & Eggs", "Yogurt section of the dairy aisle"),
    "cheese": ("Dairy & Eggs", "Cheese section — blocks, shredded bags, sliced in dairy aisle"),
    "parmesan": ("Dairy & Eggs", "Specialty cheese section, or grated in the pasta aisle"),
    "mozzarella": ("Dairy & Eggs", "Shredded cheese bags or fresh mozzarella near deli"),
    "cheddar": ("Dairy & Eggs", "Block/shredded cheese section in dairy"),
    "ghee": ("International / Dairy", "Indian food section, or near the butter in some stores"),

    # Pantry / Dry Goods
    "rice": ("Rice & Grains Aisle", "Rice section — white, brown, jasmine, basmati"),
    "pasta": ("Pasta Aisle", "Pasta section — spaghetti, penne, etc. with the sauces"),
    "noodle": ("Pasta / International Aisle", "Regular pasta aisle, or Asian noodles in international"),
    "bread": ("Bakery / Bread Aisle", "Bread aisle, or fresh in the bakery section"),
    "tortilla": ("Bread / International Aisle", "Near the bread, or in the Mexican food section"),
    "flour": ("Baking Aisle", "Baking section — all-purpose, bread flour, etc."),
    "sugar": ("Baking Aisle", "Baking section with flour"),
    "brown sugar": ("Baking Aisle", "Baking section near white sugar"),
    "baking powder": ("Baking Aisle", "Baking section, small cans/containers"),
    "baking soda": ("Baking Aisle", "Baking section, orange Arm & Hammer box"),
    "vanilla": ("Baking Aisle", "Baking section with extracts"),
    "chocolate": ("Baking Aisle", "Baking section for chips/bars, or candy aisle"),
    "oats": ("Cereal / Baking Aisle", "Either cereal aisle or baking section"),
    "breadcrumbs": ("Baking / Bread Aisle", "Near the stuffing mixes, or in baking"),
    "panko": ("International / Baking Aisle", "Asian section or near regular breadcrumbs"),

    # Canned & Jarred
    "tomato sauce": ("Canned Goods Aisle", "Canned tomatoes section — sauce, paste, diced"),
    "tomato paste": ("Canned Goods Aisle", "Small cans near other canned tomatoes"),
    "diced tomato": ("Canned Goods Aisle", "Canned tomato section"),
    "beans": ("Canned Goods Aisle", "Canned beans — black, kidney, pinto, chickpeas"),
    "chickpea": ("Canned Goods Aisle", "Canned beans section, or dried in bulk"),
    "coconut milk": ("International / Canned Aisle", "Asian food section, or with canned goods"),
    "broth": ("Canned Goods / Soup Aisle", "Broth/stock section near the soups — chicken, beef, veggie"),
    "stock": ("Canned Goods / Soup Aisle", "Next to the broths and soups"),

    # Oils & Vinegar
    "olive oil": ("Oil & Vinegar Aisle", "Cooking oils section — look for extra virgin"),
    "avocado oil": ("Oil & Vinegar Aisle", "Cooking oils section, or natural/health food aisle"),
    "coconut oil": ("Oil & Vinegar Aisle", "Cooking oils, or natural foods section"),
    "vinegar": ("Oil & Vinegar Aisle", "Next to the cooking oils — white, apple cider, balsamic"),
    "balsamic": ("Oil & Vinegar Aisle", "Vinegar section"),

    # Condiments & Sauces
    "soy sauce": ("Condiments / International Aisle", "Asian food section, or condiments aisle"),
    "hot sauce": ("Condiments Aisle", "Hot sauce / salsa section"),
    "ketchup": ("Condiments Aisle", "Ketchup/mustard/mayo section"),
    "mustard": ("Condiments Aisle", "Next to ketchup"),
    "mayo": ("Condiments Aisle", "With ketchup and mustard"),
    "mayonnaise": ("Condiments Aisle", "With ketchup and mustard"),
    "honey": ("Condiments / Baking Aisle", "Near the peanut butter & jelly, or baking section"),
    "maple syrup": ("Breakfast / Condiments Aisle", "Pancake/breakfast section with syrups"),
    "worcestershire": ("Condiments Aisle", "With steak sauces and marinades"),
    "sriracha": ("Condiments / International Aisle", "Hot sauce section or Asian foods"),
    "salsa": ("Condiments Aisle", "Chips & salsa section, or near Mexican foods"),
    "bbq sauce": ("Condiments Aisle", "Near the ketchup and steak sauces"),
    "teriyaki": ("International Aisle", "Asian food section with soy sauce"),
    "fish sauce": ("International Aisle", "Asian food section"),
    "oyster sauce": ("International Aisle", "Asian food section"),
    "hoisin": ("International Aisle", "Asian food section"),
    "sesame oil": ("International Aisle", "Asian food section"),
    "peanut butter": ("Condiments / Spreads Aisle", "Peanut butter & jelly section"),

    # Spices & Seasonings
    "salt": ("Spice Aisle", "Spice aisle — table salt, kosher salt, sea salt"),
    "black pepper": ("Spice Aisle", "Spice aisle — ground pepper or peppercorns with grinder"),
    "paprika": ("Spice Aisle", "Alphabetical in the spice rack — regular or smoked"),
    "cumin": ("Spice Aisle", "Alphabetical in the spice rack"),
    "oregano": ("Spice Aisle", "Alphabetical in the spice rack"),
    "thyme": ("Spice Aisle", "Alphabetical in the spice rack"),
    "rosemary": ("Spice Aisle", "Alphabetical in the spice rack (or fresh in produce)"),
    "chili powder": ("Spice Aisle", "Spice rack, or Mexican foods section"),
    "cayenne": ("Spice Aisle", "Spice rack — cayenne pepper"),
    "cinnamon": ("Spice Aisle", "Spice rack or baking section"),
    "nutmeg": ("Spice Aisle", "Spice rack"),
    "garlic powder": ("Spice Aisle", "Spice rack, very common — look near onion powder"),
    "onion powder": ("Spice Aisle", "Spice rack near garlic powder"),
    "italian seasoning": ("Spice Aisle", "Spice rack — pre-mixed blends section"),
    "red pepper flakes": ("Spice Aisle", "Spice rack, or Italian foods section"),
    "bay leaf": ("Spice Aisle", "Spice rack"),
    "turmeric": ("Spice Aisle", "Spice rack"),
    "curry powder": ("Spice Aisle", "Spice rack or international aisle"),
    "taco seasoning": ("Spice / Mexican Aisle", "Spice rack or Mexican food section, packet mixes"),

    # Frozen
    "frozen": ("Frozen Foods Aisle", "Frozen section — veggies, fruits, meals"),
    "ice cream": ("Frozen Foods Aisle", "Frozen desserts section"),

    # Beverages
    "wine": ("Wine & Spirits / Grocery", "Wine section, or cooking wine in vinegar aisle"),
    "beer": ("Beer & Wine", "Beer section, or near checkout"),
    "coffee": ("Coffee & Tea Aisle", "Coffee aisle"),

    # Nuts & Seeds
    "almond": ("Nuts & Snacks Aisle", "Nut section, or baking aisle for slivered/sliced"),
    "walnut": ("Nuts & Snacks Aisle", "Nut section or baking aisle"),
    "pecan": ("Nuts & Snacks Aisle", "Nut section or baking aisle"),
    "cashew": ("Nuts & Snacks Aisle", "Nut snacks section"),
    "peanut": ("Nuts & Snacks Aisle", "Nut section"),
    "sesame seed": ("International / Spice Aisle", "Spice rack or Asian foods section"),
}

# Default for anything not matched
DEFAULT_AISLE = ("Check Grocery Aisles", "Ask store staff for the best location")


def get_aisle_info(ingredient_name: str) -> tuple[str, str]:
    """Look up aisle and location tip for an ingredient."""
    name_lower = ingredient_name.lower().strip()

    # Try exact-ish matches first (longest match wins)
    best_match = None
    best_len = 0
    for keyword, info in AISLE_MAP.items():
        if keyword in name_lower and len(keyword) > best_len:
            best_match = info
            best_len = len(keyword)

    return best_match or DEFAULT_AISLE


def pick_weekly_recipe(exclude_recent: int = 4) -> dict | None:
    """Pick a random recipe, avoiding recently picked ones."""
    if not RECIPES_FILE.exists():
        return None

    with open(RECIPES_FILE) as f:
        recipes = json.load(f)

    valid = [r for r in recipes if "error" not in r]
    if not valid:
        return None

    # Load history to avoid repeats
    history = _load_history()
    recent_ids = [h.get("source_id") for h in history[-exclude_recent:]]

    # Prefer recipes not recently picked
    fresh = [r for r in valid if r.get("source_id") not in recent_ids]
    pool = fresh if fresh else valid

    chosen = random.choice(pool)
    return chosen


def build_grocery_list(recipe: dict) -> dict:
    """
    Build a detailed grocery list from a recipe, with aisle/section info
    for each ingredient.
    """
    items = []
    for ing in recipe.get("ingredients", []):
        item_name = ing.get("item", "")
        amount = ing.get("amount", "")
        aisle, tip = get_aisle_info(item_name)

        items.append({
            "item": item_name,
            "amount": amount,
            "aisle": aisle,
            "tip": tip,
        })

    # Group by aisle for easier shopping
    aisles = {}
    for item in items:
        aisle = item["aisle"]
        if aisle not in aisles:
            aisles[aisle] = []
        aisles[aisle].append(item)

    return {
        "recipe_title": recipe.get("title", "Unknown Recipe"),
        "recipe_description": recipe.get("description", ""),
        "servings": recipe.get("servings", "2-4"),
        "prep_time": recipe.get("total_time", "30 minutes"),
        "items": items,
        "by_aisle": aisles,
        "total_items": len(items),
    }


def format_grocery_list_text(grocery: dict) -> str:
    """Format the grocery list as a nice text string for email/SMS."""
    lines = []
    lines.append(f"🍳 THIS WEEK'S RECIPE: {grocery['recipe_title']}")
    lines.append(f"   {grocery['recipe_description']}")
    lines.append(f"   Servings: {grocery['servings']} | Time: {grocery['prep_time']}")
    lines.append("")
    lines.append("=" * 50)
    lines.append("🛒 GROCERY LIST")
    lines.append("=" * 50)

    for aisle, items in grocery["by_aisle"].items():
        lines.append("")
        lines.append(f"📍 {aisle.upper()}")
        lines.append("-" * 40)
        for item in items:
            amount_str = f" ({item['amount']})" if item['amount'] else ""
            lines.append(f"  □ {item['item']}{amount_str}")
            lines.append(f"    → {item['tip']}")

    lines.append("")
    lines.append(f"Total items: {grocery['total_items']}")
    lines.append("")
    lines.append("Happy cooking! 🎉")
    return "\n".join(lines)


def format_grocery_list_html(grocery: dict) -> str:
    """Format the grocery list as HTML for email."""
    html = f"""
    <div style="font-family: -apple-system, Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #1a1a2e; color: #e0e0e0; padding: 30px; border-radius: 12px;">
        <h1 style="color: #ff6b6b; text-align: center;">🍳 This Week's Recipe</h1>
        <h2 style="color: #ffffff; text-align: center; margin-bottom: 5px;">{grocery['recipe_title']}</h2>
        <p style="color: #aaa; text-align: center;">{grocery['recipe_description']}</p>
        <p style="color: #aaa; text-align: center;">Servings: {grocery['servings']} | Time: {grocery['prep_time']}</p>

        <hr style="border: 1px solid #333; margin: 20px 0;">

        <h2 style="color: #ff6b6b;">🛒 Grocery List</h2>
    """

    for aisle, items in grocery["by_aisle"].items():
        html += f"""
        <div style="background: #16213e; padding: 15px; border-radius: 8px; margin-bottom: 12px;">
            <h3 style="color: #4ecdc4; margin-top: 0;">📍 {aisle}</h3>
            <ul style="list-style: none; padding: 0;">
        """
        for item in items:
            amount_str = f" <span style='color: #888;'>({item['amount']})</span>" if item['amount'] else ""
            html += f"""
                <li style="padding: 8px 0; border-bottom: 1px solid #1a1a2e;">
                    <strong>□ {item['item']}</strong>{amount_str}<br>
                    <span style="color: #888; font-size: 0.85em;">→ {item['tip']}</span>
                </li>
            """
        html += "</ul></div>"

    html += f"""
        <p style="text-align: center; color: #888; margin-top: 20px;">
            Total items: {grocery['total_items']} | Happy cooking! 🎉
        </p>
    </div>
    """
    return html


def save_to_history(recipe: dict, grocery: dict):
    """Save this week's pick to history."""
    history = _load_history()
    history.append({
        "source_id": recipe.get("source_id", ""),
        "title": recipe.get("title", ""),
        "date": __import__("datetime").datetime.now().isoformat(),
        "items_count": grocery.get("total_items", 0),
    })
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(GROCERY_HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)


def _load_history() -> list:
    if GROCERY_HISTORY_FILE.exists():
        with open(GROCERY_HISTORY_FILE) as f:
            return json.load(f)
    return []
