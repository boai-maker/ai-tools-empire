#!/bin/bash
# ============================================================
# AI Tools Empire — One-Time Setup Script
# Run once: bash setup.sh
# ============================================================

set -e
echo ""
echo "╔════════════════════════════════════════════╗"
echo "║     🤖 AI Tools Empire — Setup             ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# 1. Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.9+"
    exit 1
fi
echo "✅ Python: $(python3 --version)"

# 2. Create virtualenv
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# 3. Activate and install deps
source venv/bin/activate
echo "📦 Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "✅ Dependencies installed"

# 4. Create .env if not exists
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "⚠️  .env file created from template."
    echo "    Please edit .env and add your API keys before running the server."
    echo ""
fi

# 5. Initialize database
python3 -c "from database.db import init_db; init_db(); print('✅ Database initialized')"

# 6. Seed content queue
python3 -c "
from database.db import init_db
from automation.content_generator import populate_initial_queue
init_db()
populate_initial_queue()
print('✅ Content queue seeded with 28 high-intent topics')
" 2>/dev/null || echo "⚠️  Queue seeding skipped (API key needed)"

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║  ✅ Setup complete!                        ║"
echo "╚════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1. Edit .env and add your API keys"
echo "  2. Run: bash start.sh           (website only)"
echo "  3. Run: bash start_full.sh      (website + scheduler)"
echo ""
echo "Get your API keys:"
echo "  • Anthropic: https://console.anthropic.com/"
echo "  • Resend:    https://resend.com/ (free: 3k emails/mo)"
echo "  • Twitter:   https://developer.twitter.com/"
echo ""
echo "Then register for affiliate programs (see .env.example for links)"
echo ""
