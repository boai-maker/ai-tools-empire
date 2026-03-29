#!/bin/bash
# Start the web server only
source venv/bin/activate
echo "🌐 Starting AI Tools Empire web server..."
echo "   Visit: http://localhost:8000"
echo "   Admin: http://localhost:8000/admin?pwd=$(grep ADMIN_PASSWORD .env 2>/dev/null | cut -d= -f2 || echo 'admin123')"
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
