#!/usr/bin/env bash
# Start both FastAPI and Streamlit
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting HyOpps..."
echo ""

# Start FastAPI in background
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload &
FASTAPI_PID=$!

# Give FastAPI a moment to start
sleep 1

# Start Streamlit
streamlit run frontend/app.py --server.port 8501 --server.headless true &
STREAMLIT_PID=$!

echo ""
echo "═══════════════════════════════════════════════════"
echo "  HyOpps running!"
echo "  FastAPI  → http://localhost:8000"
echo "  API Docs → http://localhost:8000/docs"
echo "  Streamlit → http://localhost:8501"
echo ""
echo "  Default admin: admin@hyopps.local / admin123"
echo "═══════════════════════════════════════════════════"
echo ""

# Wait for either to exit
wait -n $FASTAPI_PID $STREAMLIT_PID
kill $FASTAPI_PID $STREAMLIT_PID 2>/dev/null
