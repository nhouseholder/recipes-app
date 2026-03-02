#!/usr/bin/env python3
"""Launcher that starts the app fully detached from the terminal."""
import subprocess
import sys
import os

app_dir = os.path.dirname(os.path.abspath(__file__))
python = os.path.join(app_dir, "venv", "bin", "python3")
app_py = os.path.join(app_dir, "app.py")
log_file = "/tmp/recipe_server.log"

# Start the server fully detached
with open(log_file, "w") as log:
    proc = subprocess.Popen(
        [python, "-u", app_py],
        cwd=app_dir,
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        start_new_session=True,  # Fully detach from terminal
    )
    print(f"Server started (PID {proc.pid}), log at {log_file}")
