#!/usr/bin/env python3
"""
Re-extract all recipes from stored transcripts using the improved v2 extractor.
Keeps source_id, source_url, and transcript intact. Only re-does the extraction.
"""
import json
import copy
from pathlib import Path
from recipe_extractor import extract_recipe_local

DATA_DIR = Path(__file__).parent / "data"
RECIPES_FILE = DATA_DIR / "recipes.json"
BACKUP_FILE = DATA_DIR / "recipes_v1_backup.json"

def main():
    recipes = json.load(open(RECIPES_FILE))
    print(f"Loaded {len(recipes)} recipes")

    # Backup
    with open(BACKUP_FILE, 'w') as f:
        json.dump(recipes, f, indent=2)
    print(f"Backed up to {BACKUP_FILE}")

    good = 0
    bad = 0
    improved = 0
    removed = 0

    new_recipes = []
    for i, old in enumerate(recipes):
        transcript = old.get("transcript", "")
        caption = ""  # We don't have the original caption stored

        if not transcript or len(transcript.strip()) < 10:
            print(f"  #{i}: SKIP — no transcript")
            removed += 1
            continue

        # Re-extract
        new = extract_recipe_local(transcript, caption)

        if "error" in new:
            print(f"  #{i}: REMOVED — {new['error'][:60]}")
            removed += 1
            continue

        # Preserve metadata from old recipe
        new["source_id"] = old.get("source_id", "")
        new["source_url"] = old.get("source_url", "")
        new["transcript"] = old.get("transcript", "")

        # Check if improved
        old_steps = len(old.get("instructions", old.get("steps", [])))
        old_ings = len(old.get("ingredients", []))
        new_steps = len(new.get("instructions", []))
        new_ings = len(new.get("ingredients", []))

        if new_steps > old_steps or new_ings > old_ings:
            improved += 1
            marker = " ✓ IMPROVED"
        elif new_steps >= old_steps and new_ings >= old_ings:
            good += 1
            marker = ""
        else:
            marker = " (slightly changed)"
            good += 1

        print(f"  #{i}: {new['title'][:45]:45s}  {old_ings}→{new_ings} ing, {old_steps}→{new_steps} steps{marker}")
        new_recipes.append(new)

    # Save
    with open(RECIPES_FILE, 'w') as f:
        json.dump(new_recipes, f, indent=2)

    print(f"\n{'='*55}")
    print(f"Results:")
    print(f"  Kept:     {len(new_recipes)} recipes")
    print(f"  Improved: {improved}")
    print(f"  Removed:  {removed} (garbage/music/too short)")
    print(f"{'='*55}")

if __name__ == "__main__":
    main()
