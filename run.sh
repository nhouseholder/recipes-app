#!/bin/bash
# ═══════════════════════════════════════════════════════
#  Nick's Recipe Extractor — Launch
# ═══════════════════════════════════════════════════════
cd "$(dirname "$0")"

# Auto-setup if first time
if [ ! -d "venv" ]; then
    echo "First time? Running setup..."
    bash setup.sh
fi

source venv/bin/activate

echo ""
echo "══════════════════════════════════════════════"
echo "  🍳 Opening Recipe Extractor..."
echo "  http://localhost:5050"
echo "  Ctrl+C to stop"
echo "══════════════════════════════════════════════"
echo ""

# Open browser
(sleep 2 && open http://localhost:5050) &

python app.py
