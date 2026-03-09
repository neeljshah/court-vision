#!/usr/bin/env bash
# Start the NBA AI System
# Usage: ./start.sh
# Requires: DATABASE_URL and ANTHROPIC_API_KEY in .env

set -e

if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

echo "Starting NBA AI System..."
echo ""
echo "  Dashboard : http://localhost:8501"
echo "  API       : http://localhost:8000"
echo "  API docs  : http://localhost:8000/docs"
echo ""

# Start FastAPI in background
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!

# Start Streamlit
streamlit run dashboards/app.py --server.port 8501 --server.address 0.0.0.0

# Cleanup on exit
kill $API_PID 2>/dev/null || true
