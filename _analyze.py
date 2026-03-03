#!/usr/bin/env python3
"""Analyze recipe quality issues."""
import json

recipes = json.load(open('data/recipes.json'))

few_ing = 0
one_step = 0

print(f'Total: {len(recipes)} recipes\n')

print('=== PROBLEM RECIPES (<=1 step OR <=2 ingredients) ===\n')
for i, r in enumerate(recipes):
    title = r.get('title', '?')
    ings = r.get('ingredients', [])
    steps = r.get('instructions', r.get('steps', []))
    transcript = r.get('transcript', '')
    
    if len(ings) <= 2:
        few_ing += 1
    if len(steps) <= 1:
        one_step += 1
    
    if len(steps) <= 1 or len(ings) <= 2:
        print(f'#{i}: {title[:70]}')
        print(f'  Ingredients ({len(ings)}): {ings}')
        if steps:
            print(f'  Steps ({len(steps)}): {steps[0][:100]}')
        else:
            print(f'  Steps: NONE')
        print(f'  Transcript preview: {transcript[:120]}...')
        print()

print(f'\nSummary: {few_ing} with <=2 ingredients, {one_step} with <=1 step')

# Also show a few GOOD recipes for comparison
print('\n=== GOOD RECIPES (5+ ingredients, 3+ steps) ===\n')
count = 0
for i, r in enumerate(recipes):
    ings = r.get('ingredients', [])
    steps = r.get('instructions', r.get('steps', []))
    if len(ings) >= 5 and len(steps) >= 3:
        print(f'#{i}: {r.get("title","?")[:70]}')
        print(f'  {len(ings)} ingredients, {len(steps)} steps')
        count += 1
        if count >= 5:
            break
