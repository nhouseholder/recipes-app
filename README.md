# 🍳 Nick's Recipe Extractor

Turns your saved Instagram recipe videos into clean, simple recipes — automatically.

## Your Preferences (Built In)

- **Minimal ingredients** — stripped down to essentials
- **No seed oils** — canola, vegetable, soybean, corn, sunflower etc. are auto-replaced with butter/olive oil/avocado oil
- **Under 1 hour** — if a recipe takes too long, it gets simplified
- **Basic equipment only** — frying pan, baking sheet, oven, microwave, sauce pot. No air fryers, instant pots, etc.

## Quick Start

### 1. Setup (one time)

```bash
cd recipes-app
./setup.sh
```

This installs Python packages including:
- **Whisper** (free, local AI transcription — no API key needed)
- **Flask** (web server)
- **yt-dlp** (video downloader)

### 2. Launch the App

```bash
./run.sh
```

Opens at **http://localhost:5000** in your browser.

### 3. Import Your Recipe Videos

You have 4 options:

| Method | How | Reliability |
|--------|-----|-------------|
| **Paste URLs** (recommended) | Copy Instagram reel links and paste them | ⭐⭐⭐ |
| **Instagram Auto-Fetch** | Enter your Instagram login in Settings | ⭐⭐ |
| **Data Export** | Download your data from Instagram Settings | ⭐⭐⭐ |
| **Manual Drop** | Put .mp4 files in `data/videos/` folder | ⭐⭐⭐ |

**Easiest method:** Open each saved reel on Instagram, tap Share → Copy Link, paste all links into the "Paste URLs" box.

### 4. Process → Recipes

Click **Process All Videos** and the app will:
1. Transcribe each video using Whisper AI (runs locally, free)
2. Extract the recipe and simplify it
3. Replace any seed oils with healthy fats
4. Display your clean recipe cards

## Optional: Better Recipe Extraction

Without an API key, the app uses a basic local parser. For **much better** results:

1. Get an OpenAI API key at https://platform.openai.com/api-keys
2. Go to Settings in the app and paste it in
3. Uses GPT-4o-mini (~$0.01 per recipe) for intelligent extraction

## Project Structure

```
recipes-app/
├── app.py                 # Flask web server
├── instagram_fetcher.py   # Downloads videos from Instagram
├── transcriber.py         # Whisper AI transcription
├── recipe_extractor.py    # LLM recipe extraction + rules
├── requirements.txt       # Python dependencies
├── setup.sh               # One-time setup script
├── run.sh                 # Launch script
├── .env                   # Your credentials (created by setup)
├── templates/index.html   # Web UI
├── static/
│   ├── style.css          # Styles
│   └── app.js             # Frontend logic
└── data/
    ├── videos/            # Downloaded video files
    └── recipes.json       # Your extracted recipes
```

## Requirements

- **macOS** (or Linux/Windows with minor adjustments)
- **Python 3.9+**
- **ffmpeg** (`brew install ffmpeg`)
- ~500MB disk space for Whisper model
