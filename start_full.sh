#!/bin/bash
# ============================================================
# Start EVERYTHING: web server + automation scheduler
# This is the fully autonomous mode — runs 24/7
# ============================================================
source venv/bin/activate

ADMIN_PWD=$(grep ADMIN_PASSWORD .env 2>/dev/null | cut -d= -f2 || echo 'admin123')

echo ""
echo "╔════════════════════════════════════════════════════╗"
echo "║  🤖 AI Tools Empire — FULL AUTONOMOUS MODE        ║"
echo "╠════════════════════════════════════════════════════╣"
echo "║  Website:   http://localhost:8000                  ║"
echo "║  Admin:     http://localhost:8000/admin?pwd=$ADMIN_PWD    ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "Automation schedule:"
echo "  07:00 daily  → Generate 3 AI articles"
echo "  09:00 daily  → Send welcome emails to new subscribers"
echo "  08/12/16/18  → Post to Twitter/X (4x daily)"
echo "  Monday 9:30  → Send weekly newsletter"
echo ""
echo "Press Ctrl+C to stop."
echo ""

# Start scheduler in background
python3 -m automation.scheduler &
SCHEDULER_PID=$!
echo "✅ Scheduler started (PID: $SCHEDULER_PID)"

# Start web server in foreground
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000

# Cleanup on exit
kill $SCHEDULER_PID 2>/dev/null
echo "Stopped."
