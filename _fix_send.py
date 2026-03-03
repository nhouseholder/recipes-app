#!/usr/bin/env python3
"""Fix the _send_imessage_text function to handle newlines properly."""
import os

filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'notifier.py')

with open(filepath, 'r') as f:
    content = f.read()

# Find the function boundaries
start_marker = 'def _send_imessage_text('
end_marker = '\ndef _send_imessage_image('

start = content.find(start_marker)
end = content.find(end_marker)

if start < 0 or end < 0:
    print(f"ERROR: Could not find function boundaries. start={start}, end={end}")
    exit(1)

new_func = '''def _send_imessage_text(phone: str, text: str) -> bool:
    """Send a text via iMessage using AppleScript. Handles newlines properly."""
    script = (
        'on run argv\\n'
        '  set phoneNum to item 1 of argv\\n'
        '  set msg to item 2 of argv\\n'
        '  tell application "Messages"\\n'
        '    set targetService to 1st account whose service type = iMessage\\n'
        '    set targetBuddy to participant phoneNum of targetService\\n'
        '    send msg to targetBuddy\\n'
        '  end tell\\n'
        'end run\\n'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script, "--", phone, text],
            capture_output=True, text=True, timeout=15
        )
        return result.returncode == 0
    except Exception:
        return False

'''

content = content[:start] + new_func + content[end:]

with open(filepath, 'w') as f:
    f.write(content)

print("Fixed _send_imessage_text successfully")
print(f"File now has {content.count(chr(10))+1} lines")
