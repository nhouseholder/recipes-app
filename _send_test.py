#!/usr/bin/env python3
"""Send 3 plain text recipes via iMessage for testing."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Clear pycache
import shutil
for d in os.listdir(os.path.dirname(os.path.abspath(__file__))):
    if d == "__pycache__":
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), d)
        shutil.rmtree(p, ignore_errors=True)

# Force reload
import importlib
import notifier
importlib.reload(notifier)

print("Available functions:", [x for x in dir(notifier) if 'imessage' in x])

if hasattr(notifier, 'imessage_recipe_text'):
    result = notifier.imessage_recipe_text(3)
    print(result)
else:
    print("ERROR: imessage_recipe_text not found!")
    print("File lines:", sum(1 for _ in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'notifier.py'))))
    # Try direct exec
    import types
    mod = types.ModuleType('notifier_fresh')
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'notifier.py')) as f:
        code = f.read()
    exec(compile(code, 'notifier.py', 'exec'), mod.__dict__)
    print("Direct exec functions:", [x for x in dir(mod) if 'imessage' in x])
    if hasattr(mod, 'imessage_recipe_text'):
        result = mod.imessage_recipe_text(3)
        print(result)

