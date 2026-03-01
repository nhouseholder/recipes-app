#!/bin/bash
# ═══════════════════════════════════════════════════════
#  Nick's Recipe Extractor — One-Time Setup
# ═══════════════════════════════════════════════════════
set -e
cd "$(dirname "$0")"

echo ""
echo "══════════════════════════════════════════════"
echo "  🍳 Recipe Extractor — Setting Up"
echo "══════════════════════════════════════════════"
echo ""

# Python
if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3 not found. Install: brew install python3"
    exit 1
fi
echo "✅ Python: $(python3 --version)"

# ffmpeg
if ! command -v ffmpeg &>/dev/null; then
    echo "📦 Installing ffmpeg..."
    if command -v brew &>/dev/null; then
        brew install ffmpeg
    else
        echo "⚠️  Install ffmpeg manually: brew install ffmpeg"
    fi
fi
echo "✅ ffmpeg ready"

# Virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate

# Packages
echo "📦 Installing packages (first time takes ~2 min)..."
pip install --upgrade pip -q 2>/dev/null
pip install -r requirements.txt -q 2>/dev/null
echo "✅ All packages installed"

mkdir -p data/videos data/session

echo ""
echo "══════════════════════════════════════════════"
echo "  ✅ Setup done! Run:  ./run.sh"
echo "══════════════════════════════════════════════"
echo ""
