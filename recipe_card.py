"""
Recipe Card Image Generator
Creates beautiful, phone-friendly JPG recipe cards with grocery lists.
Each card is a single image ready to be sent via email/MMS.
"""

import hashlib
import json
import random
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

DATA_DIR = Path(__file__).parent / "data"
CARDS_DIR = DATA_DIR / "cards"
RECIPES_FILE = DATA_DIR / "recipes.json"

# ── Design constants ─────────────────────────────────────────
SCALE = 3  # 3x for Retina / high-DPI screens
CARD_WIDTH = 1080 * SCALE
MAX_HEIGHT = 4000 * SCALE  # safety cap
PADDING = 60 * SCALE
CONTENT_WIDTH = CARD_WIDTH - PADDING * 2

# Color palette — warm, appetizing, modern (defaults / fallback)
BG_COLOR = (25, 25, 35)           # deep navy
CARD_BG = (35, 37, 50)            # slightly lighter card
HEADER_BG = (220, 80, 60)         # warm red-orange accent
ACCENT = (255, 140, 66)           # orange
ACCENT2 = (120, 200, 150)         # sage green
TEXT_WHITE = (240, 240, 245)      # soft white
TEXT_LIGHT = (190, 195, 210)      # light gray
TEXT_DIM = (130, 135, 155)        # muted
DIVIDER_COLOR = (55, 58, 75)      # subtle line
AISLE_BG = (45, 48, 65)           # section background
CHECKBOX_COLOR = (100, 105, 125)  # checkbox outline
BADGE_BG = (50, 55, 75)           # time/serving badge bg

# ── Unique color palettes ────────────────────────────────────
# Each recipe gets a deterministic palette based on its title hash,
# so every card looks distinct but the same recipe always matches.
COLOR_PALETTES = [
    {   # 0: Ember — warm red-orange (original)
        "bg": (25, 25, 35), "header": (220, 80, 60),
        "accent": (255, 140, 66), "accent2": (120, 200, 150),
        "text_white": (240, 240, 245), "text_light": (190, 195, 210),
        "text_dim": (130, 135, 155), "divider": (55, 58, 75),
        "aisle_bg": (45, 48, 65), "checkbox": (100, 105, 125),
        "badge_bg": (50, 55, 75), "grocery_accent": (255, 200, 80),
    },
    {   # 1: Ocean — deep teal with aqua highlights
        "bg": (18, 30, 38), "header": (30, 130, 150),
        "accent": (80, 210, 210), "accent2": (255, 150, 120),
        "text_white": (235, 242, 245), "text_light": (180, 200, 210),
        "text_dim": (120, 145, 158), "divider": (45, 65, 78),
        "aisle_bg": (35, 55, 68), "checkbox": (85, 115, 130),
        "badge_bg": (40, 60, 72), "grocery_accent": (255, 200, 100),
    },
    {   # 2: Forest — earthy green with golden accents
        "bg": (20, 30, 22), "header": (55, 120, 70),
        "accent": (180, 220, 100), "accent2": (220, 170, 100),
        "text_white": (238, 242, 235), "text_light": (185, 200, 185),
        "text_dim": (125, 145, 128), "divider": (50, 65, 52),
        "aisle_bg": (40, 55, 42), "checkbox": (90, 110, 92),
        "badge_bg": (45, 60, 48), "grocery_accent": (240, 200, 90),
    },
    {   # 3: Berry — rich purple with lavender
        "bg": (30, 20, 35), "header": (140, 60, 130),
        "accent": (210, 140, 220), "accent2": (120, 210, 180),
        "text_white": (242, 238, 245), "text_light": (200, 190, 210),
        "text_dim": (140, 130, 155), "divider": (62, 50, 72),
        "aisle_bg": (52, 42, 62), "checkbox": (110, 100, 125),
        "badge_bg": (58, 48, 68), "grocery_accent": (255, 190, 100),
    },
    {   # 4: Sunset — amber gold with cool blue contrast
        "bg": (32, 25, 20), "header": (200, 120, 40),
        "accent": (255, 190, 70), "accent2": (160, 200, 220),
        "text_white": (245, 242, 235), "text_light": (210, 200, 185),
        "text_dim": (155, 140, 125), "divider": (70, 58, 48),
        "aisle_bg": (58, 50, 40), "checkbox": (120, 108, 95),
        "badge_bg": (62, 55, 45), "grocery_accent": (255, 210, 110),
    },
    {   # 5: Terracotta — warm clay with sage
        "bg": (35, 25, 22), "header": (185, 95, 65),
        "accent": (240, 160, 110), "accent2": (130, 185, 160),
        "text_white": (245, 240, 238), "text_light": (210, 195, 190),
        "text_dim": (150, 135, 130), "divider": (72, 55, 48),
        "aisle_bg": (60, 46, 40), "checkbox": (120, 105, 98),
        "badge_bg": (65, 50, 44), "grocery_accent": (255, 200, 100),
    },
    {   # 6: Coral — midnight with salmon pink
        "bg": (18, 18, 28), "header": (220, 100, 100),
        "accent": (255, 155, 140), "accent2": (140, 190, 230),
        "text_white": (240, 238, 242), "text_light": (195, 192, 205),
        "text_dim": (135, 132, 150), "divider": (52, 52, 68),
        "aisle_bg": (42, 42, 58), "checkbox": (100, 100, 120),
        "badge_bg": (48, 48, 64), "grocery_accent": (255, 200, 120),
    },
    {   # 7: Sage — soft green kitchen
        "bg": (25, 30, 25), "header": (100, 140, 90),
        "accent": (180, 215, 160), "accent2": (215, 175, 130),
        "text_white": (240, 244, 238), "text_light": (192, 200, 190),
        "text_dim": (132, 142, 130), "divider": (52, 60, 52),
        "aisle_bg": (42, 50, 42), "checkbox": (95, 108, 95),
        "badge_bg": (48, 56, 48), "grocery_accent": (230, 200, 100),
    },
    {   # 8: Espresso — rich coffee brown
        "bg": (30, 22, 18), "header": (120, 80, 55),
        "accent": (210, 170, 120), "accent2": (140, 200, 180),
        "text_white": (244, 240, 235), "text_light": (205, 195, 185),
        "text_dim": (148, 138, 128), "divider": (65, 52, 44),
        "aisle_bg": (55, 44, 36), "checkbox": (112, 100, 90),
        "badge_bg": (60, 48, 40), "grocery_accent": (240, 195, 90),
    },
    {   # 9: Plum — deep plum with gold
        "bg": (28, 20, 32), "header": (120, 50, 100),
        "accent": (230, 180, 80), "accent2": (120, 200, 200),
        "text_white": (242, 238, 244), "text_light": (200, 192, 208),
        "text_dim": (142, 132, 152), "divider": (58, 48, 65),
        "aisle_bg": (48, 38, 55), "checkbox": (108, 98, 118),
        "badge_bg": (54, 44, 60), "grocery_accent": (255, 210, 100),
    },
    {   # 10: Slate — cool gray with rust accent
        "bg": (25, 28, 32), "header": (175, 85, 55),
        "accent": (230, 145, 90), "accent2": (110, 175, 220),
        "text_white": (240, 242, 245), "text_light": (192, 198, 208),
        "text_dim": (130, 138, 150), "divider": (54, 58, 66),
        "aisle_bg": (44, 48, 56), "checkbox": (98, 104, 116),
        "badge_bg": (50, 54, 62), "grocery_accent": (255, 195, 90),
    },
    {   # 11: Rose — dusty rose with mint
        "bg": (32, 22, 28), "header": (180, 75, 100),
        "accent": (240, 150, 170), "accent2": (150, 210, 180),
        "text_white": (244, 238, 240), "text_light": (208, 192, 200),
        "text_dim": (148, 132, 142), "divider": (66, 48, 56),
        "aisle_bg": (56, 40, 48), "checkbox": (115, 98, 108),
        "badge_bg": (60, 44, 52), "grocery_accent": (255, 200, 110),
    },
]


def _pick_palette(recipe: dict) -> dict:
    """Deterministically pick a color palette based on recipe title."""
    title = recipe.get("title", "")
    h = int(hashlib.md5(title.encode()).hexdigest(), 16)
    return COLOR_PALETTES[h % len(COLOR_PALETTES)]

# ── Font setup ───────────────────────────────────────────────
def _load_fonts():
    """Load system fonts with fallbacks."""
    fonts = {}
    
    # Try Avenir (clean, modern) → Helvetica Neue → Arial → default
    title_paths = [
        "/System/Library/Fonts/Avenir Next.ttc",
        "/System/Library/Fonts/Avenir.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ]
    body_paths = [
        "/System/Library/Fonts/Avenir Next.ttc",
        "/System/Library/Fonts/Avenir.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    
    def try_load(paths, size, index=0):
        for p in paths:
            try:
                return ImageFont.truetype(p, size, index=index)
            except (OSError, IndexError):
                try:
                    return ImageFont.truetype(p, size)
                except OSError:
                    continue
        return ImageFont.load_default()
    
    # Title: bold weight (index varies by font collection)
    fonts["title"] = try_load(title_paths, 42 * SCALE, index=9)     # Avenir Next Bold
    fonts["heading"] = try_load(title_paths, 28 * SCALE, index=9)
    fonts["subhead"] = try_load(title_paths, 22 * SCALE, index=5)   # Avenir Next Demi
    fonts["body"] = try_load(body_paths, 21 * SCALE, index=0)
    fonts["body_bold"] = try_load(body_paths, 21 * SCALE, index=5)
    fonts["small"] = try_load(body_paths, 18 * SCALE, index=0)
    fonts["tiny"] = try_load(body_paths, 15 * SCALE, index=0)
    fonts["emoji"] = try_load(body_paths, 22 * SCALE, index=0)
    
    return fonts

FONTS = None

def _get_fonts():
    global FONTS
    if FONTS is None:
        FONTS = _load_fonts()
    return FONTS


# ── Drawing helpers ──────────────────────────────────────────
def _rounded_rect(draw, xy, radius, fill, outline=None):
    """Draw a rounded rectangle."""
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline)


def _text_height(draw, text, font, max_width):
    """Calculate height of wrapped text."""
    lines = _wrap_text(text, font, max_width, draw)
    if not lines:
        return 0
    bbox = draw.textbbox((0, 0), "Ay", font=font)
    line_h = bbox[3] - bbox[1] + 6 * SCALE
    return line_h * len(lines)


def _wrap_text(text, font, max_width, draw):
    """Word-wrap text to fit within max_width."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines if lines else [""]


def _draw_wrapped(draw, pos, text, font, fill, max_width, line_spacing=None):
    """Draw word-wrapped text. Returns final y position."""
    if line_spacing is None:
        line_spacing = 6 * SCALE
    x, y = pos
    lines = _wrap_text(text, font, max_width, draw)
    bbox = draw.textbbox((0, 0), "Ay", font=font)
    line_h = bbox[3] - bbox[1] + line_spacing
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h
    return y


# ── Main card generator ─────────────────────────────────────
def generate_recipe_card(recipe: dict, grocery: dict = None) -> Path:
    """
    Generate a beautiful recipe card JPG.
    Returns path to the saved image.
    """
    from grocery_list import build_grocery_list
    
    if grocery is None:
        grocery = build_grocery_list(recipe)
    
    fonts = _get_fonts()
    CARDS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Pick a unique color palette for this recipe ──
    pal = _pick_palette(recipe)
    BG_COLOR = pal["bg"]
    HEADER_BG = pal["header"]
    ACCENT = pal["accent"]
    ACCENT2 = pal["accent2"]
    TEXT_WHITE = pal["text_white"]
    TEXT_LIGHT = pal["text_light"]
    TEXT_DIM = pal["text_dim"]
    DIVIDER_COLOR = pal["divider"]
    AISLE_BG = pal["aisle_bg"]
    CHECKBOX_COLOR = pal["checkbox"]
    BADGE_BG = pal["badge_bg"]
    GROCERY_ACCENT = pal["grocery_accent"]

    # ── Phase 1: Calculate total height needed ──
    # Create a temp image just for text measurements
    tmp = Image.new("RGB", (CARD_WIDTH, 100))
    draw = ImageDraw.Draw(tmp)
    
    title = recipe.get("title", "Recipe")
    # Clean up title - title case, trim
    title = _clean_title(title)
    
    y = 0
    
    # Header area
    y += 40 * SCALE  # top padding
    y += _text_height(draw, title, fonts["title"], CONTENT_WIDTH - 40 * SCALE) + 20 * SCALE
    y += 50 * SCALE  # badges row
    y += 30 * SCALE  # gap
    
    # Ingredients section
    y += 50 * SCALE  # section header
    ingredients = recipe.get("ingredients", [])
    for ing in ingredients:
        y += 36 * SCALE  # each ingredient line
    y += 30 * SCALE  # gap
    
    # Instructions section
    y += 50 * SCALE  # section header
    instructions = recipe.get("instructions", [])
    for step in instructions:
        step_text = step if len(step) <= 200 else step[:200] + "..."
        h = _text_height(draw, f"  {step_text}", fonts["body"], CONTENT_WIDTH - 60 * SCALE)
        y += max(h, 28 * SCALE) + 16 * SCALE
    y += 30 * SCALE  # gap
    
    # Tips
    tips = recipe.get("tips", "")
    if tips:
        y += 50 * SCALE + _text_height(draw, tips, fonts["small"], CONTENT_WIDTH - 80 * SCALE) + 30 * SCALE
    
    # Grocery list section
    y += 20 * SCALE  # divider
    y += 60 * SCALE  # section header
    by_aisle = grocery.get("by_aisle", {})
    for aisle, items in by_aisle.items():
        y += 44 * SCALE  # aisle header
        for item in items:
            y += 34 * SCALE  # item
            y += 22 * SCALE  # tip
        y += 16 * SCALE  # aisle gap
    
    y += 60 * SCALE  # bottom padding
    
    total_height = min(y, MAX_HEIGHT)
    
    # ── Phase 2: Draw the card ──
    img = Image.new("RGB", (CARD_WIDTH, total_height), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    y = 0
    
    # ── Header gradient bar ──
    header_h = _text_height(draw, title, fonts["title"], CONTENT_WIDTH - 40 * SCALE) + 110 * SCALE
    _rounded_rect(draw, (0, 0, CARD_WIDTH, header_h), 0, HEADER_BG)
    
    # Subtle gradient overlay (darker at top)
    for i in range(40 * SCALE):
        alpha = int(60 * (1 - i / (40 * SCALE)))
        draw.line([(0, i), (CARD_WIDTH, i)], fill=(0, 0, 0, alpha) if alpha > 0 else (0, 0, 0))
    
    y = 35 * SCALE
    
    # Title
    y = _draw_wrapped(draw, (PADDING + 10 * SCALE, y), title, fonts["title"], TEXT_WHITE, CONTENT_WIDTH - 20 * SCALE) + 15 * SCALE
    
    # Time & serving badges
    badge_x = PADDING + 10 * SCALE
    prep_time = recipe.get("total_time", recipe.get("prep_time", ""))
    servings = recipe.get("servings", "")
    category = recipe.get("category", "")
    
    for badge_text, icon in [(prep_time, "clock"), (servings, "fork"), (category, "tag")]:
        if not badge_text:
            continue
        icon_map = {"clock": "\u23F1", "fork": "\U0001F37D", "tag": "\U0001F3F7"}
        label = f" {badge_text}"
        bbox = draw.textbbox((0, 0), label, font=fonts["small"])
        bw = bbox[2] - bbox[0] + 24 * SCALE
        _rounded_rect(draw, (badge_x, y, badge_x + bw, y + 30 * SCALE), 15 * SCALE, BADGE_BG)
        draw.text((badge_x + 12 * SCALE, y + 5 * SCALE), label, font=fonts["small"], fill=ACCENT)
        badge_x += bw + 12 * SCALE
    
    y = header_h + 20 * SCALE
    
    # ── Ingredients Section ──
    y = _draw_section_header(draw, y, "INGREDIENTS", ACCENT, fonts)
    y += 8 * SCALE
    
    for ing in ingredients:
        amt = ing.get("amount", "")
        item = ing.get("item", "")
        
        # Checkbox
        cx, cy = PADDING + 8 * SCALE, y + 4 * SCALE
        draw.rounded_rectangle((cx, cy, cx + 22 * SCALE, cy + 22 * SCALE), radius=4 * SCALE, outline=CHECKBOX_COLOR, width=2 * SCALE)
        
        # Amount + item
        if amt:
            draw.text((PADDING + 42 * SCALE, y + 2 * SCALE), amt, font=fonts["body_bold"], fill=ACCENT)
            amt_bbox = draw.textbbox((0, 0), amt + " ", font=fonts["body_bold"])
            amt_w = amt_bbox[2] - amt_bbox[0]
            draw.text((PADDING + 42 * SCALE + amt_w, y + 2 * SCALE), item, font=fonts["body"], fill=TEXT_LIGHT)
        else:
            draw.text((PADDING + 42 * SCALE, y + 2 * SCALE), item, font=fonts["body"], fill=TEXT_LIGHT)
        
        y += 36 * SCALE
    
    y += 20 * SCALE
    
    # ── Instructions Section ──
    y = _draw_section_header(draw, y, "INSTRUCTIONS", ACCENT2, fonts)
    y += 8 * SCALE
    
    for i, step in enumerate(instructions, 1):
        step_text = step if len(step) <= 200 else step[:200] + "..."
        
        # Step number circle
        num_text = str(i)
        cx = PADDING + 16 * SCALE
        cy_center = y + 12 * SCALE
        draw.ellipse((cx - 14 * SCALE, cy_center - 14 * SCALE, cx + 14 * SCALE, cy_center + 14 * SCALE), fill=ACCENT2)
        num_bbox = draw.textbbox((0, 0), num_text, font=fonts["subhead"])
        nw = num_bbox[2] - num_bbox[0]
        draw.text((cx - nw // 2, cy_center - 11 * SCALE), num_text, font=fonts["subhead"], fill=BG_COLOR)
        
        # Step text
        step_y = _draw_wrapped(draw, (PADDING + 42 * SCALE, y), step_text, fonts["body"], TEXT_LIGHT, CONTENT_WIDTH - 52 * SCALE)
        y = max(step_y, y + 28 * SCALE) + 12 * SCALE
    
    y += 10 * SCALE
    
    # ── Tips ──
    if tips:
        _rounded_rect(draw, (PADDING, y, CARD_WIDTH - PADDING, y + _text_height(draw, tips, fonts["small"], CONTENT_WIDTH - 80 * SCALE) + 28 * SCALE), 12 * SCALE, BADGE_BG)
        draw.text((PADDING + 16 * SCALE, y + 6 * SCALE), "TIP", font=fonts["subhead"], fill=ACCENT)
        tip_bbox = draw.textbbox((0, 0), "TIP  ", font=fonts["subhead"])
        _draw_wrapped(draw, (PADDING + 16 * SCALE + tip_bbox[2] - tip_bbox[0], y + 8 * SCALE), tips, fonts["small"], TEXT_DIM, CONTENT_WIDTH - 100 * SCALE)
        y += _text_height(draw, tips, fonts["small"], CONTENT_WIDTH - 80 * SCALE) + 40 * SCALE
    
    y += 10 * SCALE
    
    # ── Divider ──
    draw.line([(PADDING, y), (CARD_WIDTH - PADDING, y)], fill=DIVIDER_COLOR, width=2 * SCALE)
    y += 20 * SCALE
    
    # ── Grocery List Section ──
    y = _draw_section_header(draw, y, "GROCERY LIST", GROCERY_ACCENT, fonts)
    y += 4 * SCALE
    
    # Aisle-grouped items
    for aisle, items in by_aisle.items():
        # Aisle label
        _rounded_rect(draw, (PADDING, y, CARD_WIDTH - PADDING, y + 34 * SCALE), 8 * SCALE, AISLE_BG)
        draw.text((PADDING + 14 * SCALE, y + 6 * SCALE), f"\U0001F4CD {aisle.upper()}", font=fonts["subhead"], fill=ACCENT)
        y += 40 * SCALE
        
        for item_data in items:
            item_name = item_data.get("item", "")
            amount = item_data.get("amount", "")
            tip = item_data.get("tip", "")
            
            # Grocery checkbox
            cx = PADDING + 14 * SCALE
            draw.rounded_rectangle((cx, y + 2 * SCALE, cx + 20 * SCALE, y + 22 * SCALE), radius=3 * SCALE, outline=CHECKBOX_COLOR, width=2 * SCALE)
            
            # Item text
            display = f"{amount} {item_name}".strip() if amount else item_name
            draw.text((PADDING + 44 * SCALE, y + 1 * SCALE), display, font=fonts["body"], fill=TEXT_LIGHT)
            y += 28 * SCALE
            
            # Aisle tip (smaller, dimmed)
            if tip:
                tip_short = tip if len(tip) <= 70 else tip[:67] + "..."
                draw.text((PADDING + 44 * SCALE, y), f"  {tip_short}", font=fonts["tiny"], fill=TEXT_DIM)
                y += 22 * SCALE
        
        y += 12 * SCALE
    
    y += 20 * SCALE
    
    # ── Footer ──
    draw.text((PADDING, y), "Recipe Bot", font=fonts["small"], fill=TEXT_DIM)
    
    # ── Save ──
    source_id = recipe.get("source_id", "recipe")
    safe_title = "".join(c if c.isalnum() or c in " -_" else "" for c in title)[:40].strip()
    filename = f"{safe_title}_{source_id}.jpg"
    filepath = CARDS_DIR / filename
    
    # Crop to actual content height
    img = img.crop((0, 0, CARD_WIDTH, min(y + 30 * SCALE, total_height)))
    img.save(filepath, "JPEG", quality=98)
    
    return filepath


def _clean_title(title: str) -> str:
    """Clean up recipe title for display."""
    # Fix "It'S" style capitalization 
    title = title.strip()
    # Title case but preserve short words
    words = title.split()
    cleaned = []
    for i, w in enumerate(words):
        if len(w) <= 3 and i > 0:
            cleaned.append(w.lower())
        else:
            # Fix weird caps like "It'S" → "It's"
            cleaned.append(w.capitalize())
        
    result = " ".join(cleaned)
    # Trim overly long titles
    if len(result) > 80:
        result = result[:77].rsplit(" ", 1)[0] + "..."
    return result


def _draw_section_header(draw, y, text, color, fonts):
    """Draw a section divider with colored accent bar."""
    # Accent bar
    draw.rounded_rectangle((PADDING, y, PADDING + 5 * SCALE, y + 28 * SCALE), radius=2 * SCALE, fill=color)
    draw.text((PADDING + 16 * SCALE, y - 1 * SCALE), text, font=fonts["heading"], fill=color)
    return y + 40 * SCALE


def generate_cards_for_recipes(recipes: list, count: int = 3) -> list:
    """
    Pick `count` random recipes and generate beautiful card images.
    Returns list of (recipe, grocery, image_path) tuples.
    """
    from grocery_list import build_grocery_list
    
    pick = min(count, len(recipes))
    chosen = random.sample(recipes, pick)
    
    results = []
    for recipe in chosen:
        grocery = build_grocery_list(recipe)
        path = generate_recipe_card(recipe, grocery)
        results.append((recipe, grocery, path))
    
    return results


if __name__ == "__main__":
    # Quick test
    with open(RECIPES_FILE) as f:
        recipes = json.load(f)
    
    results = generate_cards_for_recipes(recipes, 3)
    for recipe, grocery, path in results:
        print(f"Generated: {path} ({path.stat().st_size // 1024}KB)")
        print(f"  → {recipe['title']}")
